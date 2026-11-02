"""Bounded local false-alarm study on public FLEURS human speech.

The default only prints a plan. Explicit execution reads a checked public-source
manifest and the installed CPU model; it never downloads, contacts providers,
reads provider environment files, records speech or changes live screening.
Public dataset licensing is reuse evidence, not personally verified consent.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import statistics
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
DATASET = "google/fleurs"
REVISION = "70bb2e84b976b7e960aa89f1c648e09c59f894dd"
LANGUAGES = ("hi", "ta", "bn", "te", "mr")
CONFIGS = {language: language + "_in" for language in LANGUAGES}
MAX_RECORDINGS = 50
MAX_ANALYSIS_CALLS = 250
SAMPLE_RATE = 16000
WINDOW_SAMPLES = 64600
PREFIX_SAMPLES = (8000, 16000, 32000, 48000, WINDOW_SAMPLES)
DEFAULT_WALL_SECONDS = 180
MAX_WALL_SECONDS = 300
CPU_THREADS = 2
MODEL_KEYS = ("id", "revision", "sha256", "ready", "kind", "license", "reason",
              "threshold", "allow_threshold", "score_calibrated", "cpu_threads",
              "window_ms", "validated_on_indian_meeting_audio")


def _experiment():
    spec = importlib.util.spec_from_file_location("public_human_prefixes", ROOT / "scripts/compare_screening_durations.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_plan() -> dict:
    return {
        "schema_version": 1, "record_type": "public_human_screening_study",
        "plan_only": True, "status": "plan_only", "experimental": True,
        "source_dataset": DATASET, "source_revision": REVISION,
        "source_split": "test", "license": "cc-by-4.0",
        "attribution": "Google FLEURS (Conneau et al., 2022)",
        "required_languages": list(LANGUAGES), "maximum_source_recordings": MAX_RECORDINGS,
        "maximum_analysis_calls": MAX_ANALYSIS_CALLS,
        "default_wall_seconds": DEFAULT_WALL_SECONDS, "maximum_wall_seconds": MAX_WALL_SECONDS,
        "provider_calls": 0, "paid_servers": 0, "analysis_calls": 0,
        "inference_calls": 0, "successfully_scored_model_windows": 0,
        "voice_cloning": False, "live_activation": False, "affects_live_screening": False,
        "accuracy": None, "accuracy_preservation_proven": False,
        "miss_rate": None, "detection_rate": None, "true_positive_rate": None,
        "distinct_speakers": None, "pass_decision": None,
        "ai_recordings": 0, "headline_scope": "human_only_public_read_speech_false_alarm_pilot",
        "cpu_profile": {"provider": "CPUExecutionProvider", "intra_op_threads": CPU_THREADS, "sequential": True},
        "candidates_ms": [500, 1000, 2000, 3000, 4037.5],
        "baseline": "The same first native 4.0375 seconds from each recording; no whole-clip or tail certification.",
        "prefix_policy": "Short-prefix repetition is an isolated sensitivity experiment. Repeated samples supply no new observed speech and cannot activate a shorter live gate.",
        "threshold_policy": "Frozen defaults: allow at or below 0.2; suspicious at or above 0.8. No tuning or calibration.",
        "latency_boundary": "CPU analyzer processing time; excludes speech collection, network, STT/translation/TTS and listener playback.",
        "limitations": [
            "Publisher describes human read speech; origin and individual consent are not independently reverified here.",
            "Public CC BY 4.0 licensing is reuse-permission evidence, not personally obtained consent.",
            "Speaker identifiers are unavailable; distinct speaker count and speaker independence are unknown.",
            "Selection is a small deterministic convenience subset, not representative live Indian meetings.",
            "Training overlap with the installed detector is not established.",
            "No AI examples are present, so AI detection, misses, overall accuracy and accuracy preservation cannot be estimated.",
            "Clip fractions are descriptive; repeated speakers and paired prefixes are not independent observations.",
        ],
        "wall_budget_policy": "Stop admitting calls at the deadline. A synchronous load or running analysis can finish afterwards; no hard process timeout or retries.",
    }


def _prepare(manifest: Path) -> tuple[dict, list[dict]]:
    """Validate exact retained bytes with stdlib only, before any model import."""
    if manifest.stat().st_size > 1_000_000:
        raise ValueError("Manifest exceeds 1 MB")
    inputs = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not 1 <= len(inputs) <= MAX_RECORDINGS or any(not isinstance(item, dict) for item in inputs):
        raise ValueError("Use one to fifty recording objects")
    issues, recordings = [], []
    seen_ids, seen_pcm, seen_sources = set(), set(), set()
    coverage = {language: 0 for language in LANGUAGES}
    base = manifest.parent.resolve()
    for index, item in enumerate(inputs, 1):
        codes = []
        language = item.get("language")
        if language not in LANGUAGES:
            codes.append("language_not_supported")
        fixed = {"source_dataset": DATASET, "source_revision": REVISION, "source_split": "test",
                 "label": "genuine", "split": "evaluation", "usage_permission": "public_license", "license": "cc-by-4.0"}
        if any(item.get(field) != expected for field, expected in fixed.items()) or item.get("schema_version", 1) != 1:
            codes.append("public_source_or_license_not_confirmed")
        if item.get("source_config") != CONFIGS.get(language):
            codes.append("source_config_does_not_match_language")
        attribution = item.get("attribution")
        if not isinstance(attribution, str) or not attribution.strip() or len(attribution) > 1000:
            codes.append("source_attribution_missing")
        # Unknown identities stay unknown. Clip IDs or filenames are not people.
        if item.get("speaker_id") is not None:
            codes.append("unsupported_speaker_identity_claim")
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in seen_ids:
            codes.append("source_id_missing_or_duplicate")
        else:
            seen_ids.add(identifier)
        filename = item.get("source_filename")
        if (not isinstance(filename, str) or not filename or len(filename) > 250
                or PurePosixPath(filename).name != filename or "\\" in filename
                or not filename.lower().endswith(".wav")):
            codes.append("source_filename_invalid")
        else:
            source_key = (language, filename)
            if source_key in seen_sources:
                codes.append("duplicate_source_recording")
            seen_sources.add(source_key)
        for field in ("sha256", "source_sha256"):
            if not isinstance(item.get(field), str) or not re.fullmatch(r"[0-9a-f]{64}", item[field]):
                codes.append(field + "_missing_or_invalid")
        frames = item.get("num_samples")
        if type(frames) is not int or not WINDOW_SAMPLES <= frames <= SAMPLE_RATE * 30:
            codes.append("num_samples_invalid")
        if codes:
            issues.extend({"row": index, "code": code} for code in codes)
            continue
        try:
            path = Path(item["wav"])
            if not path.is_absolute():
                path = manifest.parent / path
            if not path.resolve().is_relative_to(base) or path.is_symlink():
                raise ValueError("Recording path escapes manifest directory")
            with path.open("rb") as source:
                raw = source.read(1_025_537)
            if not raw or len(raw) > 1_025_536 or hashlib.sha256(raw).hexdigest() != item["sha256"]:
                raise ValueError("Recording hash does not match")
            with wave.open(io.BytesIO(raw), "rb") as source:
                if (source.getcomptype() != "NONE" or source.getnchannels() != 1 or source.getsampwidth() != 2
                        or source.getframerate() != SAMPLE_RATE or source.getnframes() != frames):
                    raise ValueError("Recording format or frame count mismatch")
                pcm = source.readframes(frames)
            if len(pcm) != frames * 2:
                raise ValueError("Truncated recording")
            fingerprint = hashlib.sha256(pcm).hexdigest()
            if fingerprint in seen_pcm:
                issues.append({"row": index, "code": "duplicate_decoded_audio"})
            seen_pcm.add(fingerprint)
            coverage[language] += 1
            recordings.append({"id": f"recording-{index:03d}", "language": language, "pcm": pcm})
        except (OSError, ValueError, TypeError, KeyError, wave.Error, EOFError):
            issues.append({"row": index, "code": "recording_hash_format_or_path_invalid"})
    for language, count in coverage.items():
        if not count:
            issues.append({"row": None, "code": "missing_public_human_" + language})
    preflight = {"ready_for_scoring": not issues, "recording_count": len(inputs), "issues": issues,
                 "by_language": coverage, "provider_calls": 0, "inference_calls": 0,
                 "distinct_speakers": None,
                 "checks": "Pinned source/license declarations, local WAV hashes, exact format, source and decoded-audio duplicates. Original-source hashes are retained declarations, not re-fetched or reverified from the Internet."}
    return preflight, recordings if not issues else []


def _summary(rows: list[dict]) -> dict:
    completed = [row for row in rows if row["status"] == "complete"]
    allowed = sum(row["verdict"] == "allow" for row in completed)
    alarms = sum(row["verdict"] == "suspicious" for row in completed)
    classified = allowed + alarms
    timings = sorted(row["compute_ms"] for row in completed)
    warm = [row["compute_ms"] for row in completed if not row["first_analysis"]]
    paired = [row for row in rows if row["verdict_agrees_with_full"] is not None]
    deltas = [abs(row["score_delta_from_full"]) for row in rows if row["score_delta_from_full"] is not None]
    return {
        "source_recordings": len(rows), "genuine_recordings": len(rows), "ai_recordings": 0,
        "allow": allowed, "false_alarms": alarms, "classified": classified,
        "unknown": sum(row["verdict"] == "unknown" for row in completed),
        "errors": sum(row["status"] == "error" for row in rows),
        "unattempted": sum(row["status"] == "unattempted" for row in rows),
        "false_alarms_over_all_genuine": alarms / len(rows) if rows else None,
        "false_alarm_rate_classified": alarms / classified if classified else None,
        "classification_coverage": classified / len(rows) if rows else None,
        "distinct_speakers": None, "accuracy": None, "miss_rate": None,
        "true_positive_rate": None, "detection_rate": None,
        "compute_p50_ms": statistics.median(timings) if timings else None,
        "compute_p95_ms": timings[max(0, math.ceil(len(timings) * .95) - 1)] if timings else None,
        "warm_compute_p50_ms": statistics.median(warm) if warm else None,
        "paired_complete": len(paired),
        "verdict_changes_from_full": sum(not row["verdict_agrees_with_full"] for row in paired),
        "maximum_absolute_score_delta_from_full": max(deltas) if deltas else None,
        "denominator_note": "All-source false-alarm fractions retain unknown/error/unattempted clips; these are not accuracy. Conditional rates exclude those outcomes and require coverage alongside them. Distinct speakers and independence are unknown.",
    }


def run_study(manifest: Path, *, model: Path | None = None,
              max_wall_seconds: float = DEFAULT_WALL_SECONDS, clock=time.monotonic) -> dict:
    if (isinstance(max_wall_seconds, bool) or not isinstance(max_wall_seconds, (int, float))
            or not math.isfinite(max_wall_seconds) or not 0 < max_wall_seconds <= MAX_WALL_SECONDS):
        raise ValueError("Wall budget must be above zero and at most 300 seconds")
    started = clock()
    report = {**build_plan(), "plan_only": False, "status": "blocked_dataset", "max_wall_seconds": max_wall_seconds,
              "source_recording_count": 0, "results": [], "evaluation_by_duration": []}
    try:
        preflight, recordings = _prepare(manifest)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        preflight, recordings = {"ready_for_scoring": False, "issues": [{"row": None, "code": "public_manifest_or_recording_invalid"}]}, []
    report["dataset_preflight"] = preflight
    if not preflight["ready_for_scoring"]:
        report["wall_seconds"] = max(0, clock() - started)
        return report
    report["source_recording_count"] = len(recordings)
    order = (WINDOW_SAMPLES, *PREFIX_SAMPLES[:-1])
    for recording in recordings:
        for samples in order:
            report["results"].append({"id": recording["id"], "language": recording["language"], "label": "genuine",
                "split": "evaluation", "observed_audio_ms": samples * 1000 / SAMPLE_RATE,
                "model_input_samples": WINDOW_SAMPLES, "repeated_samples": WINDOW_SAMPLES - samples,
                "strategy": "native_full_window" if samples == WINDOW_SAMPLES else "prefix_tile_repeat",
                "status": "unattempted", "verdict": "unknown", "score": None, "compute_ms": None,
                "first_analysis": False, "score_delta_from_full": None, "verdict_agrees_with_full": None})
    report["status"] = "stopped_wall_budget"
    if clock() - started < max_wall_seconds:
        experiment = _experiment()
        model_started = clock()
        try:
            factory, _ = experiment._runtime()
            screener = factory(model, threshold=.8, allow_threshold=.2, cpu_threads=CPU_THREADS)
            status = screener.status()
        except Exception:
            screener, status = None, {"ready": False, "reason": "local_model_setup_failed"}
        report["model_load_ms"] = max(0, (clock() - model_started) * 1000)
        report["model"] = {key: status[key] for key in MODEL_KEYS if key in status}
        if not status.get("ready"):
            report["status"] = "blocked_model_unavailable"
        else:
            report["inference_calls"] = None
            report["inference_count_note"] = "Analysis attempts and successfully scored windows are counted; failed native inference attempts are not exposed by the analyzer."
            report["status"] = "human_false_alarm_pilot_complete"
            halted = False
            for index, recording in enumerate(recordings):
                for offset, samples in enumerate(order):
                    if clock() - started >= max_wall_seconds or report["analysis_calls"] >= MAX_ANALYSIS_CALLS:
                        halted = True
                        break
                    row = report["results"][index * len(order) + offset]
                    row["first_analysis"] = report["analysis_calls"] == 0
                    report["analysis_calls"] += 1
                    row["status"] = "error"
                    try:
                        result = screener.analyze(experiment.tiled_prefix(recording["pcm"], samples), SAMPLE_RATE).as_dict()
                        score, verdict, compute = result["score"], result["verdict"], result["compute_ms"]
                        if (verdict not in {"allow", "suspicious", "unknown"}
                                or score is None and verdict != "unknown"
                                or score is not None and (isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1)
                                or isinstance(compute, bool) or not isinstance(compute, (int, float)) or not math.isfinite(compute) or compute < 0
                                or type(result.get("windows_analyzed", 0)) is not int or not 0 <= result.get("windows_analyzed", 0) <= 1):
                            raise ValueError("Invalid bounded analysis result")
                        row.update(status="complete", verdict=verdict, score=score, compute_ms=compute)
                        report["successfully_scored_model_windows"] += result.get("windows_analyzed", 0)
                    except Exception:
                        row["error"] = "local_analysis_failed"
                if halted:
                    break
            if halted:
                report["status"] = "stopped_wall_budget"
    for start in range(0, len(report["results"]), len(order)):
        paired = report["results"][start:start + len(order)]
        baseline = paired[0]
        for row in paired:
            if row["status"] == baseline["status"] == "complete":
                row["verdict_agrees_with_full"] = row["verdict"] == baseline["verdict"]
                if row["score"] is not None and baseline["score"] is not None:
                    row["score_delta_from_full"] = round(row["score"] - baseline["score"], 6)
    report["unattempted_analysis_calls"] = sum(row["status"] == "unattempted" for row in report["results"])
    report["failed_analysis_calls"] = sum(row["status"] == "error" for row in report["results"])
    if report["failed_analysis_calls"] and report["status"] == "human_false_alarm_pilot_complete":
        report["status"] = "analysis_complete_with_errors"
    for samples in PREFIX_SAMPLES:
        rows = [row for row in report["results"] if row["observed_audio_ms"] == samples * 1000 / SAMPLE_RATE]
        report["evaluation_by_duration"].append({"observed_audio_ms": samples * 1000 / SAMPLE_RATE, **_summary(rows),
            "by_language": {language: _summary([row for row in rows if row["language"] == language]) for language in LANGUAGES}})
    first = next((row for row in report["results"] if row["first_analysis"]), None)
    report["first_analysis_compute_ms"] = first["compute_ms"] if first else None
    report["wall_seconds"] = max(0, clock() - started)
    report["results"].sort(key=lambda row: (row["id"], row["observed_audio_ms"]))
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=lambda prog: argparse.HelpFormatter(prog, width=88))
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--max-wall-seconds", type=float, default=DEFAULT_WALL_SECONDS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.output and args.output.exists():
        print("Report already exists; no work performed.")
        return 2
    if args.plan and args.execute or args.execute and not args.manifest:
        print("Use --execute with --manifest, or the default plan.")
        return 2
    if not math.isfinite(args.max_wall_seconds) or not 0 < args.max_wall_seconds <= MAX_WALL_SECONDS:
        print("Wall budget must be above zero and at most 300 seconds.")
        return 2
    report = run_study(args.manifest, model=args.model, max_wall_seconds=args.max_wall_seconds) if args.execute else build_plan()
    payload = json.dumps(report, ensure_ascii=True, indent=2, allow_nan=False) + "\n"
    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as target:
                target.write(payload)
        except OSError:
            print("Report output unavailable; existing files were not overwritten.")
            return 2
    print(payload, end="")
    return 0 if report["status"] in {"plan_only", "human_false_alarm_pilot_complete"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
