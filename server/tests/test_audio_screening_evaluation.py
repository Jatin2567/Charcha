from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[2] / "evaluation" / "audio_screening.py"
spec = importlib.util.spec_from_file_location("audio_screening_evaluation", PATH)
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


def row(label, verdict, *, fixture=False, **extra):
    return {"label": label, "verdict": verdict, "fixture": fixture,
            "status": "complete", "compute_ms": 5, **extra}


def test_no_accuracy_from_signal_fixtures_or_unlabelled():
    result = evaluation.summarize([
        row("genuine", "allow", fixture=True), row("unlabelled", "suspicious"),
    ])
    assert result["accuracy_classified_only"] is None
    assert result["coverage"] is None
    assert result["labelled_nonfixture"] == 0
    assert result["excluded_fixture_or_unlabelled"] == 2


def test_unknowns_are_visible_not_counted_as_correct_predictions():
    result = evaluation.summarize([
        row("genuine", "allow"), row("genuine", "suspicious"),
        row("spoof", "allow"), row("spoof", "suspicious"),
        row("genuine", "unknown"), row("spoof", "unknown"),
    ])
    assert result["coverage"] == pytest.approx(4 / 6)
    assert result["accuracy_classified_only"] == .5
    assert result["unknown_genuine"] == result["unknown_spoof"] == 1
    assert result["false_alarm_rate_classified"] == .5
    assert result["miss_rate_classified"] == .5
    assert result["confusion"] == {
        "genuine_allowed": 1, "false_alarms": 1, "spoof_flagged": 1, "spoof_missed": 1,
    }


def test_errors_do_not_appear_as_missed_or_correct_detections():
    result = evaluation.summarize([row("spoof", "allow", status="error"),
                                   row("genuine", "unknown", compute_ms=float("nan"))])
    assert result["errors"] == 1
    assert result["confusion"]["spoof_missed"] == 0
    assert result["accuracy_classified_only"] is None
    assert result["compute_p50_ms"] is None


def test_balanced_accuracy_requires_both_classes():
    result = evaluation.summarize([row("genuine", "allow")])
    assert result["balanced_accuracy_classified_only"] is None


def test_failed_recordings_reduce_all_labelled_coverage():
    result = evaluation.summarize([
        row("genuine", "allow"), row("spoof", "unknown"),
        row("genuine", "unknown", status="error"), row("spoof", "unknown", status="error"),
    ])
    assert result["labelled_total"] == 4
    assert result["labelled_errors"] == 2
    assert result["classification_coverage_all_labelled"] == .25
    assert result["coverage_of_successfully_analyzed"] == .5


def test_manifest_errors_do_not_disclose_local_paths(tmp_path):
    manifest = tmp_path / "recordings.jsonl"
    manifest.write_text('{"id":"private","wav":"private.wav","label":"genuine","fixture":false}\n')
    screener = evaluation.LocalAudioScreener(tmp_path / "absent.onnx")
    result = evaluation.evaluate(manifest, screener)
    assert result[0]["error"] == "recording_unavailable_or_invalid"
    assert "wav" not in result[0]


def test_duplicate_ids_are_rejected(tmp_path):
    manifest = tmp_path / "recordings.jsonl"
    manifest.write_text('{"id":"a","wav":"a.wav"}\n' * 2)
    with pytest.raises(ValueError, match="unique"):
        evaluation.evaluate(manifest, evaluation.LocalAudioScreener(tmp_path / "absent"))
