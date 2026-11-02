"""Prepare/check a local 60-clip speech collection kit; never record or infer.

The checklist contains intended slots, not established labels or consent. All
actual evidence is supplied by the owner; successful checks verify declarations
and audio format, not identity, consent validity or representative accuracy.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import wave

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "evaluation" / "speech_collection_prompts.json"
LANGUAGES = ("hi", "ta", "bn", "te", "mr")
ROLES = {"HA": ("calibration", "genuine", "live_microphone"),
         "HB": ("evaluation", "genuine", "live_microphone"),
         "AA": ("calibration", "spoof", "standard_tts"),
         "AB": ("evaluation", "spoof", "standard_tts")}
FIELDS = ("id", "wav", "language", "role", "split", "prompt_id", "expected_label",
          "prompt_text", "expected_meaning_en", "collected", "prompt_reviewed",
          "confirmed_label", "origin", "consent", "label_evidence", "speaker_group",
          "source_group", "generator", "model_version", "voice_id", "voice_is_cloned")
IMMUTABLE = ("id", "wav", "language", "role", "split", "prompt_id", "expected_label",
             "prompt_text", "expected_meaning_en")


def csv_safe(value: object) -> str:
    text = str(value)
    return "'" + text if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")) else text


def prompt_bank(path: Path = PROMPTS) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("prompts")
    if data.get("schema_version") != 1 or not isinstance(rows, list) or len(rows) != 30:
        raise ValueError("Expected the reviewed 30-prompt collection bank")
    keys = set()
    for row in rows:
        language, prompt_id = row.get("language"), row.get("id")
        if language not in LANGUAGES or prompt_id not in {"C01", "C02", "C03", "E01", "E02", "E03"}:
            raise ValueError("Invalid prompt identity")
        key = (language, prompt_id)
        if key in keys:
            raise ValueError("Duplicate prompt identity")
        keys.add(key)
        expected_split = "calibration" if prompt_id.startswith("C") else "evaluation"
        if row.get("split") != expected_split:
            raise ValueError("Prompt split does not match its identity")
        for field in ("text", "expected_meaning_en"):
            if not isinstance(row.get(field), str) or not 1 <= len(row[field]) <= 4000:
                raise ValueError("Prompt text/meaning is missing or oversized")
        if row.get("review_status") != "native_speaker_review_required":
            raise ValueError("Prompt bank must retain the native-review requirement")
    return rows


def slots(prompts: list[dict]) -> list[dict]:
    by_key = {(row["language"], row["id"]): row for row in prompts}
    result = []
    for language in LANGUAGES:
        for role, (split, label, _origin) in ROLES.items():
            for number in range(1, 4):
                prompt_id = f"{'C' if split == 'calibration' else 'E'}{number:02d}"
                prompt = by_key[(language, prompt_id)]
                identifier = f"{language}_{role}_{prompt_id}"
                row = dict.fromkeys(FIELDS, "")
                row.update(id=identifier, wav=f"recordings/{identifier}.wav", language=language,
                           role=role, split=split, prompt_id=prompt_id, expected_label=label,
                           prompt_text=prompt["text"], expected_meaning_en=prompt["expected_meaning_en"],
                           collected="false", prompt_reviewed="false", consent="false")
                result.append(row)
    return result


def build_plan(prompts: list[dict]) -> dict:
    return {"schema_version": 1, "record_type": "speech_collection_pilot", "plan_only": True,
            "languages": list(LANGUAGES), "source_clips": 60, "human_clips": 30,
            "standard_ai_clips": 30, "calibration_clips": 30, "evaluation_clips": 30,
            "clips_per_language": 12, "human_identities_per_language": 2,
            "stock_ai_voice_identities_per_language": 2,
            "format": {"container": "WAV", "sample_rate": 16000, "channels": 1,
                       "pcm_bits": 16, "minimum_seconds": 8, "maximum_seconds": 20,
                       "target_seconds": [8, 15]},
            "speaker_rule": "A roles are calibration; B roles are evaluation. The same actual person or stock AI voice must keep one stable anonymous group and one split across all languages.",
            "evidence_rule": "An intended slot is not ground truth; confirm live microphone or non-cloned standard TTS origin independently before labelling.",
            "accuracy": None, "accuracy_preservation_proven": False,
            "provider_calls": 0, "inference_calls": 0, "voice_cloning": False,
            "note": "60 source clips are a collection/debugging pilot, not sufficient representative accuracy or short-window non-inferiority evidence.",
            "slots": slots(prompts)}


def _link(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def confined(path: Path, root: Path = ROOT) -> Path:
    """Only normal paths strictly below this checkout's ignored work directory."""
    root = root.resolve()
    work = root / "work"
    if ".." in path.parts:
        raise ValueError("Parent traversal is not a collection destination")
    candidate = path if path.is_absolute() else root / path
    candidate = candidate.absolute()
    if not candidate.is_relative_to(work) or candidate == work:
        raise ValueError("Use a new path strictly inside this repository's work directory")
    if any(_link(parent) for parent in (candidate, *candidate.parents) if parent.is_relative_to(work)):
        raise ValueError("Symlink/junction paths are not collection destinations")
    if not candidate.resolve().is_relative_to(work.resolve()) or _link(work):
        raise ValueError("Collection destination escapes the work directory")
    return candidate


def _pending(row: dict) -> dict:
    return {"id": row["id"], "wav": row["wav"], "label": row["expected_label"],
            "language": row["language"], "condition": "clean_direct",
            "fixture": False, "consent": False, "label_evidence": "", "split": row["split"],
            "speaker_group": "", "source_group": ""}


def prepare(output: Path, prompts: list[dict], *, root: Path = ROOT) -> dict:
    output = confined(output, root)
    if output.exists():
        raise ValueError("Collection directory already exists; it will not be overwritten")
    rows = slots(prompts)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()  # Exclusive: another process cannot silently replace a populated kit.
    for folder in ("recordings", "originals", "private-provenance"):
        (output / folder).mkdir()
    with (output / "checklist.csv").open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({field: csv_safe(value) for field, value in row.items()} for row in rows)
    with (output / "manifest.pending.jsonl").open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(_pending(row), ensure_ascii=False) + "\n")
    (output / "collection-plan.json").write_text(json.dumps(build_plan(prompts), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"schema_version": 1, "record_type": "speech_collection_kit_prepared", "source_slots": 60,
            "recordings_created": 0, "consent_confirmed": 0, "labels_confirmed": 0,
            "provider_calls": 0, "inference_calls": 0, "accuracy": None,
            "note": "Empty folders and pending checklist prepared. Originals are preserved; nothing recorded, generated, converted or scored."}


def _validate_existing_manifest(path: Path) -> dict:
    spec = importlib.util.spec_from_file_location("collection_dataset_checks", ROOT / "evaluation" / "audio_screening.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_dataset(path)


def check(kit: Path, prompts: list[dict], *, manifest_output: Path | None = None, root: Path = ROOT) -> dict:
    kit = confined(kit, root)
    if not kit.is_dir() or not (kit / "checklist.csv").is_file() or _link(kit / "checklist.csv"):
        raise ValueError("Use a prepared collection directory")
    if (kit / "checklist.csv").stat().st_size > 1_000_000:
        raise ValueError("Checklist exceeds 1 MB")
    destination = confined(manifest_output, root) if manifest_output is not None else None
    if destination is not None and destination.exists():
        raise ValueError("Manifest output already exists")
    with (kit / "checklist.csv").open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(FIELDS):
            raise ValueError("Checklist columns differ from the prepared schema")
        rows = list(reader)
    expected = {row["id"]: row for row in slots(prompts)}
    issues, candidates = [], []
    seen, role_groups, role_voices, voice_splits, voice_groups, group_origins = set(), {}, {}, {}, {}, {}
    present = 0

    def issue(identifier, code):
        issues.append({"id": identifier, "code": code})

    if len(rows) != 60:
        issue(None, "expected_sixty_checklist_rows")
    for row_number, row in enumerate(rows, 1):
        if set(row) != set(FIELDS) or any(not isinstance(value, str) for value in row.values()):
            issue(f"row-{row_number}", "malformed_checklist_row")
            continue
        identifier = row.get("id", "")
        safe_id = identifier if identifier in expected else f"row-{row_number}"
        if identifier not in expected or identifier in seen:
            issue(safe_id, "unknown_or_duplicate_slot")
            continue
        seen.add(identifier)
        intended = expected[identifier]
        if any(row.get(field) != csv_safe(intended[field]) for field in IMMUTABLE):
            issue(safe_id, "planned_slot_metadata_changed")
            continue
        split, label, origin = ROLES[row["role"]]
        for field in ("collected", "prompt_reviewed", "consent"):
            if row.get(field) != "true":
                issue(safe_id, field + "_not_confirmed")
        if row.get("confirmed_label") != label or row.get("origin") != origin:
            issue(safe_id, "independent_origin_or_label_not_confirmed")
        for field in ("label_evidence", "speaker_group", "source_group"):
            value = row.get(field, "")
            if not isinstance(value, str) or not value.strip() or len(value) > 1000:
                issue(safe_id, field + "_missing_or_invalid")
        group = row.get("speaker_group", "").strip()
        role_key = (row["language"], row["role"])
        if group:
            if role_key in role_groups and role_groups[role_key] != group:
                issue(safe_id, "role_must_use_one_actual_voice_identity")
            role_groups[role_key] = group
            if group in group_origins and group_origins[group] != label:
                issue(safe_id, "voice_group_used_for_human_and_ai")
            group_origins[group] = label
        if row.get("voice_is_cloned") == "true":
            issue(safe_id, "cloned_voice_outside_this_collection")
        if label == "spoof":
            for field in ("generator", "model_version", "voice_id"):
                if not row.get(field, "").strip() or len(row[field]) > 200:
                    issue(safe_id, field + "_missing_or_invalid")
            if row.get("voice_is_cloned") != "false":
                issue(safe_id, "noncloned_stock_voice_not_confirmed")
            voice = (row.get("generator", "").strip().casefold(),
                     row.get("model_version", "").strip().casefold(),
                     row.get("voice_id", "").strip().casefold())
            role_voice = voice
            if role_key in role_voices and role_voices[role_key] != role_voice:
                issue(safe_id, "role_must_use_one_stock_voice_and_model")
            role_voices[role_key] = role_voice
            if all(voice):
                if voice in voice_splits and voice_splits[voice] != split:
                    issue(safe_id, "stock_voice_identity_crosses_splits")
                if voice in voice_groups and voice_groups[voice] != group:
                    issue(safe_id, "stock_voice_identity_has_inconsistent_group")
                voice_splits[voice], voice_groups[voice] = split, group
        path = kit / intended["wav"]
        try:
            confined(path, root)
            if not path.resolve().is_relative_to((kit / "recordings").resolve()) or _link(kit / "recordings"):
                raise ValueError("Unexpected recording path")
            with wave.open(str(path), "rb") as audio:
                if (audio.getcomptype() != "NONE" or audio.getnchannels() != 1
                        or audio.getsampwidth() != 2 or audio.getframerate() != 16000):
                    raise ValueError("Unsupported WAV format")
                frames = audio.getnframes()
                if not 128000 <= frames <= 320000:
                    issue(safe_id, "recording_must_be_eight_to_twenty_seconds")
                elif len(audio.readframes(frames)) != frames * 2:
                    issue(safe_id, "recording_truncated")
                else:
                    present += 1
        except (OSError, ValueError, wave.Error, EOFError):
            issue(safe_id, "recording_missing_invalid_or_escaped")
        candidate = _pending(intended)
        candidate.update(wav=str(path), consent=row.get("consent") == "true",
                         label=row.get("confirmed_label"), label_evidence=row.get("label_evidence", ""),
                         speaker_group=group, source_group=row.get("source_group", "").strip())
        if label == "spoof":
            candidate.update(generator=row.get("generator"), model_version=row.get("model_version"),
                             voice_id=row.get("voice_id"), voice_is_cloned=False)
        candidates.append(candidate)
    if seen != set(expected):
        issue(None, "collection_slots_missing")
    preflight = None
    if not issues:
        # Validate global split separation and decoded-audio duplicates before
        # writing any final manifest. No classifier is constructed by this call.
        with tempfile.TemporaryDirectory(prefix=".collection-check-", dir=kit) as temporary:
            probe = Path(temporary) / "manifest.jsonl"
            probe.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in candidates), encoding="utf-8")
            preflight = _validate_existing_manifest(probe)
        if not preflight["ready_for_scoring"]:
            for row in preflight["issues"]:
                number = row.get("row")
                issue(candidates[number - 1]["id"] if isinstance(number, int) else None, row["code"])
    ready = not issues
    written = False
    if ready and destination is not None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8") as stream:
            stream.write("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in candidates))
        written = True
    return {"schema_version": 1, "record_type": "speech_collection_check", "expected_source_clips": 60,
            "readable_compatible_recordings": present, "ready_for_scoring": ready,
            "manifest_written": written, "issues": issues, "provider_calls": 0,
            "inference_calls": 0, "accuracy": None, "accuracy_preservation_proven": False,
            "note": "Checks declared origin/consent, role consistency, WAV format, duplicates and global split groups only. It cannot independently authenticate speech origin, labels, participation permission or representative accuracy. Replays and codec/noise derivatives are separate challenge cases, not independent sources."}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--output-dir", type=Path)
    mode.add_argument("--check", type=Path)
    parser.add_argument("--manifest-output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.manifest_output and not args.check:
            raise ValueError("Manifest output requires a completed kit check")
        prompts = prompt_bank()
        if args.output_dir:
            result = prepare(args.output_dir, prompts)
        elif args.check:
            result = check(args.check, prompts, manifest_output=args.manifest_output)
        else:
            result = build_plan(prompts)
        print(json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False))
        return 1 if result.get("ready_for_scoring") is False else 0
    except (ValueError, TypeError, KeyError, OSError, csv.Error):
        print("Invalid collection input or output. Use the prepared schema and new paths inside work/; nothing was scored.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
