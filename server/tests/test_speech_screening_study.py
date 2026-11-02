"""Runner unit tests use fabricated PCM/model doubles, never a real speech corpus."""
import importlib.util
import json
import os
from pathlib import Path
import socket
from types import SimpleNamespace

import pytest

from conftest import make_wav

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("speech_screening_study", ROOT / "scripts/run_speech_screening_study.py")
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)


class ScreenerDouble:
    def __init__(self, outputs=None, ready=True):
        self.outputs = iter(outputs) if outputs else None
        self.inputs = []
        self.ready = ready

    def status(self):
        return {"ready": self.ready, "id": "unit-test-double", "sha256": "test-only-not-a-model",
                "cpu_threads": 2, "private_path": "never-export-this-path"}

    def analyze(self, pcm, rate):
        self.inputs.append((pcm, rate))
        output = next(self.outputs) if self.outputs else {"score": .1, "verdict": "allow"}
        if isinstance(output, Exception):
            raise output
        return SimpleNamespace(as_dict=lambda: {"compute_ms": 2.5, "windows_analyzed": 1, **output})


def fake_prepared(count=60):
    """No speech/accuracy evidence: distinct bytes solely exercise runner bounds."""
    recordings, metadata = [], {}
    for index in range(count):
        language = study.LANGUAGES[index // 12 % 5]
        split = "calibration" if index % 12 < 6 else "evaluation"
        label = "genuine" if index % 6 < 3 else "spoof"
        identifier = f"recording-{index + 1:03d}"
        recordings.append({"id": identifier, "pcm": index.to_bytes(2, "little") * 128000,
                           "fixture": False, "language": language, "split": split,
                           "label": label, "condition": "condition-001"})
        metadata[identifier] = {"speaker_group": f"private-speaker-{language}-{split}-{label}",
                                "source_group": f"private-source-{language}-{split}-{label}"}
    return {"ready_for_scoring": True, "issues": []}, recordings, metadata


def install_doubles(monkeypatch, *, screener=None, prepared=None):
    experiment = study._experiment()
    screener = screener or ScreenerDouble()
    loads = []
    def factory(model, **kwargs):
        loads.append((model, kwargs))
        return screener
    monkeypatch.setattr(experiment, "_runtime", lambda: (factory, None))
    monkeypatch.setattr(study, "_experiment", lambda: experiment)
    monkeypatch.setattr(study, "_prepare", lambda *_: prepared or fake_prepared())
    return experiment, screener, loads


def test_default_plan_never_touches_model_manifest_network_or_provider_environment(monkeypatch, capsys):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Default plan performed data or model access")
    class NoProviderEnvironment(dict):
        def get(self, key, default=None):
            return default if key in {"LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"} else forbidden()
        __getitem__ = forbidden
    with monkeypatch.context() as context:
        context.setattr(study, "_experiment", forbidden)
        context.setattr(study, "run_study", forbidden)
        context.setattr(socket, "socket", forbidden)
        context.setattr(os, "environ", NoProviderEnvironment())
        assert study.main(["--manifest", "missing-private-manifest.jsonl"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["plan_only"] is True
    assert result["provider_calls"] == result["analysis_calls"] == result["inference_calls"] == 0
    assert result["maximum_source_recordings"] == 60 and result["maximum_analysis_calls"] == 300
    assert result["live_activation"] is result["voice_cloning"] is False


def test_sixty_sources_are_paired_in_twelve_bounded_batches_with_one_two_thread_model(monkeypatch):
    experiment, screener, loads = install_doubles(monkeypatch)
    result = study.run_study(Path("unused"))
    assert result["status"] == "labelled_exploratory_pilot_complete"
    assert len(loads) == 1 and loads[0][1] == {"cpu_threads": 2}
    assert result["batch_count"] == 12
    assert result["analysis_calls"] == result["successfully_scored_model_windows"] == 300
    assert result["unattempted_analysis_calls"] == result["failed_analysis_calls"] == 0
    assert result["inference_calls"] is None
    assert len(screener.inputs) == 300 and all(len(pcm) == 64600 * 2 and rate == 16000 for pcm, rate in screener.inputs)
    assert {row["id"] for row in result["results"]} == {f"recording-{i:03d}" for i in range(1, 61)}
    assert [row["observed_audio_ms"] for row in result["results"][:5]] == [500, 1000, 2000, 3000, 4037.5]
    assert result["model"]["sha256"] == "test-only-not-a-model"
    assert result["accuracy"] is None and result["accuracy_preservation_proven"] is False
    assert result["live_activation"] is result["affects_live_screening"] is False
    exported = json.dumps(result)
    assert "private-" not in exported and "never-export" not in exported and '"pcm"' not in exported
    for candidate in result["evaluation_by_duration"]:
        assert candidate["source_recordings"] == 30
        for language in study.LANGUAGES:
            metric = candidate["by_language"][language]
            assert metric["genuine_recordings"] == metric["spoof_recordings"] == 3
            assert metric["distinct_declared_speaker_groups"] == metric["distinct_declared_source_groups"] == 2
            assert metric["genuine_distinct_declared_speaker_groups"] == metric["spoof_distinct_declared_source_groups"] == 1
    assert all(row["source_recordings"] == 30 for row in result["calibration_by_duration"])


def test_native_baseline_and_prefixes_never_read_whole_recording_or_later_tail(monkeypatch):
    preflight, recordings, metadata = fake_prepared()
    first = bytes(range(256)) * 505  # 64640 samples; deliberately irregular prefix.
    recordings[0]["pcm"] = first + b"\x7f\x7f" * 100000
    experiment, screener, _ = install_doubles(monkeypatch, prepared=(preflight, recordings, metadata))
    study.run_study(Path("unused"))
    assert screener.inputs[0][0] == first[:64600 * 2]
    for offset, samples in enumerate((64600, 8000, 16000, 32000, 48000)):
        assert screener.inputs[offset][0] == experiment.tiled_prefix(recordings[0]["pcm"], samples)


def test_unknowns_and_errors_are_retained_with_denominators_not_made_correct(monkeypatch):
    outputs = []
    for index in range(60):
        evaluation = index % 12 >= 6
        if evaluation:
            output = {"score": None, "verdict": "unknown"} if index % 6 < 3 else RuntimeError("private-failure-path")
        else:
            output = {"score": .1, "verdict": "allow"} if index % 6 < 3 else {"score": .9, "verdict": "suspicious"}
        outputs.extend([output] * 5)
    _, _, _ = install_doubles(monkeypatch, screener=ScreenerDouble(outputs))
    result = study.run_study(Path("unused"))
    assert result["failed_analysis_calls"] == 75
    assert result["successfully_scored_model_windows"] == 225
    for metric in result["evaluation_by_duration"]:
        assert metric["source_recordings"] == 30 and metric["classified"] == 0
        assert metric["unknown"] == metric["errors"] == 15
        assert metric["unknown_genuine"] == metric["spoof_errors"] == 15
        assert metric["unknown_spoof"] == metric["genuine_errors"] == 0
        assert metric["classification_coverage"] == 0
        assert metric["false_alarm_rate_classified"] is metric["miss_rate_classified"] is None
        assert "accuracy_classified_only" not in metric
    assert all(metric["classified"] == 30 for metric in result["calibration_by_duration"])
    assert "private-failure" not in json.dumps(result)


def test_wall_budget_stops_admitting_calls_and_preserves_failures_and_unattempted(monkeypatch):
    current = [0.0]
    screener = ScreenerDouble([RuntimeError("private-error"), {"score": .1, "verdict": "allow"}])
    original = screener.analyze
    def delayed(pcm, rate):
        current[0] += .6
        return original(pcm, rate)
    screener.analyze = delayed
    install_doubles(monkeypatch, screener=screener)
    result = study.run_study(Path("unused"), max_wall_seconds=1, clock=lambda: current[0])
    assert result["status"] == "stopped_wall_budget"
    assert result["analysis_calls"] == 2 and result["failed_analysis_calls"] == 1
    assert result["unattempted_analysis_calls"] == 298
    assert result["wall_seconds"] == 1.2
    assert result["evaluation_by_duration"][0]["unattempted"] == 30


def test_expired_preflight_budget_never_initializes_model(monkeypatch):
    current = [0.0]
    _, screener, loads = install_doubles(monkeypatch)
    def prepare(*_):
        current[0] = 2
        return fake_prepared()
    monkeypatch.setattr(study, "_prepare", prepare)
    result = study.run_study(Path("unused"), max_wall_seconds=1, clock=lambda: current[0])
    assert loads == [] and screener.inputs == []
    assert result["analysis_calls"] == 0 and result["unattempted_analysis_calls"] == 300


def test_missing_model_and_failed_model_setup_leave_every_row_unattempted(monkeypatch):
    _, screener, loads = install_doubles(monkeypatch, screener=ScreenerDouble(ready=False))
    result = study.run_study(Path("unused"))
    assert len(loads) == 1 and screener.inputs == []
    assert result["status"] == "blocked_model_unavailable"
    assert result["analysis_calls"] == 0 and result["unattempted_analysis_calls"] == 300


def write_manifest(tmp_path, *, count=10, mutation=None):
    rows = []
    for index in range(count):
        label = "genuine" if index % 2 == 0 else "spoof"
        row = {"id": f"private-id-{index}", "wav": f"private-recording-{index}.wav",
               "language": study.LANGUAGES[index // 2 % 5], "condition": "private-condition",
               "split": "evaluation", "label": label, "fixture": False, "consent": True,
               "label_evidence": "private declared source evidence", "speaker_group": f"private-speaker-{index}",
               "source_group": f"private-source-{index}"}
        if mutation:
            mutation(row, index)
        # Different durations prevent duplicate fingerprints; these are fabricated WAV fixtures.
        (tmp_path / row["wav"]).write_bytes(make_wav(seconds=4.1 + index / 100, rate=16000))
        rows.append(row)
    path = tmp_path / "private-manifest.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


@pytest.mark.parametrize("missing", ["consent", "label_evidence", "speaker_group", "source_group", "label", "wav"])
def test_missing_evidence_or_corpus_fails_entire_study_before_model(tmp_path, monkeypatch, missing):
    manifest = write_manifest(tmp_path)
    rows = [json.loads(line) for line in manifest.read_text().splitlines()]
    rows[-1].pop(missing)
    manifest.write_text("".join(json.dumps(row) + "\n" for row in rows))
    experiment = study._experiment()
    monkeypatch.setattr(experiment, "_runtime", lambda: pytest.fail("Invalid study must not initialize model or decode selected inputs"))
    monkeypatch.setattr(study, "_experiment", lambda: experiment)
    result = study.run_study(manifest)
    assert result["status"] == "blocked_dataset" and result["analysis_calls"] == 0
    assert "private-" not in json.dumps(result)


def test_missing_language_class_fails_before_model(tmp_path, monkeypatch):
    manifest = write_manifest(tmp_path, mutation=lambda row, index: row.update(label="genuine") if index == 9 else None)
    experiment = study._experiment()
    monkeypatch.setattr(experiment, "_runtime", lambda: pytest.fail("Incomplete language coverage must block model"))
    monkeypatch.setattr(study, "_experiment", lambda: experiment)
    result = study.run_study(manifest)
    assert result["status"] == "blocked_dataset"
    assert any(issue["code"] == "study_evaluation_missing_mr_spoof" for issue in result["dataset_preflight"]["issues"])


def test_cross_split_identity_in_any_recording_blocks_the_entire_study(tmp_path, monkeypatch):
    manifest = write_manifest(tmp_path, count=11)
    rows = [json.loads(line) for line in manifest.read_text().splitlines()]
    rows[-1].update(split="calibration", speaker_group=rows[0]["speaker_group"])
    manifest.write_text("".join(json.dumps(row) + "\n" for row in rows))
    experiment = study._experiment()
    monkeypatch.setattr(experiment, "_runtime", lambda: pytest.fail("Split leakage must block model"))
    monkeypatch.setattr(study, "_experiment", lambda: experiment)
    result = study.run_study(manifest)
    assert result["status"] == "blocked_dataset" and result["analysis_calls"] == 0
    assert any(issue["code"] == "speaker_group_crosses_splits" for issue in result["dataset_preflight"]["issues"])


def test_sixty_recording_scope_limit_checked_before_audio_or_model(tmp_path, monkeypatch):
    manifest = tmp_path / "oversized.jsonl"
    manifest.write_text("".join(json.dumps({"id": f"item-{index}"}) + "\n" for index in range(61)))
    experiment = study._experiment()
    dataset = experiment._dataset()
    monkeypatch.setattr(dataset, "validate_dataset", lambda *_: pytest.fail("Oversized scope must not read audio"))
    monkeypatch.setattr(experiment, "_dataset", lambda: dataset)
    monkeypatch.setattr(experiment, "_runtime", lambda: pytest.fail("Must not load model"))
    monkeypatch.setattr(study, "_experiment", lambda: experiment)
    result = study.run_study(manifest)
    assert result["status"] == "blocked_dataset"
    assert result["dataset_preflight"]["issues"][0]["code"] == "study_exceeds_sixty_recordings"


def test_prepare_retains_global_anonymous_ids_and_exports_only_anonymous_conditions(tmp_path):
    manifest = write_manifest(tmp_path)
    preflight, recordings, metadata = study._prepare(manifest, study._experiment())
    assert preflight["ready_for_scoring"] is True
    assert [row["id"] for row in recordings] == [f"recording-{i:03d}" for i in range(1, 11)]
    assert {row["condition"] for row in recordings} == {"condition-001"}
    assert all(row["source_group"].startswith("private-") for row in metadata.values())
    assert "private-" not in json.dumps([{key: value for key, value in row.items() if key != "pcm"} for row in recordings])


def test_actual_collection_kit_schema_is_accepted_with_fabricated_wavs_and_no_real_inference(tmp_path, monkeypatch):
    kit_spec = importlib.util.spec_from_file_location("study_collection_kit", ROOT / "scripts/prepare_speech_screening_kit.py")
    kit = importlib.util.module_from_spec(kit_spec)
    kit_spec.loader.exec_module(kit)
    slots = kit.slots(kit.prompt_bank())
    rows = []
    for index, slot in enumerate(slots):
        row = kit._pending(slot)
        # These declarations and tones only test schema compatibility. They do
        # not establish genuine/spoof speech labels or human consent evidence.
        row.update(consent=True, label_evidence="UNIT TEST fabricated tone fixture, not speech evidence",
                   speaker_group=f"unit-only-{slot['language']}-{slot['role']}",
                   source_group=f"unit-only-source-{slot['language']}-{slot['role']}")
        path = tmp_path / row["wav"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(make_wav(seconds=8 + index / 100, rate=16000))
        rows.append(row)
    manifest = tmp_path / "unit-test-kit-manifest.jsonl"
    manifest.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    experiment = study._experiment()
    _, decoder = experiment._runtime()
    screener, loads = ScreenerDouble(), []
    def factory(model, **kwargs):
        loads.append(kwargs)
        return screener
    monkeypatch.setattr(experiment, "_runtime", lambda: (factory, decoder))
    monkeypatch.setattr(study, "_experiment", lambda: experiment)
    result = study.run_study(manifest)
    assert result["dataset_preflight"]["ready_for_scoring"] is True
    assert loads == [{"cpu_threads": 2}]
    assert result["source_recording_count"] == 60 and result["analysis_calls"] == 300
    assert result["accuracy"] is None and result["accuracy_preservation_proven"] is False
    assert "unit-only" not in json.dumps(result)


def test_sparse_condition_classes_report_null_absent_class_rates_instead_of_blocking(tmp_path, monkeypatch):
    manifest = write_manifest(tmp_path, mutation=lambda row, index: row.update(condition="human-direct" if index % 2 == 0 else "ai-direct"))
    experiment = study._experiment()
    _, decoder = experiment._runtime()
    screener = ScreenerDouble()
    monkeypatch.setattr(experiment, "_runtime", lambda: (lambda *_a, **_k: screener, decoder))
    monkeypatch.setattr(study, "_experiment", lambda: experiment)
    result = study.run_study(manifest)
    assert result["status"] == "labelled_exploratory_pilot_complete"
    for candidate in result["evaluation_by_duration"]:
        assert len(candidate["by_condition"]) == 2
        genuine_condition, spoof_condition = candidate["by_condition"].values()
        assert genuine_condition["spoof_recordings"] == 0 and genuine_condition["miss_rate_classified"] is None
        assert spoof_condition["genuine_recordings"] == 0 and spoof_condition["false_alarm_rate_classified"] is None


@pytest.mark.parametrize("budget", [0, -1, 301, float("inf"), float("nan"), True])
def test_invalid_wall_budgets_fail_before_access(monkeypatch, budget):
    monkeypatch.setattr(study, "_experiment", lambda: pytest.fail("Invalid budget must fail before any access"))
    with pytest.raises(ValueError, match="300"):
        study.run_study(Path("unused"), max_wall_seconds=budget)


def test_existing_report_refused_before_any_work(tmp_path, monkeypatch):
    target = tmp_path / "existing.json"
    target.write_text("keep this")
    monkeypatch.setattr(study, "run_study", lambda *_a, **_k: pytest.fail("No overwrite or inference"))
    assert study.main(["--manifest", "missing", "--execute", "--output", str(target)]) == 2
    assert target.read_text() == "keep this"


def test_execute_requires_manifest_and_cannot_mix_plan(monkeypatch):
    monkeypatch.setattr(study, "run_study", lambda *_a, **_k: pytest.fail("Invalid CLI should not run"))
    assert study.main(["--execute"]) == 2
    assert study.main(["--execute", "--plan", "--manifest", "missing"]) == 2
