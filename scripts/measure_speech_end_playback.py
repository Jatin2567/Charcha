"""Offline shared-recording measurement. Never captures audio or calls a provider.

Default: print the measurement plan. Analysis needs one shared-clock PCM16 recording
and explicit sample annotations; hardware/provider provenance is operator-attested.
"""
from __future__ import annotations

import argparse
from array import array
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import wave

LANGUAGES = frozenset(("hi", "ta", "bn", "en", "te", "kn", "ml", "mr", "gu", "pa"))
CAPTURES = {"acoustic_two_channel", "electrical_loopback_two_channel", "browser_render_dual_channel",
            "acoustic_single_channel"}
PHYSICAL = CAPTURES - {"browser_render_dual_channel"}
FIELDS = {"recording_sha256", "trial_id", "source_language", "target_language", "condition",
          "provider_kind", "capture_kind", "voice_mode", "status", "source_speech_end_sample",
          "listener_audio_start_sample", "capture_attested", "annotations_reviewed", "meaning_reviewed"}


class Rejected(ValueError):
    pass


def plan() -> dict:
    return {"schema_version": 1, "record_type": "speech_end_playback_plan", "plan_only": True,
            "provider_calls": 0, "hardware_capture_started": False,
            "clock": "single_recording_sample_index", "boundary": "source_speech_end_to_listener_output",
            "format": "One shared-clock PCM16 WAV, 8–96 kHz, at most 120 seconds/60 MiB. Prefer isolated stereo; mono is accepted only for acoustic_single_channel.",
            "channels": {"left": "isolated source speech reference", "right": "isolated listener output",
                         "acoustic_single_channel": "one shared acoustic channel, manually distinguish source and listener turns"},
            "annotations": {"source_speech_end_sample": "first sample after the final voiced source sample",
                            "listener_audio_start_sample": "first translated output sample; null on failure"},
            "latency": "(listener_audio_start_sample - source_speech_end_sample) / sample_rate_hz * 1000",
            "signed_offsets": True, "target_ms": 2000, "acceptance": "not_verified",
            "provenance": "Capture, provider identity and review flags are operator attestations, not authenticated proof.",
            "privacy": "No microphone, system-audio capture, model invocation, settings or ledger access."}


def analyze(wav_path: Path, annotations: dict) -> dict:
    if not isinstance(annotations, dict) or set(annotations) - {"screening_mode"} != FIELDS:
        raise Rejected("Use exactly the documented annotation fields.")
    screening_mode = annotations.get("screening_mode", "off")
    if screening_mode not in ("off", "monitor", "enforce"):
        raise Rejected("Use the VoiceShield mode shown in the measured room.")
    for name in ("capture_attested", "annotations_reviewed", "meaning_reviewed"):
        if type(annotations[name]) is not bool:
            raise Rejected("Review and capture flags must be explicit booleans.")
    if (annotations["source_language"] not in LANGUAGES or annotations["target_language"] not in LANGUAGES
            or annotations["source_language"] == annotations["target_language"]
            or annotations["condition"] not in ("first_route", "warm_route")
            or annotations["provider_kind"] not in ("live", "double")
            or annotations["capture_kind"] not in CAPTURES or annotations["voice_mode"] != "standard"
            or annotations["status"] not in ("complete", "error", "timeout")
            or not isinstance(annotations["trial_id"], str)
            or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", annotations["trial_id"])):
        raise Rejected("Use the supported standard-voice measurement metadata.")
    if not wav_path.is_file() or wav_path.stat().st_size > 60 * 1024 * 1024:
        raise Rejected("The shared recording is missing or exceeds the supported size.")
    digest = hashlib.sha256(wav_path.read_bytes()).hexdigest()
    if annotations["recording_sha256"] != digest:
        raise Rejected("The recording does not match the reviewed SHA-256.")
    channels = 1 if annotations["capture_kind"] == "acoustic_single_channel" else 2
    output_channel = 0 if channels == 1 else 1
    try:
        with wave.open(str(wav_path), "rb") as audio:
            rate, frames = audio.getframerate(), audio.getnframes()
            if (audio.getnchannels() != channels or audio.getsampwidth() != 2 or audio.getcomptype() != "NONE"
                    or not 8000 <= rate <= 96000 or not 0 < frames <= rate * 120):
                raise Rejected("Use bounded PCM16 at 8–96 kHz: mono only for acoustic_single_channel; other captures need two-channel PCM16.")
            raw = audio.readframes(frames + 1)
            if len(raw) != frames * channels * 2:
                raise Rejected("The recording has incomplete sample data.")
            pcm = array("h", raw)
    except (wave.Error, EOFError):
        raise Rejected("The shared recording is not valid PCM16 WAV.") from None
    if sys.byteorder != "little":
        pcm.byteswap()
    if len(pcm) != frames * channels:
        raise Rejected("The recording has incomplete sample data.")
    source_end, output_start = annotations["source_speech_end_sample"], annotations["listener_audio_start_sample"]
    if type(source_end) is not int or not 0 < source_end <= frames:
        raise Rejected("Source speech end must be a sample index inside the recording.")
    complete = annotations["status"] == "complete"
    if (complete and (type(output_start) is not int or not 0 <= output_start < frames)
            or not complete and output_start is not None):
        raise Rejected("A completed output needs an onset index; failed outputs must leave it null.")
    # A local consistency check only. Nonzero PCM does not establish speech,
    # semantic correctness, acoustic capture or an appropriate annotation.
    window = max(1, rate // 50)
    if not any(pcm[max(0, source_end - window) * channels:source_end * channels:channels]):
        raise Rejected("No source reference signal exists near the annotated end.")
    if complete and not any(pcm[output_start * channels + output_channel:min(frames, output_start + window) * channels:channels]):
        raise Rejected("No listener signal exists near the annotated onset.")
    identity = {"recording_sha256": digest, "source_end": source_end, "output_start": output_start,
                "source_language": annotations["source_language"], "target_language": annotations["target_language"]}
    observation_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    physical = (complete and annotations["capture_kind"] in PHYSICAL
                and annotations["capture_attested"] and annotations["annotations_reviewed"])
    return {"schema_version": 1, "record_type": "speech_end_playback_observation",
            "observation_id": observation_id, "recording_sha256": digest,
            "recorded_on": datetime.now(timezone.utc).date().isoformat(),
            "clock": "single_recording_sample_index", "boundary": "source_speech_end_to_listener_output",
            "sample_rate_hz": rate, "recording_frames": frames, "recording_channels": channels,
            "source_channel_index": 0, "listener_channel_index": output_channel,
            **{name: annotations[name] for name in FIELDS if name != "recording_sha256"},
            "latency_ms": round((output_start - source_end) * 1000 / rate, 4) if complete else None,
            "annotation_resolution_ms": round(1000 / rate, 6),
            "physical_playback_measured": bool(physical), "capture_provenance": "operator_attested",
            "provider_provenance": "operator_attested", "screening_mode": screening_mode, "voice_cloning": False,
            "target_ms": 2000, "acceptance": "requires_aggregate_gate_and_human_review",
            "limitations": ["Provenance and meaning review are operator attestations, not verified from PCM.",
                "Prefer isolated reference/output channels; crosstalk or other system sounds can invalidate onset annotations.",
                "For single-channel acoustic capture, identify both turns by waveform and listening in a quiet room; mixed or overlapping voices cannot establish a clean latency acceptance result.",
                "Sample resolution is not a bound on annotation, capture-path or hardware error.",
                "Negative offsets are retained as overlap and need review; they are never clamped to zero."]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--wav", type=Path)
    parser.add_argument("--annotations", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if not args.analyze:
            print(json.dumps(plan(), indent=2))
            return 0
        if not args.wav or not args.annotations or not args.output or args.output.exists():
            raise Rejected("Analysis needs a WAV, annotations and a fresh output path.")
        if args.annotations.stat().st_size > 16384:
            raise Rejected("Annotation file is too large.")
        result = analyze(args.wav, json.loads(args.annotations.read_text(encoding="utf-8")))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as output:
            json.dump(result, output, indent=2, allow_nan=False)
        print(json.dumps({"record_type": result["record_type"], "status": result["status"],
                          "latency_ms": result["latency_ms"], "capture_provenance": "operator_attested"}))
        return 0
    except (Rejected, OSError, ValueError, TypeError):
        print("Measurement was not imported; check the shared WAV, annotations and fresh output path.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
