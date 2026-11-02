import importlib.util
import json
from pathlib import Path

import pytest

from conftest import make_wav

spec = importlib.util.spec_from_file_location(
    "screening_dataset", Path(__file__).resolve().parents[2] / "evaluation/audio_screening.py",
)
dataset = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dataset)


def manifest(tmp_path, patches=None):
    rows = []
    for index, label in enumerate(("genuine", "spoof")):
        wav = tmp_path / f"private-recording-{index}.wav"
        # Distinct generated unit fixtures exercise metadata, never detector accuracy.
        wav.write_bytes(make_wav(seconds=4.1 + index / 10, rate=16000))
        rows.append({
            "id": f"private-id-{index}", "wav": str(wav), "label": label,
            "fixture": False, "consent": True, "split": "evaluation",
            "speaker_group": f"private-speaker-{index}", "source_group": f"private-source-{index}",
            "label_evidence": "private consent and label log", "language": "hi", "condition": "clean",
            **((patches or {}).get(index, {})),
        })
    path = tmp_path / "manifest.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def test_preflight_checks_format_not_accuracy_or_identity(tmp_path):
    result = dataset.validate_dataset(manifest(tmp_path))
    assert result["ready_for_scoring"] is True
    assert result["accuracy"] is None
    assert result["inference_calls"] == result["provider_calls"] == 0
    assert result["split_label_counts"] == {"evaluation": {"genuine": 1, "spoof": 1}}
    assert "private-" not in json.dumps(result)


def test_consent_and_independent_evidence_are_required(tmp_path):
    result = dataset.validate_dataset(manifest(tmp_path, {0: {"consent": False, "label_evidence": ""}}))
    assert result["ready_for_scoring"] is False
    assert {i["code"] for i in result["issues"]} == {"consent_not_confirmed", "independent_label_evidence_missing"}


@pytest.mark.parametrize("field", ["speaker_group", "source_group"])
def test_shared_identity_or_generator_cannot_cross_splits(tmp_path, field):
    result = dataset.validate_dataset(manifest(tmp_path, {
        0: {"split": "calibration", field: "same"}, 1: {field: "same"},
    }))
    issue = next(i for i in result["issues"] if i["code"] == field + "_crosses_splits")
    assert issue == {"row": 2, "code": field + "_crosses_splits", "related_row": 1}
    assert result["ready_for_scoring"] is False


def test_duplicate_decoded_audio_is_rejected_even_with_distinct_names(tmp_path):
    path = manifest(tmp_path)
    (tmp_path / "private-recording-1.wav").write_bytes((tmp_path / "private-recording-0.wav").read_bytes())
    result = dataset.validate_dataset(path)
    assert {"row": 2, "code": "duplicate_audio", "related_row": 1} in result["issues"]


def test_invalid_types_short_audio_and_missing_files_are_not_hidden(tmp_path):
    path = manifest(tmp_path, {0: {"label": [], "split": {}, "fixture": "false"}, 1: {"wav": None}})
    (tmp_path / "private-recording-0.wav").write_bytes(make_wav(seconds=1, rate=16000))
    result = dataset.validate_dataset(path)
    codes = {i["code"] for i in result["issues"]}
    assert {"not_labelled_nonfixture_speech", "shorter_than_detector_window", "split_missing_or_invalid",
            "recording_unavailable_or_invalid", "evaluation_missing_genuine"} <= codes


@pytest.mark.parametrize("content", ['[]\n', 'null\n', '7\n', '"row"\n'])
def test_manifest_requires_recording_objects(tmp_path, content):
    path = tmp_path / "bad.jsonl"
    path.write_text(content)
    with pytest.raises(ValueError, match="objects"):
        dataset.validate_dataset(path)


def test_validate_only_does_not_load_model_and_exports_no_private_metadata(tmp_path, monkeypatch):
    path = manifest(tmp_path)
    monkeypatch.setattr(dataset, "LocalAudioScreener", lambda *_: pytest.fail("Model must not load"))
    monkeypatch.setattr("sys.argv", ["screening", "--manifest", str(path), "--validate-only",
                                    "--output-dir", str(tmp_path / "out")])
    assert dataset.main() == 0
    report = (tmp_path / "out/dataset-preflight.json").read_text()
    assert "private-" not in report


def test_strict_failure_stops_before_inference(tmp_path, monkeypatch):
    path = manifest(tmp_path, {0: {"consent": False}})
    monkeypatch.setattr(dataset, "LocalAudioScreener", lambda *_: pytest.fail("Model must not load"))
    monkeypatch.setattr("sys.argv", ["screening", "--manifest", str(path), "--strict-manifest",
                                    "--output-dir", str(tmp_path / "out")])
    assert dataset.main() == 2


@pytest.mark.parametrize("field,value", [("label", []), ("split", {}), ("condition", 2), ("language", []), ("fixture", "false")])
def test_bad_metadata_stops_default_run_before_loading_model(tmp_path, monkeypatch, capsys, field, value):
    path = manifest(tmp_path, {0: {field: value}})
    monkeypatch.setattr(dataset, "LocalAudioScreener", lambda *_: pytest.fail("Model must not load"))
    monkeypatch.setattr("sys.argv", ["screening", "--manifest", str(path)])
    with pytest.raises(SystemExit) as error:
        dataset.main()
    assert error.value.code == 2
    assert "private-" not in capsys.readouterr().err


def test_headline_uses_evaluation_not_good_calibration_score(tmp_path, monkeypatch, capsys):
    path = manifest(tmp_path)
    common = {"label": "genuine", "fixture": False, "status": "complete", "compute_ms": 1,
              "language": "hi", "condition": "clean"}
    monkeypatch.setattr(dataset, "evaluate", lambda *_: [
        {**common, "split": "calibration", "verdict": "allow"},
        {**common, "split": "evaluation", "verdict": "suspicious"},
    ])
    class Stub:
        def status(self):
            return {"fixture": True}
    monkeypatch.setattr(dataset, "LocalAudioScreener", lambda *_: Stub())
    monkeypatch.setattr("sys.argv", ["screening", "--manifest", str(path), "--strict-manifest",
                                    "--output-dir", str(tmp_path / "out")])
    dataset.main()
    printed = json.loads(capsys.readouterr().out)
    assert printed["scope"] == "held_out_evaluation"
    assert printed["summary"]["accuracy_classified_only"] == 0
    report = json.loads((tmp_path / "out/summary.json").read_text())
    assert report["overall"]["accuracy_classified_only"] == .5
    assert report["headline"]["accuracy_classified_only"] == 0
