"""Bounded offline, paired speech-screening pilot; default is a no-access plan.

No downloads, provider requests, .env files, microphone access or live changes.
Only an explicit --execute reads a consented local manifest and loads one CPU
model. Prefix repetition is an experiment, not additional observed speech.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
MAX_RECORDINGS = 60
MAX_ANALYSIS_CALLS = 300
BATCH_SIZE = 5
LANGUAGES = ("hi", "ta", "bn", "te", "mr")
DEFAULT_WALL_SECONDS = 180
MAX_WALL_SECONDS = 300
CPU_THREADS = 2


def _experiment():
    spec = importlib.util.spec_from_file_location("speech_study_durations", ROOT / "scripts/compare_screening_durations.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_plan() -> dict:
    return {
        "schema_version": 1, "record_type": "speech_screening_study",
        "plan_only": True, "experimental": True, "status": "plan_only",
        "provider_calls": 0, "paid_servers": 0, "inference_calls": 0,
        "analysis_calls": 0, "successfully_scored_model_windows": 0,
        "accuracy": None, "accuracy_preservation_proven": False,
        "live_activation": False, "affects_live_screening": False, "voice_cloning": False,
        "required_languages": list(LANGUAGES), "maximum_source_recordings": MAX_RECORDINGS,
        "maximum_analysis_calls": MAX_ANALYSIS_CALLS, "batch_size": BATCH_SIZE,
        "maximum_batches": 12, "cpu_profile": {"provider": "CPUExecutionProvider", "intra_op_threads": CPU_THREADS, "sequential": True},
        "default_wall_seconds": DEFAULT_WALL_SECONDS, "maximum_wall_seconds": MAX_WALL_SECONDS,
        "candidates_ms": [500, 1000, 2000, 3000, 4037.5],
        "baseline": "First native 4.0375 seconds, never the whole 8–20 second recording or its final tail.",
        "evidence": "Every short input repeats only its observed prefix into the fixed native tensor. Repeated samples are not new evidence.",
        "headline_scope": "declared_held_out_evaluation_only",
        "threshold_policy": "Frozen production defaults: allow at or below 0.2, suspicious at or above 0.8. This study never fits thresholds or changes live policy.",
        "requirements": "Validate the entire manifest, consent, label evidence, speaker/source split separation and WAV files before loading a model. Every required language needs genuine and spoof evaluation recordings. Sparse condition subsets retain their own denominators and null rates for absent classes.",
        "limitations": "A small pilot cannot establish representative accuracy or preserved accuracy. Declared labels and independent groups are not independently authenticated. Evaluation must not be used to tune thresholds. Calibration is reported separately.",
        "wall_budget_policy": "Stop admitting analysis calls at the deadline. A running synchronous model load or analysis may finish after it; this is not a hard process timeout. No retries.",
    }


def _prepare(manifest: Path, experiment) -> tuple[dict, list[dict], dict]:
    dataset = experiment._dataset()
    inputs = dataset.load_manifest(manifest)
    # Reject an oversized scope before reading WAVs or loading a model.
    if not 1 <= len(inputs) <= MAX_RECORDINGS:
        return {"ready_for_scoring": False, "recording_count": len(inputs), "issues": [{"row": None, "code": "study_exceeds_sixty_recordings"}]}, [], {}
    dataset.validate_metadata(inputs)
    preflight = dataset.validate_dataset(manifest)
    issues = preflight["issues"]
    for index, item in enumerate(inputs, 1):
        if item.get("language") not in LANGUAGES:
            issues.append({"row": index, "code": "study_language_not_supported"})
    evaluation = [item for item in inputs if item.get("split") == "evaluation"]
    for language in LANGUAGES:
        for label in ("genuine", "spoof"):
            if not any(item.get("language") == language and item.get("label") == label for item in evaluation):
                issues.append({"row": None, "code": "study_evaluation_missing_" + language + "_" + label})
    preflight["ready_for_scoring"] = not issues
    if issues:
        return preflight, [], {}
    _, decode = experiment._runtime()
    recordings, metadata, conditions = [], {}, {}
    for index, item in enumerate(inputs, 1):
        path = Path(item["wav"])
        if not path.is_absolute():
            path = manifest.parent / path
        with path.open("rb") as source:
            pcm, _ = decode(source.read(1_025_537))
        # Revalidate the exact bytes retained for the study; never analyze a tail.
        experiment.tiled_prefix(pcm, experiment.WINDOW_SAMPLES)
        identifier = f"recording-{index:03d}"
        condition = conditions.setdefault(item["condition"], f"condition-{len(conditions) + 1:03d}")
        recordings.append({"id": identifier, "pcm": pcm, "fixture": False,
                           "label": item["label"], "split": item["split"],
                           "language": item["language"], "condition": condition})
        metadata[identifier] = {key: item[key].strip() for key in ("speaker_group", "source_group")}
    return preflight, recordings, metadata


def _summary(rows: list[dict], private_metadata: dict) -> dict:
    genuine = [row for row in rows if row["label"] == "genuine"]
    spoof = [row for row in rows if row["label"] == "spoof"]
    classified = [row for row in rows if row["status"] == "complete" and row["verdict"] in {"allow", "suspicious"}]
    classified_genuine = [row for row in classified if row["label"] == "genuine"]
    classified_spoof = [row for row in classified if row["label"] == "spoof"]
    alarms = sum(row["verdict"] == "suspicious" for row in classified_genuine)
    misses = sum(row["verdict"] == "allow" for row in classified_spoof)
    def groups(subset, field):
        return len({private_metadata[row["id"]][field] for row in subset})
    timings = sorted(row["compute_ms"] for row in rows if row["status"] == "complete" and row["compute_ms"] is not None)
    percentile = lambda p: timings[max(0, math.ceil(len(timings) * p) - 1)] if timings else None
    return {
        "source_recordings": len(rows), "genuine_recordings": len(genuine), "spoof_recordings": len(spoof),
        "classified": len(classified), "classified_genuine": len(classified_genuine), "classified_spoof": len(classified_spoof),
        "unknown": sum(row["status"] == "complete" and row["verdict"] == "unknown" for row in rows),
        "unknown_genuine": sum(row["status"] == "complete" and row["verdict"] == "unknown" for row in genuine),
        "unknown_spoof": sum(row["status"] == "complete" and row["verdict"] == "unknown" for row in spoof),
        "errors": sum(row["status"] == "error" for row in rows),
        "genuine_errors": sum(row["status"] == "error" for row in genuine),
        "spoof_errors": sum(row["status"] == "error" for row in spoof),
        "unattempted": sum(row["status"] == "unattempted" for row in rows),
        "genuine_unattempted": sum(row["status"] == "unattempted" for row in genuine),
        "spoof_unattempted": sum(row["status"] == "unattempted" for row in spoof),
        "false_alarms": alarms, "misses": misses,
        "false_alarms_over_all_genuine": alarms / len(genuine) if genuine else None,
        "misses_over_all_spoof": misses / len(spoof) if spoof else None,
        "false_alarm_rate_classified": alarms / len(classified_genuine) if classified_genuine else None,
        "miss_rate_classified": misses / len(classified_spoof) if classified_spoof else None,
        "classification_coverage": len(classified) / len(rows) if rows else None,
        "genuine_classification_coverage": len(classified_genuine) / len(genuine) if genuine else None,
        "spoof_classification_coverage": len(classified_spoof) / len(spoof) if spoof else None,
        "distinct_declared_speaker_groups": groups(rows, "speaker_group"),
        "distinct_declared_source_groups": groups(rows, "source_group"),
        "genuine_distinct_declared_speaker_groups": groups(genuine, "speaker_group"),
        "spoof_distinct_declared_source_groups": groups(spoof, "source_group"),
        "compute_p50_ms": percentile(.5), "compute_p95_ms": percentile(.95),
        "denominator_note": "All-source error fractions are not accuracy; unknown, error and unattempted recordings remain in their denominators. Classified-only rates are null when that class has no classified result. Group counts reflect declarations, not verified independence.",
    }


def _aggregate(rows: list[dict], metadata: dict, prefixes: tuple[int, ...], sample_rate: int) -> list[dict]:
    return [{"observed_audio_ms": samples * 1000 / sample_rate,
             **_summary(selected := [row for row in rows if row["observed_audio_ms"] == samples * 1000 / sample_rate], metadata),
             "by_language": {language: _summary([row for row in selected if row["language"] == language], metadata) for language in LANGUAGES},
             "by_condition": {condition: _summary([row for row in selected if row["condition"] == condition], metadata) for condition in sorted({row["condition"] for row in selected})}}
            for samples in prefixes]


def run_study(manifest: Path, *, model: Path | None = None,
              max_wall_seconds: float = DEFAULT_WALL_SECONDS, clock=time.monotonic) -> dict:
    if isinstance(max_wall_seconds, bool) or not isinstance(max_wall_seconds, (int, float)) or not math.isfinite(max_wall_seconds) or not 0 < max_wall_seconds <= MAX_WALL_SECONDS:
        raise ValueError("Wall budget must be above zero and at most 300 seconds")
    started = clock()
    report = {**build_plan(), "plan_only": False, "status": "blocked_dataset", "max_wall_seconds": max_wall_seconds,
              "source_recording_count": 0, "results": [], "evaluation_by_duration": [], "calibration_by_duration": []}
    experiment = _experiment()
    try:
        preflight, recordings, metadata = _prepare(manifest, experiment)
    except (ValueError, TypeError, OSError, KeyError, json.JSONDecodeError):
        preflight, recordings, metadata = {"ready_for_scoring": False, "issues": [{"row": None, "code": "study_manifest_or_recording_invalid"}]}, [], {}
    report["dataset_preflight"] = preflight
    if not preflight.get("ready_for_scoring"):
        report["wall_seconds"] = max(0, clock() - started)
        return report
    report["source_recording_count"] = len(recordings)
    report["batch_count"] = math.ceil(len(recordings) / BATCH_SIZE)
    order = (experiment.WINDOW_SAMPLES, *experiment.PREFIX_SAMPLES[:-1])
    for recording in recordings:
        for samples in order:
            report["results"].append({key: recording[key] for key in ("id", "fixture", "label", "split", "language", "condition")} | {
                "observed_audio_ms": samples * 1000 / experiment.SAMPLE_RATE,
                "model_input_samples": experiment.WINDOW_SAMPLES,
                "repeated_samples": experiment.WINDOW_SAMPLES - samples,
                "strategy": "native_full_window" if samples == experiment.WINDOW_SAMPLES else "prefix_tile_repeat",
                "status": "unattempted", "verdict": "unknown", "score": None, "compute_ms": None,
                "score_delta_from_full": None, "verdict_agrees_with_full": None})
    report["status"] = "stopped_wall_budget"
    if clock() - started < max_wall_seconds:
        try:
            factory, _ = experiment._runtime()
            screener = factory(model, cpu_threads=CPU_THREADS)
            status = screener.status()
        except Exception:
            screener = None
            status = {"ready": False, "reason": "local_model_setup_failed"}
        # A fixed allowlist prevents local paths or exception details entering exports.
        report["model"] = {key: status[key] for key in ("id", "revision", "sha256", "ready", "kind", "license", "reason", "threshold", "allow_threshold", "score_calibrated", "cpu_threads", "window_ms", "validated_on_indian_meeting_audio") if key in status}
        if not status.get("ready"):
            report["status"] = "blocked_model_unavailable"
        else:
            report["inference_calls"] = None
            report["inference_count_note"] = "Analysis attempts and successfully scored windows are counted. Failed native inference attempts are not exposed by the analyzer."
            report["status"] = "labelled_exploratory_pilot_complete"
            halted = False
            # Explicit sequential five-recording batches, with a check before every call.
            for batch_start in range(0, len(recordings), BATCH_SIZE):
                for recording_index in range(batch_start, min(batch_start + BATCH_SIZE, len(recordings))):
                    recording = recordings[recording_index]
                    for offset, samples in enumerate(order):
                        if clock() - started >= max_wall_seconds or report["analysis_calls"] >= MAX_ANALYSIS_CALLS:
                            halted = True
                            break
                        row = report["results"][recording_index * len(order) + offset]
                        report["analysis_calls"] += 1
                        row["status"] = "error"
                        try:
                            result = screener.analyze(experiment.tiled_prefix(recording["pcm"], samples), experiment.SAMPLE_RATE).as_dict()
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
    report["wall_seconds"] = max(0, clock() - started)
    for split in ("evaluation", "calibration"):
        report[split + "_by_duration"] = _aggregate([row for row in report["results"] if row["split"] == split], metadata, experiment.PREFIX_SAMPLES, experiment.SAMPLE_RATE)
    report["calibration_scope"] = "review_only_not_a_held_out_score"
    report["results"].sort(key=lambda row: (row["id"], row["observed_audio_ms"]))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=lambda prog: argparse.HelpFormatter(prog, width=88))
    parser.add_argument("--plan", action="store_true", help="Print only the no-access plan (default)")
    parser.add_argument("--execute", action="store_true", help="Explicitly validate and run the bounded offline pilot")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--max-wall-seconds", type=float, default=DEFAULT_WALL_SECONDS)
    parser.add_argument("--output", type=Path, help="New report path; existing files are never overwritten")
    args = parser.parse_args(argv)
    if args.output and args.output.exists():
        print("Report already exists; no work performed.")
        return 2
    if args.plan and args.execute or args.execute and not args.manifest:
        print("Use --execute with --manifest, or use the default plan.")
        return 2
    if not math.isfinite(args.max_wall_seconds) or not 0 < args.max_wall_seconds <= MAX_WALL_SECONDS:
        print("Wall budget must be above zero and at most 300 seconds.")
        return 2
    report = run_study(args.manifest, model=args.model, max_wall_seconds=args.max_wall_seconds) if args.execute else build_plan()
    payload = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        try:
            with args.output.open("x", encoding="utf-8") as target:
                target.write(payload)
        except FileExistsError:
            print("Report already exists; it was not overwritten.")
            return 2
    print(payload, end="")
    return 0 if report["status"] in {"plan_only", "labelled_exploratory_pilot_complete"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
