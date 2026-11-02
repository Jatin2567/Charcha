"""Local fixed-window CPU timing/parity experiment; never an accuracy benchmark.

Uses only the installed, checksum-pinned model and deterministic synthetic PCM.
No download, microphone, provider access or production configuration change.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gc
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from artha_mesh.services.audio_screening import (  # noqa: E402
    DEFAULT_MODEL, MODEL_ID, MODEL_REVISION, MODEL_SHA256, SAMPLE_RATE,
    WINDOW_SAMPLES, LocalAudioScreener,
)

LOGIT_ATOL = 1e-5
SCORE_ATOL = 1e-6


def validate_options(threads, repeats, wall_seconds):
    if (not isinstance(threads, (list, tuple)) or not threads or threads[0] != 1
            or len(threads) != len(set(threads))
            or any(type(value) is not int or value not in (1, 2, 4) for value in threads)):
        raise ValueError("Compare unique CPU thread counts from 1, 2, 4, with 1 first")
    if type(repeats) is not int or not 1 <= repeats <= 10:
        raise ValueError("Use 1–10 warm repeats per fixture")
    if type(wall_seconds) not in (int, float) or not np.isfinite(wall_seconds) or not 10 <= wall_seconds <= 180:
        raise ValueError("Use a 10–180 second local experiment budget")


def fixtures():
    """Exact-length synthetic diagnostics, with no human/generated speech labels."""
    t = np.arange(WINDOW_SAMPLES, dtype=np.float64) / SAMPLE_RATE
    rng = np.random.default_rng(20261029)
    envelope = .55 + .35 * np.sin(2 * np.pi * 3.7 * t)
    carrier = sum(np.sin(2 * np.pi * 137 * harmonic * t) / harmonic for harmonic in range(1, 7))
    samples = {
        "steady_tone": .18 * np.sin(2 * np.pi * 220 * t),
        "chirp": .18 * np.sin(2 * np.pi * (100 * t + 40 * t * t)),
        "harmonic_envelope_not_speech": .13 * envelope * carrier,
        "seeded_noise": .07 * rng.standard_normal(WINDOW_SAMPLES),
    }
    result = []
    for name, signal in samples.items():
        pcm = np.clip(signal * 32767, -32768, 32767).astype("<i2").tobytes()
        waveform = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
        waveform.flags.writeable = False
        result.append({"id": name, "pcm": pcm, "waveform": waveform,
                       "pcm_sha256": hashlib.sha256(pcm).hexdigest()})
    return result


def verify_model(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 4_000_000:
        raise ValueError("Installed bounded AASIST model is required")
    if hashlib.sha256(path.read_bytes()).hexdigest() != MODEL_SHA256:
        raise ValueError("Installed AASIST checksum differs from the reviewed export")


def create_session(path, threads):
    import onnxruntime as ort

    ort.disable_telemetry_events()
    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.log_severity_level = 3
    options.add_session_config_entry("session.intra_op.allow_spinning", "0")
    session = ort.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"])
    inputs, outputs = session.get_inputs(), session.get_outputs()
    if (len(inputs) != 1 or inputs[0].name != "wav"
            or inputs[0].shape[-1] != WINDOW_SAMPLES or inputs[0].type != "tensor(float)"
            or len(outputs) != 1 or outputs[0].name != "logits"):
        raise ValueError("Unsupported pinned model input/output contract")
    return session


def infer(session, waveform):
    logits = np.asarray(session.run(["logits"], {"wav": waveform[None, :]})[0], dtype=np.float64)
    if logits.shape != (1, 2) or not np.all(np.isfinite(logits)):
        raise ValueError("Invalid model logits")
    # Copy avoids mutating the raw logits used for strict numerical comparison.
    stable = logits - logits.max(axis=1, keepdims=True)
    exponent = np.exp(stable)
    score = float(exponent[0, 0] / exponent.sum())
    verdict = "suspicious" if score >= .8 else "allow" if score <= .2 else "unknown"
    return logits, score, verdict


def summary(values):
    return {"count": len(values), "median_ms": statistics.median(values) if values else None,
            "min_ms": min(values) if values else None, "max_ms": max(values) if values else None}


def choose_candidate(configurations, *, complete):
    """Require numerical parity and improvement on every diagnostic, never auto-enable."""
    if not complete or len(configurations) < 2:
        return None
    baseline = configurations[0]
    candidates = []
    for candidate in configurations[1:]:
        if (candidate["parity_passed"]
                and candidate["kernel_summary"]["median_ms"] <= .9 * baseline["kernel_summary"]["median_ms"]
                and candidate["analysis_summary"]["median_ms"] <= .9 * baseline["analysis_summary"]["median_ms"]
                and all(c["kernel_summary"]["median_ms"] <= b["kernel_summary"]["median_ms"]
                        and c["analysis_summary"]["median_ms"] <= b["analysis_summary"]["median_ms"]
                        for c, b in zip(candidate["fixtures"], baseline["fixtures"], strict=True))):
            candidates.append(candidate)
    return min(candidates, key=lambda row: row["kernel_summary"]["median_ms"])["threads"] if candidates else None


def benchmark(path=DEFAULT_MODEL, *, threads=(1, 2, 4), repeats=5, wall_seconds=120,
              session_factory=None, timer=None):
    validate_options(threads, repeats, wall_seconds)
    verify_model(path)
    timer = time.perf_counter if timer is None else timer
    session_factory = create_session if session_factory is None else session_factory
    data = fixtures()
    started = timer()
    deadline = started + wall_seconds
    references, configurations = {}, []
    complete = True
    for thread_count in threads:
        if timer() >= deadline:
            complete = False
            break
        load_started = timer()
        session = session_factory(path, thread_count)
        load_ms = (timer() - load_started) * 1000
        # Reuse production conversion/DSP/gating for end-to-end analysis timing.
        screener = LocalAudioScreener(load_model=False)
        screener._session = session
        screener._model.update(id=MODEL_ID, revision=MODEL_REVISION, sha256=MODEL_SHA256,
                               ready=True, kind="onnx_classifier")
        first_started = timer()
        infer(session, data[0]["waveform"])
        first_ms = (timer() - first_started) * 1000
        rows, kernel_values, analyze_values = [], [], []
        parity_passed = True
        for fixture in data:
            logits, score, verdict = infer(session, fixture["waveform"])
            if thread_count == 1:
                references[fixture["id"]] = (logits.copy(), score, verdict)
            ref_logits, ref_score, ref_verdict = references[fixture["id"]]
            logit_difference = float(np.max(np.abs(logits - ref_logits)))
            score_difference = abs(score - ref_score)
            verdict_equal = verdict == ref_verdict
            fixture_kernel, fixture_analyze = [], []
            for _ in range(repeats):
                if timer() >= deadline:
                    complete = False
                    break
                attempt = timer()
                observed_logits, observed_score, observed_verdict = infer(session, fixture["waveform"])
                fixture_kernel.append((timer() - attempt) * 1000)
                logit_difference = max(logit_difference, float(np.max(np.abs(observed_logits - ref_logits))))
                score_difference = max(score_difference, abs(observed_score - ref_score))
                verdict_equal = verdict_equal and observed_verdict == ref_verdict
                attempt = timer()
                result = screener.analyze(fixture["pcm"])
                fixture_analyze.append((timer() - attempt) * 1000)
                verdict_equal = verdict_equal and result.verdict == ref_verdict
            passed = logit_difference <= LOGIT_ATOL and score_difference <= SCORE_ATOL and verdict_equal
            parity_passed = parity_passed and passed
            kernel_values.extend(fixture_kernel)
            analyze_values.extend(fixture_analyze)
            rows.append({"id": fixture["id"], "label": "unlabelled_synthetic_diagnostic",
                         "pcm_sha256": fixture["pcm_sha256"], "samples": WINDOW_SAMPLES,
                         "score": score, "verdict": verdict,
                         "max_abs_raw_logit_difference": logit_difference,
                         "max_abs_unrounded_score_difference": score_difference,
                         "verdict_parity": verdict_equal, "parity_passed": passed,
                         "kernel_ms": fixture_kernel, "analysis_ms": fixture_analyze,
                         "kernel_summary": summary(fixture_kernel), "analysis_summary": summary(fixture_analyze)})
            if not complete:
                break
        configurations.append({"threads": thread_count, "model_init_ms": load_ms,
                               "first_kernel_call_ms": first_ms, "parity_passed": parity_passed,
                               "fixtures": rows, "kernel_summary": summary(kernel_values),
                               "analysis_summary": summary(analyze_values)})
        del screener, session
        gc.collect()
        if not complete:
            break
    complete = complete and len(configurations) == len(threads)
    candidate = choose_candidate(configurations, complete=complete)
    return {"schema_version": 1, "record_type": "fixed_window_cpu_compute_experiment",
            "recorded_at": datetime.now(timezone.utc).isoformat(), "model_sha256": MODEL_SHA256,
            "sample_rate": SAMPLE_RATE, "window_samples": WINDOW_SAMPLES,
            "window_ms": WINDOW_SAMPLES * 1000 / SAMPLE_RATE, "repeats_per_fixture": repeats,
            "fixture_count": len(data), "elapsed_ms": (timer() - started) * 1000,
            "complete": complete, "logit_absolute_tolerance": LOGIT_ATOL,
            "score_absolute_tolerance": SCORE_ATOL, "configurations": configurations,
            "candidate_threads_for_review": candidate, "production_configuration_changed": False,
            "accuracy": None, "representative_speech_accuracy_tested": False,
            "provider_calls": 0, "model_downloads": 0, "voice_cloning": False,
            "note": "Diagnostic numerical parity is not accuracy validation. Audio evidence remains 4037.5 ms; compute tuning cannot remove that collection delay. Small repeat medians are descriptive, not latency guarantees."}


def benchmark_concurrency(path=DEFAULT_MODEL, *, threads=(1, 2), repeats=3, wall_seconds=90,
                          session_factory=None):
    """Two concurrent callers mirror the runtime's two-worker admission bound."""
    from concurrent.futures import ThreadPoolExecutor
    import threading

    validate_options(threads, repeats, wall_seconds)
    verify_model(path)
    session_factory = create_session if session_factory is None else session_factory
    data, references, configurations = fixtures(), {}, []
    started = time.perf_counter()
    deadline = started + wall_seconds
    complete = True
    for thread_count in threads:
        session = session_factory(path, thread_count)
        for fixture in data:
            logits, score, verdict = infer(session, fixture["waveform"])
            if thread_count == 1:
                references[fixture["id"]] = (logits, score, verdict)
        thread_results = threading.local()

        class TrackingSession:
            def run(self, names, inputs):
                before = time.perf_counter()
                outputs = session.run(names, inputs)
                # Capture a copy before production softmax processing; per-thread
                # storage prevents a concurrent caller overwriting the evidence.
                thread_results.raw_logits = np.asarray(outputs[0], dtype=np.float64).copy()
                thread_results.kernel_ms = (time.perf_counter() - before) * 1000
                return outputs

        screener = LocalAudioScreener(load_model=False)
        screener._session = TrackingSession()
        screener._model.update(ready=True, kind="onnx_classifier", sha256=MODEL_SHA256)
        pairs, rows = [], []

        def analyze_one(fixture, barrier):
            barrier.wait(timeout=10)
            before = time.perf_counter()
            result = screener.analyze(fixture["pcm"])
            elapsed = (time.perf_counter() - before) * 1000
            logits = thread_results.raw_logits
            if logits.shape != (1, 2) or not np.all(np.isfinite(logits)):
                raise ValueError("Invalid concurrent model logits")
            exponent = np.exp(logits - logits.max(axis=1, keepdims=True))
            score = float(exponent[0, 0] / exponent.sum())
            expected_logits, expected_score, expected_verdict = references[fixture["id"]]
            raw_difference = float(np.max(np.abs(logits - expected_logits)))
            score_difference = abs(score - expected_score)
            return {"id": fixture["id"], "pcm_sha256": fixture["pcm_sha256"],
                    "analysis_ms": elapsed, "kernel_ms": thread_results.kernel_ms,
                    "max_abs_raw_logit_difference": raw_difference,
                    "max_abs_unrounded_score_difference": score_difference,
                    "verdict_parity": result.verdict == expected_verdict,
                    "parity_passed": raw_difference <= LOGIT_ATOL and score_difference <= SCORE_ATOL
                        and result.verdict == expected_verdict}

        with ThreadPoolExecutor(max_workers=2) as pool:
            for _ in range(repeats):
                for offset in (0, 2):
                    if time.perf_counter() >= deadline:
                        complete = False
                        break
                    barrier = threading.Barrier(2)
                    before = time.perf_counter()
                    futures = [pool.submit(analyze_one, fixture, barrier) for fixture in data[offset:offset + 2]]
                    rows.extend(future.result() for future in futures)
                    pairs.append((time.perf_counter() - before) * 1000)
                if not complete:
                    break
        configurations.append({"threads": thread_count, "concurrent_callers": 2,
                               "analysis_summary": summary([row["analysis_ms"] for row in rows]),
                               "kernel_summary": summary([row["kernel_ms"] for row in rows]),
                               "pair_wall_summary": summary(pairs), "pair_wall_ms": pairs,
                               "observations": rows, "parity_passed": all(row["parity_passed"] for row in rows)})
        del screener, session
        gc.collect()
        if not complete:
            break
    return {"schema_version": 1, "record_type": "two_inflight_fixed_window_cpu_experiment",
            "recorded_at": datetime.now(timezone.utc).isoformat(), "model_sha256": MODEL_SHA256,
            "window_samples": WINDOW_SAMPLES, "window_ms": WINDOW_SAMPLES * 1000 / SAMPLE_RATE,
            "concurrent_callers": 2, "repeats_per_pair": repeats, "configurations": configurations,
            "elapsed_ms": (time.perf_counter() - started) * 1000, "complete": complete,
            "provider_calls": 0, "model_downloads": 0, "production_configuration_changed": False,
            "accuracy": None, "representative_speech_accuracy_tested": False,
            "note": "Two concurrent calls use the same full evidence window, session and diagnostic waveforms. Numerical parity does not establish speech accuracy. Pair wall includes worker scheduling and both full analyses."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--threads", type=int, nargs="+", default=[1, 2, 4])
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--wall-seconds", type=float, default=120)
    parser.add_argument("--concurrent", action="store_true", help="Compare two in-flight production analyses per session")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise ValueError("Choose a new output file")
        runner = benchmark_concurrency if args.concurrent else benchmark
        report = runner(args.model, threads=args.threads, repeats=args.repeats, wall_seconds=args.wall_seconds)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as output:
            output.write(json.dumps(report, indent=2, allow_nan=False) + "\n")
        print(json.dumps({"complete": report["complete"], "window_ms": report["window_ms"],
                          "candidate_threads_for_review": report.get("candidate_threads_for_review"),
                          "configurations": [{"threads": c["threads"], "kernel": c["kernel_summary"],
                                              "analysis": c["analysis_summary"], "parity": c["parity_passed"]}
                                             for c in report["configurations"]]}, indent=2))
        return 0 if report["complete"] else 1
    except (ValueError, OSError, ImportError):
        print("Local experiment could not run; check model, bounds and fresh output path.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
