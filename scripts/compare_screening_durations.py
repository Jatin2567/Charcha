"""Local-only prefix sensitivity experiment; never changes live screening.

The default prints a plan. Explicit diagnostics may run the installed CPU model
on synthetic signals. Tiling a prefix fills the fixed model tensor but does not
create additional observed speech. No downloads, providers or .env files.
"""
from __future__ import annotations

import argparse
import array
import importlib.util
import json
import math
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_RATE = 16000
WINDOW_SAMPLES = 64600
PREFIX_SAMPLES = (8000, 16000, 32000, 48000, WINDOW_SAMPLES)
MAX_RECORDINGS = 5


def build_plan() -> dict:
    return {
        "schema_version": 1, "record_type": "screening_duration_plan",
        "plan_only": True, "experimental": True,
        "provider_calls": 0, "paid_servers": 0, "inference_calls": 0,
        "analysis_calls": 0, "successfully_scored_model_windows": 0,
        "accuracy": None, "accuracy_preservation_proven": False,
        "live_activation": False, "affects_live_screening": False,
        "voice_cloning": False, "sample_rate": SAMPLE_RATE,
        "model_input_samples": WINDOW_SAMPLES,
        "model_input_ms": WINDOW_SAMPLES * 1000 / SAMPLE_RATE,
        "maximum_source_recordings": MAX_RECORDINGS,
        "maximum_comparisons": MAX_RECORDINGS * len(PREFIX_SAMPLES),
        "candidates": [
            {"observed_samples": samples, "observed_audio_ms": samples * 1000 / SAMPLE_RATE,
             "model_input_samples": WINDOW_SAMPLES,
             "repeated_samples": WINDOW_SAMPLES - samples,
             "strategy": "native_full_window" if samples == WINDOW_SAMPLES else "prefix_tile_repeat"}
            for samples in PREFIX_SAMPLES
        ],
        "evidence": "Repeated prefix samples are not new observed audio. Synthetic diagnostics measure score sensitivity and execution only, never speech accuracy.",
        "production_policy": "The live classifier still requires its complete native window. This tool cannot release, allow or block meeting audio.",
        "acceptance": "Preserving accuracy requires independent labelled held-out speech, false-alarm/miss/unknown reporting and a predeclared comparison margin. Agreement on fixtures is insufficient.",
    }


def tiled_prefix(pcm: bytes, samples: int) -> bytes:
    """Crop observed evidence, tile it, then truncate to the reviewed model size."""
    if (not isinstance(pcm, bytes) or len(pcm) % 2
            or len(pcm) < WINDOW_SAMPLES * 2 or len(pcm) > 30 * SAMPLE_RATE * 2):
        raise ValueError("Use 4.0375–30 seconds of signed 16-bit mono source PCM")
    if not isinstance(samples, int) or isinstance(samples, bool) or samples not in PREFIX_SAMPLES:
        raise ValueError("Choose a reviewed prefix duration")
    prefix = pcm[:samples * 2]
    return (prefix * math.ceil(WINDOW_SAMPLES / samples))[:WINDOW_SAMPLES * 2]


def diagnostic_recordings() -> list[dict]:
    """Deterministic, unlabelled synthetic signals; no genuine/spoof label exists."""
    rng = random.Random(20261029)
    signals = {name: array.array("h") for name in (
        "steady_tone", "chirp", "amplitude_modulated", "seeded_noise", "late_frequency_change")}
    for index in range(WINDOW_SAMPLES):
        t = index / SAMPLE_RATE
        signals["steady_tone"].append(int(6000 * math.sin(2 * math.pi * 220 * t)))
        signals["chirp"].append(int(6000 * math.sin(2 * math.pi * (100 * t + 40 * t * t))))
        signals["amplitude_modulated"].append(int(6000 * (.65 + .3 * math.sin(2 * math.pi * 1.3 * t)) * math.sin(2 * math.pi * 170 * t)))
        signals["seeded_noise"].append(rng.randint(-5000, 5000))
        hz = 150 if index < SAMPLE_RATE else 300
        signals["late_frequency_change"].append(int(6000 * math.sin(2 * math.pi * hz * t)))
    rows = []
    for name, values in signals.items():
        if sys.byteorder != "little":
            values.byteswap()
        rows.append({"id": name, "pcm": values.tobytes(), "fixture": True,
                     "label": "unlabelled", "split": "diagnostic",
                     "language": "not_speech", "condition": "synthetic_signal"})
    return rows


def _runtime():
    # Kept behind explicit execution: default plan imports no model, NumPy or app settings.
    sys.path.insert(0, str(ROOT / "server"))
    from charcha.services.audio_screening import LocalAudioScreener, read_pcm_wav
    return LocalAudioScreener, read_pcm_wav


def _dataset():
    spec = importlib.util.spec_from_file_location("duration_dataset", ROOT / "evaluation" / "audio_screening.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def strict_recordings(manifest: Path, batch_index: int | None = None) -> tuple[dict, list[dict]]:
    """Load only explicit, validated local recordings; never export private paths/groups."""
    dataset = _dataset()
    preflight = dataset.validate_dataset(manifest)
    inputs = dataset.load_manifest(manifest)
    dataset.validate_metadata(inputs)
    if batch_index is not None and (type(batch_index) is not int or batch_index < 0
                                    or batch_index * MAX_RECORDINGS >= len(inputs)):
        raise ValueError("Choose an existing nonnegative duration batch index")
    if len(inputs) > MAX_RECORDINGS and batch_index is None:
        preflight["ready_for_scoring"] = False
        preflight["issues"].append({"row": None, "code": "duration_batch_exceeds_five_recordings"})
    if not preflight["ready_for_scoring"]:
        return preflight, []
    # Validate the entire study before selecting a bounded inference batch. This
    # preserves cross-batch speaker/source leakage and duplicate-audio checks.
    start = (batch_index or 0) * MAX_RECORDINGS
    selected = inputs[start:start + MAX_RECORDINGS]
    if batch_index is not None:
        preflight["batch_selection"] = {
            "index": batch_index, "batch_size_limit": MAX_RECORDINGS,
            "study_recordings": len(inputs), "selected_recordings": len(selected),
            "batch_count": math.ceil(len(inputs) / MAX_RECORDINGS),
            "validation_scope": "entire_manifest_before_batch_selection",
        }
    _, decode = _runtime()
    recordings = []
    for index, item in enumerate(selected, start + 1):
        path = Path(item["wav"])
        if not path.is_absolute():
            path = manifest.parent / path
        with path.open("rb") as source:
            pcm, _ = decode(source.read(1_025_537))
        recordings.append({"id": f"recording-{index:03d}", "pcm": pcm,
                           **{key: item[key] for key in ("fixture", "label", "split", "language", "condition")}})
    return preflight, recordings


def _metrics(rows: list[dict]) -> dict:
    """One paired observation per source per duration; evaluation split only."""
    genuine = [row for row in rows if row["label"] == "genuine"]
    spoof = [row for row in rows if row["label"] == "spoof"]
    classified = [row for row in rows if row["status"] == "complete" and row["verdict"] in {"allow", "suspicious"}]
    false_alarm = sum(row["label"] == "genuine" and row["verdict"] == "suspicious" for row in classified)
    missed = sum(row["label"] == "spoof" and row["verdict"] == "allow" for row in classified)
    return {
        "source_recordings": len(rows), "genuine_recordings": len(genuine), "spoof_recordings": len(spoof),
        "classified": len(classified), "failed": sum(row["status"] != "complete" for row in rows),
        "unknown": sum(row["status"] == "complete" and row["verdict"] == "unknown" for row in rows),
        "false_alarms": false_alarm, "misses": missed,
        "false_alarms_over_all_genuine": false_alarm / len(genuine) if genuine else None,
        "misses_over_all_spoof": missed / len(spoof) if spoof else None,
        "classification_coverage": len(classified) / len(rows) if rows else None,
        "note": "Rates retain all labelled source recordings in denominators; report failed/unknown counts alongside them. Metadata checks do not independently verify labels or representativeness.",
    }


def compare(screener, recordings: list[dict], *, dataset_preflight: dict | None = None) -> dict:
    if not 1 <= len(recordings) <= MAX_RECORDINGS:
        raise ValueError("Compare one to five source recordings per bounded run")
    for recording in recordings:
        tiled_prefix(recording["pcm"], WINDOW_SAMPLES)
        if recording.get("fixture") is not True and (
                not dataset_preflight or dataset_preflight.get("ready_for_scoring") is not True):
            raise ValueError("Nonfixture comparisons require a strict dataset preflight")
    report = {**build_plan(), "record_type": "screening_duration_comparison", "plan_only": False,
              "dataset_preflight": dataset_preflight, "source_recording_count": len(recordings),
              "model": screener.status(), "results": [], "evaluation_by_duration": []}
    if not report["model"].get("ready"):
        report["status"] = "blocked_model_unavailable"
        return report
    report["status"] = "diagnostic_complete"
    # The production analyzer reports successfully scored windows, not failed
    # native-session attempts. Do not present wrapper calls as exact ONNX calls.
    report["inference_calls"] = None
    report["inference_count_note"] = "Analysis calls and successfully scored windows are counted; failed native inference attempts are not exposed by the analyzer."
    for recording in recordings:
        paired = []
        # Establish the native baseline first; every shorter result is compared to this exact source.
        for samples in (WINDOW_SAMPLES, *PREFIX_SAMPLES[:-1]):
            row = {key: recording[key] for key in ("id", "fixture", "label", "split", "language", "condition")}
            row.update(observed_audio_ms=samples * 1000 / SAMPLE_RATE,
                       model_input_ms=WINDOW_SAMPLES * 1000 / SAMPLE_RATE,
                       model_input_samples=WINDOW_SAMPLES, repeated_samples=WINDOW_SAMPLES - samples,
                       strategy="native_full_window" if samples == WINDOW_SAMPLES else "prefix_tile_repeat",
                       status="error", verdict="unknown", score=None, compute_ms=None,
                       score_delta_from_full=None, verdict_agrees_with_full=None)
            report["analysis_calls"] += 1
            try:
                result = screener.analyze(tiled_prefix(recording["pcm"], samples), SAMPLE_RATE).as_dict()
                score = result["score"]
                if (result["verdict"] not in {"allow", "suspicious", "unknown"}
                        or score is None and result["verdict"] != "unknown"
                        or score is not None and (isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1)):
                    raise ValueError("Invalid local result")
                row.update(status="complete", verdict=result["verdict"], score=score,
                           compute_ms=result["compute_ms"], reasons=result["reasons"])
                report["successfully_scored_model_windows"] += result.get("windows_analyzed", 0)
            except Exception:
                row["error"] = "local_analysis_failed"
            paired.append(row)
        baseline = paired[0]
        for row in paired:
            if row["status"] == baseline["status"] == "complete":
                row["verdict_agrees_with_full"] = row["verdict"] == baseline["verdict"]
                if row["score"] is not None and baseline["score"] is not None:
                    row["score_delta_from_full"] = round(row["score"] - baseline["score"], 6)
        report["results"].extend(sorted(paired, key=lambda row: row["observed_audio_ms"]))
    short_rows = [row for row in report["results"] if row["repeated_samples"]]
    report["paired_short_comparisons"] = len(short_rows)
    report["verdict_changes_from_native"] = sum(row["verdict_agrees_with_full"] is False for row in short_rows)
    report["comparisons_missing_baseline_or_result"] = sum(row["verdict_agrees_with_full"] is None for row in short_rows)
    if dataset_preflight is not None:
        report["status"] = "labelled_exploratory_comparison"
        for samples in PREFIX_SAMPLES:
            held_out = [row for row in report["results"] if row["observed_audio_ms"] == samples * 1000 / SAMPLE_RATE
                        and row["split"] == "evaluation" and row["fixture"] is False]
            report["evaluation_by_duration"].append({
                "observed_audio_ms": samples * 1000 / SAMPLE_RATE,
                "scope": "declared_held_out_evaluation_only", **_metrics(held_out),
                "by_language": {language: _metrics([row for row in held_out if row["language"] == language])
                                for language in sorted({row["language"] for row in held_out})},
            })
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=lambda prog: argparse.HelpFormatter(prog, width=88))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--diagnostics", action="store_true")
    mode.add_argument("--manifest", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--batch-index", type=int, help="Explicit zero-based five-recording batch; validates the entire manifest first")
    args = parser.parse_args(argv)
    try:
        if args.output and args.output.exists():
            raise ValueError("Preserve an existing report")
        report = build_plan()
        exit_code = 0
        if args.batch_index is not None and not args.manifest:
            raise ValueError("Batch selection requires a manifest")
        if args.manifest:
            preflight, recordings = strict_recordings(args.manifest, args.batch_index)
            if not preflight["ready_for_scoring"]:
                report.update(record_type="screening_duration_preflight", status="blocked_dataset",
                              dataset_preflight=preflight)
                exit_code = 2
            else:
                factory, _ = _runtime()
                report = compare(factory(args.model), recordings, dataset_preflight=preflight)
        elif args.diagnostics:
            factory, _ = _runtime()
            report = compare(factory(args.model), diagnostic_recordings())
        if report.get("status") == "blocked_model_unavailable":
            exit_code = 2
        encoded = json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as output:
                output.write(encoded)
            print("Saved local duration report; no live screening setting changed.")
        else:
            print(encoded, end="")
        return exit_code
    except (ValueError, OSError, KeyError, TypeError):
        print("Invalid duration experiment inputs or output. No provider request was made.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
