"""Local experiment guardrails. No real model, provider or socket is needed."""
import copy
import hashlib
import importlib.util
from pathlib import Path
import socket

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("screening_compute_experiment", ROOT / "scripts/benchmark_screening_compute.py")
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)


@pytest.mark.parametrize("threads,repeats,wall", [
    ([], 5, 120), ([2, 1], 5, 120), ([1, 1], 5, 120),
    ([1, 8], 5, 120), ([True, 2], 5, 120), ([1], 0, 120),
    ([1], 11, 120), ([1], True, 120), ([1], 5, 0),
    ([1], 5, 181), ([1], 5, float("nan")),
])
def test_refuses_unbounded_or_misleading_comparisons(threads, repeats, wall):
    with pytest.raises(ValueError):
        experiment.validate_options(threads, repeats, wall)


def test_synthetic_fixtures_are_identical_pcm_not_shortened_or_labelled_speech():
    first, second = experiment.fixtures(), experiment.fixtures()
    assert len(first) == 4
    assert all(a["pcm_sha256"] == b["pcm_sha256"] for a, b in zip(first, second, strict=True))
    for row in first:
        assert len(row["pcm"]) == 64600 * 2
        assert row["waveform"].shape == (64600,)
        assert row["waveform"].dtype == np.float32
        assert not row["waveform"].flags.writeable
        assert row["pcm_sha256"] == hashlib.sha256(row["pcm"]).hexdigest()
        assert "label" not in row


def test_model_must_match_checksum_before_session_construction(tmp_path):
    missing = tmp_path / "missing.onnx"
    with pytest.raises(ValueError):
        experiment.verify_model(missing)
    missing.write_bytes(b"unreviewed model")
    with pytest.raises(ValueError, match="checksum"):
        experiment.verify_model(missing)


@pytest.mark.parametrize("value", [np.zeros((2, 2)), np.array([[float("nan"), 1]]), np.zeros((1, 3))])
def test_invalid_model_logits_are_not_timing_evidence(value):
    class BadSession:
        def run(self, *_): return [value]
    with pytest.raises(ValueError, match="logits"):
        experiment.infer(BadSession(), np.zeros(64600, np.float32))


def test_logits_are_retained_unrounded_and_not_mutated_by_softmax():
    logits = np.array([[1.234567891, 2.345678912]], dtype=np.float64)
    class Session:
        def run(self, *_): return [logits]
    observed, score, verdict = experiment.infer(Session(), np.zeros(64600, np.float32))
    assert np.array_equal(observed, logits)
    assert observed[0, 0] == 1.234567891
    assert isinstance(score, float) and score != round(score, 6)
    assert verdict == "unknown"


def test_benchmark_uses_exact_inputs_and_refuses_faster_nonparity_candidate(tmp_path, monkeypatch):
    path = tmp_path / "model.onnx"
    path.write_bytes(b"reviewed test bytes")
    monkeypatch.setattr(experiment, "MODEL_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())
    seen, counter = [], [0.0]

    class Session:
        def __init__(self, threads): self.threads = threads
        def run(self, names, values):
            counter[0] += .006 / self.threads
            waveform = values["wav"]
            seen.append((self.threads, hashlib.sha256(waveform.tobytes()).hexdigest()))
            assert names == ["logits"] and waveform.shape == (1, 64600)
            assert waveform.dtype == np.float32
            delta = 1e-7 if self.threads == 2 else .1 if self.threads == 4 else 0
            return [np.array([[-1.0 + delta, 1.0]])]

    def no_network(*_, **__): raise AssertionError("Experiment attempted network")
    monkeypatch.setattr(socket, "socket", no_network)
    report = experiment.benchmark(path, repeats=1, session_factory=lambda _path, threads: Session(threads),
                                  timer=lambda: counter[0])
    assert report["complete"]
    assert report["candidate_threads_for_review"] == 2
    assert report["configurations"][1]["parity_passed"]
    assert not report["configurations"][2]["parity_passed"]
    reference_hashes = {digest for threads, digest in seen if threads == 1}
    assert all(digest in reference_hashes for _, digest in seen)
    assert report["accuracy"] is None
    assert not report["representative_speech_accuracy_tested"]
    assert report["window_samples"] == 64600 and report["window_ms"] == 4037.5
    assert report["provider_calls"] == report["model_downloads"] == 0
    assert not report["production_configuration_changed"]
    assert all("pcm" not in row for config in report["configurations"] for row in config["fixtures"])


def test_no_candidate_when_data_incomplete_or_any_fixture_slower():
    baseline = {"threads": 1, "parity_passed": True,
                "kernel_summary": {"median_ms": 10},
                "analysis_summary": {"median_ms": 12},
                "fixtures": [{"kernel_summary": {"median_ms": 10}, "analysis_summary": {"median_ms": 12}}]}
    faster = copy.deepcopy(baseline)
    faster["threads"] = 2
    faster["kernel_summary"]["median_ms"] = 5
    faster["analysis_summary"]["median_ms"] = 6
    faster["fixtures"][0]["kernel_summary"]["median_ms"] = 5
    faster["fixtures"][0]["analysis_summary"]["median_ms"] = 6
    assert experiment.choose_candidate([baseline, faster], complete=False) is None
    faster["fixtures"][0]["kernel_summary"]["median_ms"] = 11
    assert experiment.choose_candidate([baseline, faster], complete=True) is None


def test_two_inflight_probe_preserves_same_full_inputs_and_tracks_each_thread(tmp_path, monkeypatch):
    path = tmp_path / "model.onnx"
    path.write_bytes(b"reviewed two-worker model fixture")
    monkeypatch.setattr(experiment, "MODEL_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())
    seen = []

    class Session:
        def run(self, names, inputs):
            waveform = inputs["wav"]
            assert waveform.shape == (1, 64600)
            seen.append(hashlib.sha256(waveform.tobytes()).hexdigest())
            return [np.array([[-1.0, 1.0]], dtype=np.float32)]

    report = experiment.benchmark_concurrency(path, threads=[1, 2], repeats=1,
                                              session_factory=lambda *_: Session())
    assert report["complete"] and report["concurrent_callers"] == 2
    assert report["window_samples"] == 64600
    assert report["accuracy"] is None
    assert len(report["configurations"]) == 2
    for configuration in report["configurations"]:
        assert configuration["analysis_summary"]["count"] == 4
        assert configuration["pair_wall_summary"]["count"] == 2
        assert configuration["parity_passed"]
        assert all(row["max_abs_raw_logit_difference"] == 0 for row in configuration["observations"])
    assert len(set(seen)) == 4
