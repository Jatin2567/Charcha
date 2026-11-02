"""Collection checks use artificial WAV bytes; none are real accuracy evidence."""
import csv
import importlib.util
import json
from pathlib import Path
import socket
import wave

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("speech_collection_kit", ROOT / "scripts/prepare_speech_screening_kit.py")
kit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kit_module)


@pytest.fixture
def prompts():
    return kit_module.prompt_bank()


def read_rows(kit):
    with (kit / "checklist.csv").open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def write_rows(kit, rows):
    with (kit / "checklist.csv").open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=kit_module.FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_fixture(path, value=1, *, seconds=8, rate=16000):
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(value.to_bytes(2, "little", signed=True) * int(seconds * rate))


@pytest.fixture
def completed(tmp_path, prompts):
    kit = tmp_path / "work" / "kit"
    kit_module.prepare(kit, prompts, root=tmp_path)
    rows = read_rows(kit)
    for index, row in enumerate(rows, 1):
        row.update(collected="true", prompt_reviewed="true", consent="true",
                   confirmed_label=row["expected_label"], origin=kit_module.ROLES[row["role"]][2],
                   label_evidence=f"PRIVATE-PROVENANCE-{row['id']}",
                   speaker_group=f"group-{row['language']}-{row['role']}",
                   source_group=f"source-{row['id']}")
        if row["expected_label"] == "spoof":
            row.update(generator="fixture-generator", model_version="fixture-model-v1",
                       voice_id=f"stock-{row['language']}-{row['role']}", voice_is_cloned="false")
        write_fixture(kit / row["wav"], index)
    write_rows(kit, rows)
    return tmp_path, kit, rows


def test_plan_is_balanced_pending_and_does_not_contact_services(prompts, monkeypatch):
    def forbidden(*_a, **_k):
        raise AssertionError("Collection plan opened a socket")
    monkeypatch.setattr(socket, "socket", forbidden)
    plan = kit_module.build_plan(prompts)
    assert plan["source_clips"] == len(plan["slots"]) == 60
    assert plan["human_clips"] == plan["standard_ai_clips"] == 30
    assert plan["calibration_clips"] == plan["evaluation_clips"] == 30
    assert plan["provider_calls"] == plan["inference_calls"] == 0
    assert plan["accuracy"] is None and not plan["accuracy_preservation_proven"]
    assert plan["voice_cloning"] is False
    assert all(row["consent"] == row["collected"] == row["prompt_reviewed"] == "false" for row in plan["slots"])
    assert all(row["confirmed_label"] == row["origin"] == row["speaker_group"] == row["voice_is_cloned"] == "" for row in plan["slots"])
    for language in kit_module.LANGUAGES:
        language_rows = [row for row in plan["slots"] if row["language"] == language]
        assert len(language_rows) == 12
        assert {row["role"] for row in language_rows} == {"HA", "HB", "AA", "AB"}


def test_prompt_bank_requires_unique_native_review_drafts(tmp_path, prompts):
    broken = list(prompts)
    broken[0] = dict(broken[1])
    path = tmp_path / "prompts.json"
    path.write_text(json.dumps({"schema_version": 1, "prompts": broken}))
    with pytest.raises(ValueError, match="Duplicate"):
        kit_module.prompt_bank(path)


def test_prepare_creates_no_recordings_or_confirmed_labels_and_refuses_overwrite(tmp_path, prompts):
    kit = tmp_path / "work" / "new-kit"
    report = kit_module.prepare(kit, prompts, root=tmp_path)
    assert report["recordings_created"] == report["labels_confirmed"] == report["consent_confirmed"] == 0
    assert sorted(path.name for path in kit.iterdir()) == ["checklist.csv", "collection-plan.json", "manifest.pending.jsonl", "originals", "private-provenance", "recordings"]
    assert not list((kit / "recordings").iterdir())
    pending = [json.loads(line) for line in (kit / "manifest.pending.jsonl").read_text().splitlines()]
    assert len(pending) == 60 and all(row["consent"] is False for row in pending)
    assert {row["condition"] for row in pending} == {"clean_direct"}
    assert all(row["speaker_group"] == row["source_group"] == row["label_evidence"] == "" for row in pending)
    original = (kit / "checklist.csv").read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        kit_module.prepare(kit, prompts, root=tmp_path)
    assert (kit / "checklist.csv").read_bytes() == original


@pytest.mark.parametrize("relative", ["outside", "work", "work/../outside"])
def test_output_paths_stay_strictly_inside_ignored_work(tmp_path, prompts, relative):
    with pytest.raises(ValueError):
        kit_module.prepare(tmp_path / relative, prompts, root=tmp_path)
    assert not (tmp_path / "outside").exists()


def test_symlink_collection_destination_is_rejected(tmp_path):
    work = tmp_path / "work"
    outside = tmp_path / "outside"
    work.mkdir()
    outside.mkdir()
    try:
        (work / "alias").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("This Windows account cannot create symlinks")
    with pytest.raises(ValueError):
        kit_module.confined(work / "alias" / "kit", tmp_path)


def test_empty_kit_is_blocked_without_loading_dataset_or_classifier(tmp_path, prompts, monkeypatch):
    kit = tmp_path / "work" / "empty"
    kit_module.prepare(kit, prompts, root=tmp_path)
    monkeypatch.setattr(kit_module, "_validate_existing_manifest", lambda *_: pytest.fail("Dataset/model imported before evidence was complete"))
    report = kit_module.check(kit, prompts, root=tmp_path, manifest_output=kit / "accepted.jsonl")
    assert report["ready_for_scoring"] is False
    assert report["readable_compatible_recordings"] == 0
    assert report["inference_calls"] == report["provider_calls"] == 0
    assert report["accuracy"] is None
    assert not (kit / "accepted.jsonl").exists()
    assert "recording_missing_invalid_or_escaped" in {row["code"] for row in report["issues"]}


def test_fully_declared_test_fixtures_export_manifest_after_global_checks(completed, prompts):
    root, kit, rows = completed
    output = root / "work" / "checked" / "manifest.jsonl"
    report = kit_module.check(kit, prompts, root=root, manifest_output=output)
    assert report["ready_for_scoring"] and report["manifest_written"]
    assert report["readable_compatible_recordings"] == 60
    assert report["accuracy"] is None and report["inference_calls"] == 0
    assert "PRIVATE-PROVENANCE" not in json.dumps(report)
    assert "group-hi" not in json.dumps(report)
    manifest = [json.loads(line) for line in output.read_text().splitlines()]
    assert len(manifest) == 60
    assert all(row["consent"] is True and row["fixture"] is False for row in manifest)
    assert all(Path(row["wav"]).is_absolute() for row in manifest)
    with pytest.raises(ValueError, match="already exists"):
        kit_module.check(kit, prompts, root=root, manifest_output=output)


@pytest.mark.parametrize("field,value,code", [
    ("consent", "false", "consent_not_confirmed"),
    ("prompt_reviewed", "false", "prompt_reviewed_not_confirmed"),
    ("confirmed_label", "", "independent_origin_or_label_not_confirmed"),
    ("label_evidence", "", "label_evidence_missing_or_invalid"),
    ("wav", "../private.wav", "planned_slot_metadata_changed"),
])
def test_missing_evidence_or_slot_tampering_never_exports(completed, prompts, field, value, code):
    root, kit, rows = completed
    rows[0][field] = value
    write_rows(kit, rows)
    report = kit_module.check(kit, prompts, root=root, manifest_output=kit / "accepted.jsonl")
    assert not report["ready_for_scoring"] and not report["manifest_written"]
    assert code in {row["code"] for row in report["issues"]}
    assert not (kit / "accepted.jsonl").exists()


def test_clone_and_unknown_stock_voice_provenance_are_rejected(completed, prompts):
    root, kit, rows = completed
    ai = next(row for row in rows if row["role"] == "AA")
    ai.update(voice_is_cloned="true", model_version="")
    write_rows(kit, rows)
    report = kit_module.check(kit, prompts, root=root)
    assert not report["ready_for_scoring"]
    assert {"cloned_voice_outside_this_collection", "noncloned_stock_voice_not_confirmed", "model_version_missing_or_invalid"} <= {row["code"] for row in report["issues"]}


def test_shared_human_identity_cannot_cross_calibration_and_evaluation(completed, prompts):
    root, kit, rows = completed
    for row in rows:
        if row["language"] == "hi" and row["role"] == "HB":
            row["speaker_group"] = "group-hi-HA"
    write_rows(kit, rows)
    report = kit_module.check(kit, prompts, root=root)
    assert not report["ready_for_scoring"]
    assert "speaker_group_crosses_splits" in {row["code"] for row in report["issues"]}
    assert "group-hi-HA" not in json.dumps(report)


def test_stock_voice_identity_cannot_hide_split_leakage_with_new_group(completed, prompts):
    root, kit, rows = completed
    for row in rows:
        if row["language"] == "hi" and row["role"] == "AB":
            row["voice_id"] = "stock-hi-AA"
    write_rows(kit, rows)
    report = kit_module.check(kit, prompts, root=root)
    assert not report["ready_for_scoring"]
    assert "stock_voice_identity_crosses_splits" in {row["code"] for row in report["issues"]}


def test_duplicate_audio_is_detected_despite_separate_source_ids(completed, prompts):
    root, kit, rows = completed
    (kit / rows[1]["wav"]).write_bytes((kit / rows[0]["wav"]).read_bytes())
    report = kit_module.check(kit, prompts, root=root)
    assert not report["ready_for_scoring"]
    assert "duplicate_audio" in {row["code"] for row in report["issues"]}


@pytest.mark.parametrize("seconds,rate,code", [
    (7.9, 16000, "recording_must_be_eight_to_twenty_seconds"),
    (20.1, 16000, "recording_must_be_eight_to_twenty_seconds"),
    (8, 48000, "recording_missing_invalid_or_escaped"),
])
def test_collection_duration_and_pcm_format_are_checked(completed, prompts, seconds, rate, code):
    root, kit, rows = completed
    write_fixture(kit / rows[0]["wav"], seconds=seconds, rate=rate)
    report = kit_module.check(kit, prompts, root=root)
    assert not report["ready_for_scoring"]
    assert code in {row["code"] for row in report["issues"]}


def test_spreadsheet_formula_prefix_is_never_executable():
    assert kit_module.csv_safe("=HYPERLINK('unsafe')").startswith("'=")
    assert kit_module.csv_safe("  +SUM(1,2)").startswith("'  +")
