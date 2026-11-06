"""Bounded server timing summaries, deliberately separate from listener playback."""
from __future__ import annotations

import math
from collections import defaultdict

from ..models import PerformanceSample, now
from ..store import MAX_PERFORMANCE_SAMPLES, RoomState


def milliseconds(value: float | None) -> float | None:
    if value is None or not math.isfinite(value) or value < 0:
        return None
    return round(value, 2)


def percentile(values: list[float], proportion: float) -> float | None:
    """Nearest rank, including p95 of very small samples without interpolation."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * proportion) - 1)]


def counts(samples: list[PerformanceSample]) -> dict:
    measured = [sample.total_ms for sample in samples
                if sample.status == "complete"
                and sample.measurement == "server_first_pcm"
                and sample.total_ms is not None]
    audio = [sample for sample in samples if sample.status == "complete"
             and sample.measurement == "server_first_pcm" and sample.input_kind == "audio"]
    source_intervals = [sample.source_end_to_first_pcm_ms for sample in audio
                        if sample.source_end_to_first_pcm_ms is not None]
    return {
        "sample_count": len(samples),
        "success_count": sum(sample.status == "complete" for sample in samples),
        "error_count": sum(sample.status == "error" for sample in samples),
        "cancelled_count": sum(sample.status == "cancelled" for sample in samples),
        "live_sample_count": len(measured),
        "p50_ms": percentile(measured, 0.5),
        "p95_ms": percentile(measured, 0.95),
        "audio_sample_count": len(audio),
        "stt_measured_count": sum(sample.stt_ms is not None for sample in audio),
        "source_end_measured_count": len(source_intervals),
        "source_end_to_first_pcm_p50_ms": percentile(source_intervals, .5),
        "source_end_to_first_pcm_p95_ms": percentile(source_intervals, .95),
    }


def performance_snapshot(state: RoomState) -> dict:
    samples = list(state.performance_samples)
    grouped = defaultdict(list)
    for sample in samples:
        grouped[(sample.source_language, sample.target_language)].append(sample)
    return {
        "room_code": state.room.code,
        "mode": state.room.mode,
        "generated_at": now().isoformat(),
        "measurement": {
            "boundary": "server_first_pcm",
            "stt": "processing_to_transcript",
            "total": "queue_to_first_pcm_plus_stt",
            "total_coverage": "partial_when_stt_missing",
            "source_boundary": "server_ingress_energy_end",
            "source_boundary_kind": "energy_estimate_not_microphone_or_acoustic",
            "receiver_playback_measured": False,
            "retention_limit": MAX_PERFORMANCE_SAMPLES,
        },
        "summary": {
            **counts(samples),
            "forwarded_count": sum(sample.measurement == "source_forwarded" for sample in samples),
            "simulated_count": sum(sample.measurement == "simulated" for sample in samples),
            "by_direction": [
                {"source_language": source, "target_language": target, **counts(rows)}
                for (source, target), rows in sorted(grouped.items())
            ],
        },
        "samples": [sample.model_dump(mode="json") for sample in samples],
    }
