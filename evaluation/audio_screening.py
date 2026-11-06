"""Evaluate local consented WAV files; no provider or network operations.

JSONL rows: {id, wav, label: genuine|spoof|unlabelled, language, condition,
fixture: false}. A label is human-supplied evidence, never inferred from filenames.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from charcha.services.audio_screening import LocalAudioScreener, read_pcm_wav  # noqa: E402


def load_manifest(manifest: Path) -> list[dict]:
    if manifest.stat().st_size > 1_000_000:
        raise ValueError("Manifest exceeds 1 MB")
    inputs = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not inputs or len(inputs) > 500 or any(not isinstance(item, dict) for item in inputs):
        raise ValueError("Manifest must contain 1–500 recording objects")
    ids = [item.get("id") for item in inputs]
    if any(not isinstance(id_, str) or not id_ for id_ in ids) or len(ids) != len(set(ids)):
        raise ValueError("Recording IDs must be unique nonempty strings")
    return inputs


def validate_dataset(manifest: Path) -> dict:
    """Offline evidence checks, not label verification or a detector accuracy claim.

    Only row numbers and fixed issue codes leave this function. Speaker/source
    groups, evidence notes, hashes, paths and audio stay local.
    """
    inputs = load_manifest(manifest)
    issues: list[dict] = []
    groups: dict[tuple[str, str], tuple[str, int]] = {}
    fingerprints: dict[str, int] = {}
    coverage: dict[str, dict[str, int]] = {}
    for number, item in enumerate(inputs, 1):
        def issue(code: str, related_row: int | None = None):
            entry = {"row": number, "code": code}
            if related_row is not None:
                entry["related_row"] = related_row
            issues.append(entry)

        if item.get("consent") is not True:
            issue("consent_not_confirmed")
        if not isinstance(item.get("label_evidence"), str) or not item["label_evidence"].strip():
            issue("independent_label_evidence_missing")
        label, split = item.get("label"), item.get("split")
        label = label if isinstance(label, str) else "invalid"
        split = split if isinstance(split, str) else "invalid"
        if label not in {"genuine", "spoof"} or item.get("fixture") is not False:
            issue("not_labelled_nonfixture_speech")
        if split not in {"calibration", "evaluation"}:
            issue("split_missing_or_invalid")
        if not isinstance(item.get("language"), str) or not item["language"].strip():
            issue("language_missing")
        if not isinstance(item.get("condition"), str) or not item["condition"].strip():
            issue("condition_missing")
        for field in ("speaker_group", "source_group"):
            group = item.get(field)
            if not isinstance(group, str) or not group.strip():
                issue(field + "_missing")
                continue
            key = (field, group.strip())
            if key in groups and groups[key][0] != split:
                issue(field + "_crosses_splits", groups[key][1])
            else:
                groups[key] = (split, number)
        if split in {"calibration", "evaluation"} and label in {"genuine", "spoof"}:
            bucket = coverage.setdefault(split, {"genuine": 0, "spoof": 0})
            bucket[label] += 1
        try:
            path = Path(item["wav"])
            if not path.is_absolute():
                path = manifest.parent / path
            with path.open("rb") as source:
                raw = source.read(1_025_537)
            pcm, _ = read_pcm_wav(raw)
            if len(pcm) < 64_600 * 2:
                issue("shorter_than_detector_window")
            fingerprint = hashlib.sha256(pcm).hexdigest()
            if fingerprint in fingerprints:
                issue("duplicate_audio", fingerprints[fingerprint])
            else:
                fingerprints[fingerprint] = number
        except (ValueError, TypeError, OSError, KeyError):
            issue("recording_unavailable_or_invalid")
    for label in ("genuine", "spoof"):
        if not coverage.get("evaluation", {}).get(label):
            issues.append({"row": None, "code": "evaluation_missing_" + label})
    return {
        "schema_version": 1, "record_type": "screening_dataset_preflight",
        "recording_count": len(inputs), "ready_for_scoring": not issues,
        "issues": issues, "split_label_counts": coverage,
        "provider_calls": 0, "inference_calls": 0, "accuracy": None,
        "note": "Checks declared consent, evidence fields, WAV format, duplicate audio and split separation only. It cannot verify labels, consent, representativeness or model accuracy. Do not tune thresholds on the held-out evaluation split.",
    }


def summarize(rows: list[dict]) -> dict:
    """Unknowns remain visible but never become a correct classified example."""
    eligible = [r for r in rows if r.get("label") in {"genuine", "spoof"} and r.get("fixture") is False]
    labelled = [r for r in eligible if r.get("status") == "complete"]
    classified = [r for r in labelled if r.get("verdict") in {"allow", "suspicious"}]
    genuine = [r for r in classified if r["label"] == "genuine"]
    spoof = [r for r in classified if r["label"] == "spoof"]
    false_alarms = sum(r["verdict"] == "suspicious" for r in genuine)
    missed = sum(r["verdict"] == "allow" for r in spoof)
    timings = sorted(float(r["compute_ms"]) for r in rows if r.get("status") == "complete"
                     and isinstance(r.get("compute_ms"), (int, float))
                     and math.isfinite(r["compute_ms"]) and r["compute_ms"] >= 0)
    percentile = lambda p: timings[max(0, math.ceil(len(timings) * p) - 1)] if timings else None
    return {
        "total": len(rows), "errors": sum(r.get("status") == "error" for r in rows),
        "labelled_total": len(eligible),
        "labelled_errors": sum(r.get("status") == "error" for r in eligible),
        "labelled_nonfixture": len(labelled), "classified_nonfixture": len(classified),
        "unknown_nonfixture": len(labelled) - len(classified),
        "unknown_genuine": sum(r["label"] == "genuine" and r.get("verdict") == "unknown" for r in labelled),
        "unknown_spoof": sum(r["label"] == "spoof" and r.get("verdict") == "unknown" for r in labelled),
        "excluded_fixture_or_unlabelled": sum(r.get("fixture") is not False or r.get("label") not in {"genuine", "spoof"} for r in rows),
        "coverage": len(classified) / len(labelled) if labelled else None,
        "coverage_of_successfully_analyzed": len(classified) / len(labelled) if labelled else None,
        "classification_coverage_all_labelled": len(classified) / len(eligible) if eligible else None,
        "confusion": {"genuine_allowed": len(genuine) - false_alarms, "false_alarms": false_alarms,
                      "spoof_flagged": len(spoof) - missed, "spoof_missed": missed},
        "false_alarm_rate_classified": false_alarms / len(genuine) if genuine else None,
        "miss_rate_classified": missed / len(spoof) if spoof else None,
        "accuracy_classified_only": (len(classified) - false_alarms - missed) / len(classified) if classified else None,
        "balanced_accuracy_classified_only": ((1 - false_alarms / len(genuine)) + (1 - missed / len(spoof))) / 2 if genuine and spoof else None,
        "compute_p50_ms": percentile(.5), "compute_p95_ms": percentile(.95),
        "provider_calls": 0, "experimental": True,
        "caveat": "Conditional accuracy/rates exclude unknowns and failed recordings. Legacy coverage is conditional on successful analysis; report classification_coverage_all_labelled, labelled_errors and unknowns alongside accuracy. No representative accuracy or latency claim follows from synthetic signal fixtures.",
    }


def validate_metadata(inputs: list[dict]) -> None:
    for item in inputs:
        label = item.get("label", "unlabelled")
        if not isinstance(label, str) or label not in {"genuine", "spoof", "unlabelled"}:
            raise ValueError("Labels must be genuine, spoof, or unlabelled")
        if not isinstance(item.get("fixture", True), bool):
            raise ValueError("Fixture must be a boolean")
        for field in ("language", "condition", "split"):
            value = item.get(field, "unspecified")
            if not isinstance(value, str) or not value.strip() or len(value) > 80:
                raise ValueError("Grouping metadata must be short nonempty strings")


def evaluate(manifest: Path, screener: LocalAudioScreener, inputs: list[dict] | None = None) -> list[dict]:
    inputs = load_manifest(manifest) if inputs is None else inputs
    validate_metadata(inputs)
    rows = []
    for item in inputs:
        row = {"id": item["id"], "label": item.get("label", "unlabelled"),
               "fixture": item.get("fixture", True), "language": item.get("language", "unknown"),
               "condition": item.get("condition", "unknown"),
               "split": item.get("split", "unspecified"), "status": "error"}
        if row["label"] not in {"genuine", "spoof", "unlabelled"}:
            raise ValueError("Labels must be genuine, spoof, or unlabelled")
        try:
            path = Path(item["wav"])
            if not path.is_absolute():
                path = manifest.parent / path
            with path.open("rb") as source:
                raw = source.read(1_025_537)
            pcm, rate = read_pcm_wav(raw)
            row.update(screener.analyze(pcm, rate).as_dict(), status="complete")
        except (ValueError, TypeError, OSError, KeyError):
            row["error"] = "recording_unavailable_or_invalid"
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--validate-only", action="store_true", help="Check dataset evidence without loading or running a model")
    parser.add_argument("--strict-manifest", action="store_true", help="Require the dataset evidence checks before inference")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "work" / "audio-screening-evaluation")
    args = parser.parse_args()
    try:
        inputs = load_manifest(args.manifest)
        if not args.validate_only:
            validate_metadata(inputs)
    except (ValueError, OSError):
        parser.exit(2, "Dataset manifest is invalid or unavailable; no inference performed.\n")
    preflight = None
    if args.validate_only or args.strict_manifest:
        try:
            preflight = validate_dataset(args.manifest)
        except (ValueError, OSError):
            parser.exit(2, "Dataset manifest is invalid or unavailable; no inference performed.\n")
        if args.validate_only or not preflight["ready_for_scoring"]:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            (args.output_dir / "dataset-preflight.json").write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(preflight, indent=2))
            return 0 if preflight["ready_for_scoring"] else 2
    screener = LocalAudioScreener(args.model)
    rows = evaluate(args.manifest, screener, inputs)
    report = {"model": screener.status(), "dataset_preflight": preflight, "overall": summarize(rows),
              "by_split": {split: summarize([r for r in rows if r["split"] == split])
                           for split in sorted({r["split"] for r in rows})},
              "by_language": {language: summarize([r for r in rows if r["language"] == language])
                              for language in sorted({r["language"] for r in rows})},
              "by_condition": {condition: summarize([r for r in rows if r["condition"] == condition])
                               for condition in sorted({r["condition"] for r in rows})}}
    held_out = report["by_split"].get("evaluation")
    report["headline_scope"] = ("held_out_evaluation" if preflight is not None else "declared_evaluation_unvalidated") if held_out is not None else "exploratory_no_held_out_split"
    report["headline"] = held_out if held_out is not None else report["overall"]
    report["overall_scope"] = "pooled_including_calibration_not_a_held_out_score"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "results.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    (args.output_dir / "summary.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"scope": report["headline_scope"], "dataset_preflight_passed": preflight is not None,
                      "summary": report["headline"]}, indent=2))


if __name__ == "__main__":
    sys.exit(main())
