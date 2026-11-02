import importlib.util
import json
import os
from pathlib import Path
import socket
from types import SimpleNamespace

import pytest

from conftest import make_wav

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("screening_duration_experiment", ROOT / "scripts/compare_screening_durations.py")
experiment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(experiment)


def recording(**changes):
    return {"id": "diagnostic", "pcm": bytes(range(256)) * 505,
            "fixture": True, "label": "unlabelled", "split": "diagnostic",
            "language": "not_speech", "condition": "synthetic_signal", **changes}


class ScreenerDouble:
    def __init__(self, outputs=None, ready=True):
        self.outputs = iter(outputs) if outputs else None
        self.inputs = []
        self.ready = ready

    def status(self):
        return {"ready": self.ready, "fixture": True}

    def analyze(self, pcm, rate):
        self.inputs.append((pcm, rate))
        result = next(self.outputs) if self.outputs else {"score": .1, "verdict": "allow"}
        if isinstance(result, Exception):
            raise result
        return SimpleNamespace(as_dict=lambda: {
            "compute_ms": 2.5, "reasons": ["test_double"], "windows_analyzed": 1, **result})


def test_default_plan_never_loads_model_dataset_audio_network_or_provider_environment(monkeypatch, capsys):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Plan performed inference, network or data access")

    class NoProviderEnvironment(dict):
        def get(self, key, default=None):
            if key in {"LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"}:
                return default
            return forbidden()
        __getitem__ = forbidden

    with monkeypatch.context() as context:
        context.setattr(experiment, "_runtime", forbidden)
        context.setattr(experiment, "_dataset", forbidden)
        context.setattr(experiment, "diagnostic_recordings", forbidden)
        context.setattr(socket, "socket", forbidden)
        context.setattr(os, "environ", NoProviderEnvironment())
        assert experiment.main([]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["plan_only"] is True
    assert result["live_activation"] is result["affects_live_screening"] is False
    assert result["accuracy"] is None
    assert result["inference_calls"] == result["analysis_calls"] == result["provider_calls"] == 0
    assert [item["observed_audio_ms"] for item in result["candidates"]] == [500, 1000, 2000, 3000, 4037.5]


@pytest.mark.parametrize("samples", experiment.PREFIX_SAMPLES)
def test_prefix_repetition_has_exact_model_size_and_never_reads_later_source(samples):
    source = recording()["pcm"]
    prefix = source[:samples * 2]
    result = experiment.tiled_prefix(source, samples)
    assert len(result) == experiment.WINDOW_SAMPLES * 2
    assert result == (prefix * 9)[:experiment.WINDOW_SAMPLES * 2]
    changed_tail = prefix + bytes([17]) * (len(source) - len(prefix))
    assert experiment.tiled_prefix(changed_tail, samples) == result
    if samples == experiment.WINDOW_SAMPLES:
        assert result == source[:experiment.WINDOW_SAMPLES * 2]


@pytest.mark.parametrize("pcm,samples", [(b"", 16000), (b"x", 8000), (bytes(128000), 16000),
    (None, 16000), (bytes(16000 * 2 * 31), 16000), (recording()["pcm"], True),
    (recording()["pcm"], 7999)], ids=["empty", "odd", "short", "wrong_type", "oversized", "bool_samples", "unreviewed_duration"])
def test_malformed_or_insufficient_source_audio_fails(pcm, samples):
    with pytest.raises(ValueError):
        experiment.tiled_prefix(pcm, samples)


def test_pairing_reports_score_and_verdict_changes_without_accuracy_claim():
    screener = ScreenerDouble([
        {"score": .9, "verdict": "suspicious"},
        {"score": .1, "verdict": "allow"},
        {"score": .5, "verdict": "unknown"},
        {"score": .9, "verdict": "suspicious"},
        {"score": .8, "verdict": "suspicious"},
    ])
    result = experiment.compare(screener, [recording()])
    assert result["source_recording_count"] == 1
    assert result["analysis_calls"] == result["successfully_scored_model_windows"] == 5
    assert result["inference_calls"] is None  # Wrapper calls are not a native inference counter.
    assert result["paired_short_comparisons"] == 4
    assert result["verdict_changes_from_native"] == 2
    assert result["results"][0]["score_delta_from_full"] == -.8
    assert result["results"][0]["observed_audio_ms"] == 500
    assert result["results"][0]["model_input_ms"] == 4037.5
    assert result["results"][0]["repeated_samples"] == 56600
    assert result["accuracy"] is None and result["accuracy_preservation_proven"] is False
    assert result["evaluation_by_duration"] == []
    assert all(len(pcm) == experiment.WINDOW_SAMPLES * 2 and rate == 16000 for pcm, rate in screener.inputs)
    assert "pcm" not in json.dumps(result)


def test_local_failure_is_retained_redacted_and_not_counted_as_agreement():
    screener = ScreenerDouble([RuntimeError("private-path-secret"),
        *[{"score": .1, "verdict": "allow"}] * 4])
    result = experiment.compare(screener, [recording()])
    assert result["analysis_calls"] == 5
    assert result["successfully_scored_model_windows"] == 4
    assert result["comparisons_missing_baseline_or_result"] == 4
    assert result["verdict_changes_from_native"] == 0
    assert "private-path-secret" not in json.dumps(result)
    assert result["results"][-1]["error"] == "local_analysis_failed"


def test_fixture_generator_is_fixed_bounded_and_unlabelled():
    first, second = experiment.diagnostic_recordings(), experiment.diagnostic_recordings()
    assert first == second and len(first) == 5
    assert len({row["pcm"] for row in first}) == 5
    assert all(row["fixture"] is True and row["label"] == "unlabelled" for row in first)
    result = experiment.compare(ScreenerDouble(), first)
    assert result["analysis_calls"] == 25
    assert result["source_recording_count"] == 5
    assert result["accuracy"] is None and result["live_activation"] is False


def test_experiment_does_not_enable_short_audio_in_the_live_classifier():
    from artha_mesh.services.audio_screening import LocalAudioScreener

    live = LocalAudioScreener(load_model=False)
    short = recording()["pcm"][:16000]
    assert live.window_samples == 64600
    assert live.analyze(short).verdict == "unknown"
    assert live.analyze(short).windows_analyzed == 0


def test_larger_batch_and_nonfixture_without_preflight_fail_before_analysis():
    screener = ScreenerDouble()
    with pytest.raises(ValueError, match="five"):
        experiment.compare(screener, [recording()] * 6)
    with pytest.raises(ValueError, match="preflight"):
        experiment.compare(screener, [recording(fixture=False, label="genuine")])
    assert screener.inputs == []


def test_missing_model_never_attempts_analysis():
    screener = ScreenerDouble(ready=False)
    report = experiment.compare(screener, [recording()])
    assert report["status"] == "blocked_model_unavailable"
    assert report["analysis_calls"] == report["inference_calls"] == 0
    assert screener.inputs == []


def test_report_refuses_overwrite_before_any_model_work(tmp_path, monkeypatch):
    target = tmp_path / "existing.json"
    target.write_text("keep-me")
    monkeypatch.setattr(experiment, "_runtime", lambda: pytest.fail("Must not load model"))
    assert experiment.main(["--diagnostics", "--output", str(target)]) == 2
    assert target.read_text() == "keep-me"


def manifest(tmp_path, *, consent=True, rows=4):
    inputs = []
    for index in range(rows):
        filename = f"private-{index}.wav"
        (tmp_path / filename).write_bytes(make_wav(seconds=4.1 + index / 10, rate=16000))
        inputs.append({"id": f"private-id-{index}", "wav": filename,
                       "label": "genuine" if index % 2 == 0 else "spoof", "fixture": False,
                       "consent": consent, "label_evidence": "declared evidence only",
                       "speaker_group": f"private-speaker-{index}", "source_group": f"private-source-{index}",
                       "split": "calibration" if index < 2 else "evaluation", "condition": "clean", "language": "hi"})
    path = tmp_path / "manifest.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in inputs), encoding="utf-8")
    return path


def test_invalid_manifest_blocks_before_model_and_exports_no_private_paths(tmp_path, monkeypatch):
    source = manifest(tmp_path, consent=False)
    output = tmp_path / "report.json"
    monkeypatch.setattr(experiment, "_runtime", lambda: pytest.fail("Must not load model"))
    assert experiment.main(["--manifest", str(source), "--output", str(output)]) == 2
    result = json.loads(output.read_text())
    assert result["status"] == "blocked_dataset"
    assert result["inference_calls"] == 0 and result["accuracy"] is None
    assert "private-" not in output.read_text()


def test_manifest_batch_bound_blocks_without_silently_selecting_first_five(tmp_path):
    preflight, rows = experiment.strict_recordings(manifest(tmp_path, rows=6))
    assert preflight["ready_for_scoring"] is False
    assert rows == []
    assert {"row": None, "code": "duration_batch_exceeds_five_recordings"} in preflight["issues"]


def test_manifest_results_keep_calibration_out_of_held_out_metrics(tmp_path):
    preflight, rows = experiment.strict_recordings(manifest(tmp_path))
    assert preflight["ready_for_scoring"] is True
    assert all(row["id"].startswith("recording-") for row in rows)
    # Calibration correct, held-out genuine false alarm, held-out spoof miss.
    outputs = ([{"score": .1, "verdict": "allow"}] * 5
               + [{"score": .9, "verdict": "suspicious"}] * 5
               + [{"score": .9, "verdict": "suspicious"}] * 5
               + [{"score": .1, "verdict": "allow"}] * 5)
    report = experiment.compare(ScreenerDouble(outputs), rows, dataset_preflight=preflight)
    for candidate in report["evaluation_by_duration"]:
        assert candidate["source_recordings"] == 2
        assert candidate["false_alarms"] == candidate["misses"] == 1
        assert candidate["by_language"]["hi"]["source_recordings"] == 2
    assert report["accuracy_preservation_proven"] is False
    assert "private-" not in json.dumps(report)


def test_explicit_batches_keep_global_source_indexes_and_validate_whole_study(tmp_path):
    source = manifest(tmp_path, rows=6)
    preflight, first = experiment.strict_recordings(source, batch_index=0)
    assert preflight["ready_for_scoring"] is True
    assert [row["id"] for row in first] == [f"recording-{i:03d}" for i in range(1, 6)]
    preflight, second = experiment.strict_recordings(source, batch_index=1)
    assert [row["id"] for row in second] == ["recording-006"]
    assert preflight["batch_selection"]["study_recordings"] == 6
    assert preflight["batch_selection"]["batch_count"] == 2
    rows = [json.loads(line) for line in source.read_text().splitlines()]
    # Leakage in the OTHER batch must block this one before inference.
    rows[-1]["speaker_group"] = rows[0]["speaker_group"]
    source.write_text("".join(json.dumps(row) + "\n" for row in rows))
    preflight, selected = experiment.strict_recordings(source, batch_index=0)
    assert preflight["ready_for_scoring"] is False
    assert selected == []
    assert any(issue["code"] == "speaker_group_crosses_splits" for issue in preflight["issues"])


@pytest.mark.parametrize("index", [-1, 2, True])
def test_duration_batch_selection_rejects_invalid_or_missing_batches(tmp_path, index):
    with pytest.raises(ValueError, match="batch index"):
        experiment.strict_recordings(manifest(tmp_path, rows=6), batch_index=index)


def test_batch_option_cannot_turn_a_diagnostic_plan_into_inference(monkeypatch):
    monkeypatch.setattr(experiment, "_runtime", lambda: pytest.fail("Must not load model"))
    assert experiment.main(["--diagnostics", "--batch-index", "0"]) == 2
