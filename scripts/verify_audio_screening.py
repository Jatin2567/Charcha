"""Zero-credit local classifier smoke/latency check; synthetic fixtures, not accuracy.

No microphone capture, audio upload, model download, or API access occurs here.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "evaluation"))

from charcha.services.audio_screening import LocalAudioScreener, WINDOW_SAMPLES  # noqa: E402
from audio_screening import summarize  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--cpu-threads", type=int, choices=(1, 2, 4), default=1)
    parser.add_argument("--output", type=Path, default=ROOT / "work" / "audio-screening-smoke.json")
    args = parser.parse_args()
    started = time.perf_counter()
    screener = LocalAudioScreener(args.model, cpu_threads=args.cpu_threads)
    load_ms = (time.perf_counter() - started) * 1000
    t = np.arange(WINDOW_SAMPLES) / 16000
    tone = (.2 * np.sin(2 * np.pi * 220 * t) * 32767).astype("<i2").tobytes()
    fixtures = {"silence": bytes(WINDOW_SAMPLES * 2), "short_tone": tone[:12800],
                "steady_tone": tone,
                "chirp": (.2 * np.sin(2 * np.pi * (100 * t + 40 * t * t)) * 32767).astype("<i2").tobytes(),
                "clipped": np.tile(np.array([-32768, 32767], dtype="<i2"), WINDOW_SAMPLES // 2).tobytes()}
    rows = []
    for name, pcm in fixtures.items():
        result = screener.analyze(pcm)
        rows.append({"id": name, "label": "unlabelled", "fixture": True, "status": "complete", **result.as_dict()})
    # Fixed-window repeated inference quantifies CPU scheduling cost, not end-to-end latency.
    repeats = [screener.analyze(tone).compute_ms for _ in range(5)] if screener.status()["ready"] else []
    payload = {"schema_version": 1, "provider_calls": 0, "paid_servers": 0,
               "model": screener.status(), "model_load_ms": round(load_ms, 3),
               "window_ms": screener.window_ms, "warm_compute_ms": repeats,
               "evidence": "Synthetic signal fixtures verify execution and abstention only; they do not test speech deepfake accuracy.",
               "summary": summarize(rows), "fixtures": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k != "fixtures"}, indent=2))
    if not screener.status()["ready"]:
        print("Classifier unavailable; diagnostics still tested. Install the screening extra and run the explicit model download script.")


if __name__ == "__main__":
    main()
