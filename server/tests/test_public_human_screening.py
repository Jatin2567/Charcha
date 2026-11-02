"""Fabricated WAV and model-double checks; no real speech, model or network."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import struct
from types import SimpleNamespace
import wave

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("public_human_study", ROOT / "scripts/evaluate_public_human_speech.py")
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)


def wav_bytes(value=1, frames=128000, rate=16000, channels=1, width=2):
    output = io.BytesIO()
    with wave.open(output, "wb") as clip:
        clip.setnchannels(channels)
        clip.setsampwidth(width)
        clip.setframerate(rate)
        clip.writeframes(struct.pack("<h", value) * frames * channels if width == 2 else b"\x80" * frames * channels * width)
    return output.getvalue()


def write_manifest(tmp_path, count=5, mutate=None):
    rows = []
    for index in range(count):
        language = study.LANGUAGES[index % 5]
        raw = wav_bytes(index + 1)
        path = tmp_path / f"private-{index}.wav"
        path.write_bytes(raw)
        row = {
            "schema_version": 1, "id": f"private-source-{index}", "wav": str(path),
            "language": language, "label": "genuine", "split": "evaluation",
            "source_dataset": study.DATASET, "source_revision": study.REVISION,
            "source_config": study.CONFIGS[language], "source_split": "test",
            "source_filename": f"private-original-{index}.wav", "num_samples": 128000,
            "sha256": hashlib.sha256(raw).hexdigest(), "source_sha256": "a" * 64,
            "usage_permission": "public_license", "license": "cc-by-4.0",
            "attribution": "Google FLEURS (Conneau et al., 2022)", "speaker_id": None,
        }
        if mutate:
            mutate(row, index)
        rows.append(row)
    manifest = tmp_path / "public-manifest.jsonl"
    manifest.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return manifest


class ScreenerDouble:
    def __init__(self, outputs=None, ready=True):
        self.outputs = iter(outputs) if outputs else None
        self.inputs = []
        self.ready = ready

    def status(self):
        return {"ready": self.ready, "id": "unit-test-double", "sha256": "test-not-a-model",
                "threshold": .8, "allow_threshold": .2, "cpu_threads": 2,
                "private_path": "DO-NOT-EXPORT-PRIVATE-MODEL-PATH"}

    def analyze(self, pcm, rate):
        self.inputs.append((pcm, rate))
        result = next(self.outputs) if self.outputs else {"score": .1, "verdict": "allow"}
        if isinstance(result, Exception):
            raise result
        return SimpleNamespace(as_dict=lambda: {"compute_ms": 2.5, "windows_analyzed": 1, **result})


def fake_prepared(count=50):
    return {"ready_for_scoring": True, "issues": []}, [
        {"id": f"recording-{index + 1:03d}", "language": study.LANGUAGES[index % 5],
         "pcm": struct.pack("<h", index) * 128000} for index in range(count)
    ]


def install_doubles(monkeypatch, *, screener=None, prepared=True):
    experiment = study._experiment()
    screener = screener or ScreenerDouble()
    loads = []
    def factory(model, **kwargs):
        loads.append((model, kwargs))
        return screener
    monkeypatch.setattr(experiment, "_runtime", lambda: (factory, None))
    monkeypatch.setattr(study, "_experiment", lambda: experiment)
    if prepared:
        monkeypatch.setattr(study, "_prepare", lambda *_: fake_prepared())
    return experiment, screener, loads


def test_default_plan_does_not_touch_data_model_network_or_provider_environment(monkeypatch, capsys):
    def forbidden(*_a, **_k):
        raise AssertionError("Default plan performed access")
    class NoProviderEnvironment(dict):
        def get(self, key, default=None):
            return default if key in {"LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"} else forbidden()
        __getitem__ = forbidden
    with monkeypatch.context() as context:
        context.setattr(study, "_prepare", forbidden)
        context.setattr(study, "_experiment", forbidden)
        context.setattr(socket, "socket", forbidden)
        context.setattr(os, "environ", NoProviderEnvironment())
        assert study.main(["--manifest", "private-missing.jsonl"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["plan_only"] and report["provider_calls"] == report["inference_calls"] == 0
    assert report["accuracy"] is report["detection_rate"] is report["miss_rate"] is report["distinct_speakers"] is None
    assert report["maximum_source_recordings"] == 50 and report["maximum_analysis_calls"] == 250


def test_fifty_sources_pair_with_one_frozen_two_thread_model_and_no_accuracy_claim(monkeypatch):
    _, screener, loads = install_doubles(monkeypatch)
    report = study.run_study(Path("unused"))
    assert loads == [(None, {"threshold": .8, "allow_threshold": .2, "cpu_threads": 2})]
    assert len(screener.inputs) == report["analysis_calls"] == report["successfully_scored_model_windows"] == 250
    assert all(len(pcm) == 129200 and rate == 16000 for pcm, rate in screener.inputs)
    assert report["status"] == "human_false_alarm_pilot_complete"
    assert report["inference_calls"] is None
    assert report["accuracy"] is report["miss_rate"] is report["detection_rate"] is report["pass_decision"] is None
    assert report["accuracy_preservation_proven"] is report["live_activation"] is report["voice_cloning"] is False
    assert report["unattempted_analysis_calls"] == report["failed_analysis_calls"] == 0
    for duration in report["evaluation_by_duration"]:
        assert duration["source_recordings"] == duration["allow"] == duration["classified"] == 50
        assert duration["false_alarms"] == duration["unknown"] == 0
        assert duration["classification_coverage"] == 1
        assert duration["accuracy"] is duration["distinct_speakers"] is None
        assert duration["compute_p50_ms"] == duration["compute_p95_ms"] == 2.5
        assert all(metric["genuine_recordings"] == 10 for metric in duration["by_language"].values())
    exported = json.dumps(report)
    assert "DO-NOT-EXPORT" not in exported and '"pcm"' not in exported and '"wav"' not in exported


def test_native_input_and_prefixes_use_only_same_first_window_and_not_later_tail(monkeypatch):
    preflight, recordings = fake_prepared()
    raw = bytes(range(256)) * 505
    recordings[0]["pcm"] = raw + b"\x7f\x7f" * 100000
    experiment, screener, _ = install_doubles(monkeypatch)
    monkeypatch.setattr(study, "_prepare", lambda *_: (preflight, recordings))
    study.run_study(Path("unused"))
    for index, samples in enumerate((64600, 8000, 16000, 32000, 48000)):
        assert screener.inputs[index][0] == experiment.tiled_prefix(recordings[0]["pcm"], samples)
    assert screener.inputs[0][0] == raw[:129200]


def test_unknown_error_and_false_alarms_retain_all_genuine_denominators(monkeypatch):
    outputs = []
    for index in range(50):
        output = ({"score": None, "verdict": "unknown"} if index < 10 else
                  RuntimeError("private failure") if index < 20 else
                  {"score": .9, "verdict": "suspicious"} if index < 30 else
                  {"score": .1, "verdict": "allow"})
        outputs.extend([output] * 5)
    install_doubles(monkeypatch, screener=ScreenerDouble(outputs))
    report = study.run_study(Path("unused"))
    assert report["failed_analysis_calls"] == 50 and report["status"] == "analysis_complete_with_errors"
    for duration in report["evaluation_by_duration"]:
        assert duration["source_recordings"] == 50
        assert duration["unknown"] == duration["errors"] == duration["false_alarms"] == 10
        assert duration["allow"] == 20 and duration["classification_coverage"] == .6
        assert duration["false_alarms_over_all_genuine"] == .2
        assert duration["false_alarm_rate_classified"] == 1 / 3
    assert "private failure" not in json.dumps(report)


def test_all_unknown_has_zero_coverage_and_null_conditional_false_alarm_rate(monkeypatch):
    install_doubles(monkeypatch, screener=ScreenerDouble([{"score": None, "verdict": "unknown"}] * 250))
    report = study.run_study(Path("unused"))
    assert all(row["unknown"] == 50 and row["classification_coverage"] == 0
               and row["false_alarm_rate_classified"] is None for row in report["evaluation_by_duration"])


def test_changed_prefix_reports_paired_score_and_verdict_changes(monkeypatch):
    outputs = []
    for _ in range(50):
        outputs.extend([{"score": .1, "verdict": "allow"},
                        {"score": .9, "verdict": "suspicious"},
                        {"score": .1, "verdict": "allow"},
                        {"score": .1, "verdict": "allow"},
                        {"score": .1, "verdict": "allow"}])
    install_doubles(monkeypatch, screener=ScreenerDouble(outputs))
    report = study.run_study(Path("unused"))
    half_second = report["evaluation_by_duration"][0]
    assert half_second["observed_audio_ms"] == 500
    assert half_second["verdict_changes_from_full"] == 50
    assert half_second["maximum_absolute_score_delta_from_full"] == .8


def test_wall_budget_leaves_unattempted_results_and_stops_before_next_call(monkeypatch):
    current = [0.0]
    _, screener, _ = install_doubles(monkeypatch, screener=ScreenerDouble([RuntimeError("private"), {"score": .1, "verdict": "allow"}]))
    original = screener.analyze
    def delayed(pcm, rate):
        current[0] += .6
        return original(pcm, rate)
    screener.analyze = delayed
    report = study.run_study(Path("unused"), max_wall_seconds=1, clock=lambda: current[0])
    assert report["status"] == "stopped_wall_budget"
    assert report["analysis_calls"] == 2 and report["failed_analysis_calls"] == 1
    assert report["unattempted_analysis_calls"] == 248 and report["wall_seconds"] == 1.2


def test_expired_preflight_budget_skips_model_initialization(monkeypatch):
    current = [0.0]
    _, screener, loads = install_doubles(monkeypatch)
    def expired(*_):
        current[0] = 2
        return fake_prepared()
    monkeypatch.setattr(study, "_prepare", expired)
    report = study.run_study(Path("unused"), max_wall_seconds=1, clock=lambda: current[0])
    assert loads == [] and screener.inputs == []
    assert report["analysis_calls"] == 0 and report["unattempted_analysis_calls"] == 250


def test_missing_model_does_not_analyze_and_reports_all_rows_unattempted(monkeypatch):
    _, screener, loads = install_doubles(monkeypatch, screener=ScreenerDouble(ready=False))
    report = study.run_study(Path("unused"))
    assert len(loads) == 1 and screener.inputs == []
    assert report["status"] == "blocked_model_unavailable" and report["analysis_calls"] == 0
    assert report["unattempted_analysis_calls"] == 250


@pytest.mark.parametrize("field", ["source_dataset", "source_revision", "source_config", "source_split", "label", "split",
                                  "usage_permission", "license", "attribution", "source_filename", "sha256", "source_sha256", "num_samples", "id", "wav"])
def test_incomplete_provenance_or_audio_blocks_before_model_and_exports_no_paths(tmp_path, monkeypatch, field):
    path = write_manifest(tmp_path, mutate=lambda row, index: row.pop(field) if index == 0 else None)
    monkeypatch.setattr(study, "_experiment", lambda: pytest.fail("Invalid public speech must not load model"))
    report = study.run_study(path)
    assert report["status"] == "blocked_dataset" and report["analysis_calls"] == report["inference_calls"] == 0
    assert "private-" not in json.dumps(report)


def test_valid_source_schema_runs_with_fabricated_audio_and_model_double_only(tmp_path, monkeypatch):
    manifest = write_manifest(tmp_path)
    _, screener, loads = install_doubles(monkeypatch, prepared=False)
    report = study.run_study(manifest)
    assert report["dataset_preflight"]["ready_for_scoring"] is True
    assert report["source_recording_count"] == 5 and report["analysis_calls"] == 25
    assert len(loads) == 1 and len(screener.inputs) == 25
    assert "private-" not in json.dumps(report)


@pytest.mark.parametrize("mutation", [
    lambda row, index: row.update(label="spoof") if index == 0 else None,
    lambda row, index: row.update(source_revision="main") if index == 0 else None,
    lambda row, index: row.update(source_config="ta_in") if index == 0 else None,
    lambda row, index: row.update(speaker_id="invented-speaker") if index == 0 else None,
    lambda row, index: row.update(source_filename="../escape.wav") if index == 0 else None,
    lambda row, index: row.update(sha256="0" * 64) if index == 0 else None,
    lambda row, index: row.update(num_samples=128001) if index == 0 else None,
])
def test_altered_origin_hash_identity_and_frame_count_fail_before_model(tmp_path, monkeypatch, mutation):
    manifest = write_manifest(tmp_path, mutate=mutation)
    monkeypatch.setattr(study, "_experiment", lambda: pytest.fail("Invalid speech must not load model"))
    assert study.run_study(manifest)["status"] == "blocked_dataset"


def test_missing_language_duplicate_pcm_and_escaped_path_block_before_model(tmp_path, monkeypatch):
    manifest = write_manifest(tmp_path)
    rows = [json.loads(line) for line in manifest.read_text().splitlines()]
    rows.pop()
    manifest.write_text("".join(json.dumps(row) + "\n" for row in rows))
    monkeypatch.setattr(study, "_experiment", lambda: pytest.fail("Invalid speech must not load model"))
    report = study.run_study(manifest)
    assert any(issue["code"] == "missing_public_human_mr" for issue in report["dataset_preflight"]["issues"])
    rows[1]["wav"], rows[1]["sha256"] = rows[0]["wav"], rows[0]["sha256"]
    rows[2]["wav"] = str(tmp_path.parent / "escaped-private.wav")
    manifest.write_text("".join(json.dumps(row) + "\n" for row in rows))
    report = study.run_study(manifest)
    assert any(issue["code"] == "duplicate_decoded_audio" for issue in report["dataset_preflight"]["issues"])
    assert any(issue["code"] == "recording_hash_format_or_path_invalid" for issue in report["dataset_preflight"]["issues"])


def test_oversized_manifest_rejected_before_any_wav_or_model(tmp_path, monkeypatch):
    manifest = tmp_path / "large.jsonl"
    manifest.write_text("".join(json.dumps({"id": str(index)}) + "\n" for index in range(51)))
    monkeypatch.setattr(study, "_experiment", lambda: pytest.fail("Oversized scope must not load model"))
    report = study.run_study(manifest)
    assert report["status"] == "blocked_dataset" and report["analysis_calls"] == 0


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, -1, 1.1])
def test_invalid_scores_are_failed_not_successful_classifications(monkeypatch, value):
    install_doubles(monkeypatch, screener=ScreenerDouble([{"score": value, "verdict": "allow"}] * 250))
    report = study.run_study(Path("unused"))
    assert report["failed_analysis_calls"] == 250
    assert all(row["errors"] == 50 and row["false_alarm_rate_classified"] is None for row in report["evaluation_by_duration"])


@pytest.mark.parametrize("budget", [0, -1, 301, float("inf"), float("nan"), True])
def test_invalid_wall_budgets_fail_before_any_access(monkeypatch, budget):
    monkeypatch.setattr(study, "_prepare", lambda *_: pytest.fail("Invalid budget must not read data"))
    with pytest.raises(ValueError, match="300"):
        study.run_study(Path("unused"), max_wall_seconds=budget)


def test_cli_requires_manifest_for_execution_and_refuses_report_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(study, "run_study", lambda *_a, **_k: pytest.fail("Invalid CLI must not execute"))
    assert study.main(["--execute"]) == 2
    assert study.main(["--execute", "--plan", "--manifest", "missing"]) == 2
    target = tmp_path / "preserved.json"
    target.write_text("preserve this")
    assert study.main(["--execute", "--manifest", "missing", "--output", str(target)]) == 2
    assert target.read_text() == "preserve this"
