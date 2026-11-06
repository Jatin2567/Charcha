"""Offline-first single-clock source-end -> decoded RTC measurement with doubles.

Default planning imports no application settings or SDK, opens no ledger and
makes no network request. --run-local uses only loopback LiveKit and synthetic
PCM; it never loads provider credentials or invokes a speech/translation model.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import time
import traceback
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
RATE, FRAME = 16000, 320


def plan():
    return {"schema_version": 1, "record_type": "local_speech_end_latency_plan", "plan_only": True,
            "provider_calls": 0, "network": "Only --run-local connects to ws://127.0.0.1:7880.",
            "source_language": "hi", "target_language": "ta", "trials": 11,
            "conditions": {"first_route": 1, "warm_route": 10},
            "clock": "single_process_monotonic", "boundary": "source_end_to_first_decoded_rtc",
            "source_end_reference": "last_voiced_source_frame_playout",
            "fixture": {"recognition_silence_ms": 600, "translation_delay_ms": 100,
                        "tts_first_chunk_delay_ms": 50, "source_ms": 600},
            "physical_playback_measured": False, "target_ms": 2000, "acceptance": "not_verified",
            "voice_cloning": False, "screening_mode": "off"}


def percentile(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def curate_result(result, source_sha256):
    """Construct the public record; never forward nested diagnostic fields."""
    fields = {"schema_version", "record_type", "recorded_on", "evidence_kind", "clock", "boundary",
              "source_end_reference", "physical_playback_measured", "provider_calls", "screening_mode",
              "voice_cloning", "target_ms", "acceptance"}
    sample_fields = {"trial_id", "condition", "source_language", "target_language", "status",
                     "source_end_to_decoded_ms", "source_end_to_render_estimate_ms",
                     "source_end_to_physical_playback_ms"}
    summary_fields = {"attempted", "completed", "failed", "p50_decoded_ms", "p95_decoded_ms"}
    public = {field: result[field] for field in fields}
    public["samples"] = [{field: row[field] for field in sample_fields} for row in result["samples"]]
    public["summary"] = {field: result["summary"][field] for field in summary_fields}
    public["limitations"] = [
        "Synthetic tones and provider doubles, not human speech or Gnani/Evon performance.",
        "Known source-frame SDK playout to received decoded PCM on one process clock; no physical microphone or speaker.",
        "20-ms decoder frames and callback scheduling limit timing precision.",
        "The fixture waits for 600 ms of silence, then uses fixed 100-ms MT and 50-ms TTS delays.",
        "First-route and warm-route conditions stay separate; failures remain in the attempted counts.",
        "Intertrial quiet is fixture pacing, not a measured receiver-silence guarantee.",
        "No render estimate, acoustic result, meaning acceptance or under-two-second live claim is inferred."]
    public["source_report_sha256"] = source_sha256
    return public


class Fixture:
    def __init__(self):
        self.ready = asyncio.Event()
        self.translations = 0
        self.syntheses = 0
        self.recognitions = 0

    async def transcribe(self, audio, language, on_processing=None):
        self.ready.set()
        voiced, quiet, index = False, 0, 0
        async for chunk in audio:
            signal = any(abs(value) > 200 for value in memoryview(chunk).cast("h"))
            if signal:
                voiced, quiet = True, 0
            elif voiced:
                quiet += len(chunk) // 2
                if quiet >= RATE * .6:
                    index += 1
                    self.recognitions += 1
                    voiced, quiet = False, 0
                    if on_processing:
                        on_processing()
                    yield SimpleNamespace(text=f"Synthetic source trial {index}", segment_id=str(index), stt_ms=0)

    async def translate(self, text, source, target):
        self.translations += 1
        await asyncio.sleep(.1)
        return "Synthetic target fixture"

    async def synthesize(self, text, language, embedding=None):
        assert embedding is None
        self.syntheses += 1
        await asyncio.sleep(.05)
        # The deliberately short first chunk exercises immediate PCM dispatch.
        total, offset = 24000 // 5, 0
        while offset < total:
            size = min(240 if offset == 0 else 480, total - offset)
            yield struct.pack("<" + "h" * size, *[
                int(5000 * math.sin(2 * math.pi * 1100 * n / 24000)) for n in range(offset, offset + size)])
            offset += size


async def run_local():
    # These imports occur only on the explicit local execution path.
    sys.path.insert(0, str(ROOT / "server"))
    from livekit import rtc
    from charcha.config import Settings
    from charcha.models import JoinRoom, UpdateParticipant
    from charcha.services.pipeline import Pipeline
    from charcha.services.rooms import RoomService
    from charcha.store import Store
    from charcha.transport.livekit import TransportManager

    settings = Settings(_env_file=None, mode="live", livekit_url="ws://127.0.0.1:7880",
        livekit_internal_url="ws://127.0.0.1:7880", livekit_api_key="devkey", livekit_api_secret="secret",
        # Required presence checks use inert sentinels. No real provider class
        # is constructed, and the unusable endpoint is never contacted.
        gnani_api_key="test-double-never-sent", evon_base_url="http://127.0.0.1:9/v1",
        evon_api_key="", evon_model="synthetic-test-double",
        evon_modal_key="", evon_modal_secret="", audio_screening_mode="off",
        usage_require_flow_approval=False, usage_stt_max_retries=0,
        usage_db_path=ROOT / "work/local/speech-end-fixture.sqlite3")
    fixture, store = Fixture(), Store(settings)
    pipeline = Pipeline(store, fixture, fixture)
    transport = TransportManager(store, fixture, pipeline)
    pipeline.transport = transport
    service = RoomService(store, pipeline, transport, None)
    state = store.create_room("Synthetic speech-end timing")
    clients, streams, tasks, cleanup_errors, samples = [], [], [], [], []
    source = None
    fixture_error = None
    current = {"trial": None, "detected_at": None, "end_at": None}
    detected = asyncio.Event()
    started = time.perf_counter()

    async def observe(track):
        stream = rtc.AudioStream(track, sample_rate=RATE, num_channels=1, capacity=8, frame_size_ms=20)
        streams.append(stream)
        try:
            async for event in stream:
                if current["trial"] is not None and current["detected_at"] is None:
                    if any(abs(value) > 200 for value in event.frame.data.cast("B").cast("h")):
                        current["detected_at"] = time.perf_counter()
                        detected.set()
        finally:
            await stream.aclose()
            streams.remove(stream)

    try:
        sender = await service.join(state.room.code, JoinRoom(name="Synthetic sender", language="hi", consent=True))
        listener = await service.join(state.room.code, JoinRoom(name="Synthetic listener", language="ta", consent=True))
        sender_id = sender["participant"].id
        expected_track = f"translated:{sender_id}:ta"
        routing_errors = []
        for member in (sender, listener):
            client = rtc.Room()
            is_listener = member is listener
            agent = member["livekit"]["agent_identity"]
            def subscribed(track, publication, remote, is_listener=is_listener, agent=agent):
                if not is_listener or publication.name != expected_track or remote.identity != agent:
                    routing_errors.append("unexpected_source_subscription")
                    return
                tasks.append(asyncio.create_task(observe(track)))
            client.on("track_subscribed", subscribed)
            async with asyncio.timeout(15):
                await client.connect(member["livekit"]["url"], member["livekit"]["token"])
            client.local_participant.set_track_subscription_permissions(allow_all_participants=False,
                participant_permissions=[rtc.ParticipantTrackPermission(participant_identity=agent, allow_all=True)])
            clients.append(client)
        source = rtc.AudioSource(RATE, 1, queue_size_ms=100)
        await clients[0].local_participant.publish_track(
            rtc.LocalAudioTrack.create_audio_track("synthetic speech reference", source),
            rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
        await service.update(state.room.code, UpdateParticipant(muted=False), sender["session_token"])
        await asyncio.wait_for(fixture.ready.wait(), 10)
        # Unblock recognizer readiness without letting startup silence count as speech.
        for _ in range(10):
            await source.capture_frame(rtc.AudioFrame(b"\0" * (FRAME * 2), RATE, 1, FRAME))
        await source.wait_for_playout()

        for index in range(11):
            row = {"trial_id": f"local-{index + 1:02d}", "condition": "first_route" if index == 0 else "warm_route",
                   "source_language": "hi", "target_language": "ta", "status": "error",
                   "source_end_to_decoded_ms": None, "source_end_to_render_estimate_ms": None,
                   "source_end_to_physical_playback_ms": None}
            samples.append(row)
            detected.clear()
            current.update(trial=index, detected_at=None, end_at=None)
            stop_silence = asyncio.Event()
            async def trailing_silence():
                for _ in range(125):
                    if stop_silence.is_set():
                        return
                    await source.capture_frame(rtc.AudioFrame(b"\0" * (FRAME * 2), RATE, 1, FRAME))
            trailing = None
            try:
                for offset in range(0, 9600, FRAME):
                    pcm = struct.pack("<320h", *[int(4500 * math.sin(2 * math.pi * 600 * n / RATE))
                                               for n in range(offset, offset + FRAME)])
                    await source.capture_frame(rtc.AudioFrame(pcm, RATE, 1, FRAME))
                await source.wait_for_playout()
                current["end_at"] = time.perf_counter()
                trailing = asyncio.create_task(trailing_silence())
                await asyncio.wait_for(detected.wait(), 8)
                if routing_errors:
                    raise RuntimeError("Unexpected audio subscription")
                row.update(status="complete", source_end_to_decoded_ms=round(
                    (current["detected_at"] - current["end_at"]) * 1000, 3))
                queue = pipeline.queues.get((state.room.code, sender_id))
                if queue is not None:
                    await asyncio.wait_for(queue.join(), 5)
            except TimeoutError:
                row["status"] = "timeout"
            except Exception:
                row["status"] = "error"
            finally:
                if trailing is not None:
                    # Never cancel a native capture in flight: its pending FFI
                    # write must complete before this source accepts another.
                    stop_silence.set()
                    await asyncio.wait_for(trailing, 2)
                current["trial"] = None
                # Preserve a full quiet gap between trials; no old output is a new onset.
                for _ in range(25):
                    await source.capture_frame(rtc.AudioFrame(b"\0" * (FRAME * 2), RATE, 1, FRAME))
                await source.wait_for_playout()
            print(json.dumps({"trial": row["trial_id"], "status": row["status"],
                              "decoded_ms": row["source_end_to_decoded_ms"]}), file=sys.stderr, flush=True)
    except Exception as error:
        fixture_error = type(error).__name__
    finally:
        async def close(label, operation):
            try:
                await asyncio.wait_for(operation(), 5)
            except Exception:
                cleanup_errors.append(label)
        for task in tasks:
            if task.done() and not task.cancelled() and task.exception() is not None:
                cleanup_errors.append("receiver_failure")
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for stream in list(streams):
            await close("receiver_stream", stream.aclose)
        await close("pipeline", pipeline.aclose)
        await close("transport", transport.aclose)
        for client in clients:
            await close("peer", client.disconnect)
        if source is not None:
            await close("source", source.aclose)
        store.sessions.clear()
    warm = [row["source_end_to_decoded_ms"] for row in samples
            if row["condition"] == "warm_route" and row["status"] == "complete"]
    all_values = [row["source_end_to_decoded_ms"] for row in samples if row["status"] == "complete"]
    return {"schema_version": 1, "record_type": "speech_end_latency_evidence",
        "recorded_on": datetime.now(timezone.utc).date().isoformat(), "evidence_kind": "synthetic_local_rtc",
        "clock": "single_process_monotonic", "boundary": "source_end_to_first_decoded_rtc",
        "source_end_reference": "last_voiced_source_frame_playout", "physical_playback_measured": False,
        "provider_calls": 0, "screening_mode": "off", "voice_cloning": False, "target_ms": 2000,
        "acceptance": "not_verified", "samples": samples,
        "summary": {"attempted": len(samples), "completed": sum(row["status"] == "complete" for row in samples),
            "failed": sum(row["status"] != "complete" for row in samples),
            "p50_decoded_ms": percentile(all_values, .5), "p95_decoded_ms": percentile(all_values, .95)},
        "warm_summary": {"attempted": sum(row["condition"] == "warm_route" for row in samples),
                         "completed": len(warm), "p50_decoded_ms": percentile(warm, .5),
                         "p95_decoded_ms": percentile(warm, .95)},
        "summary_condition": "all_routes", "percentile_method": "nearest_rank",
        "fixture": plan()["fixture"], "synthetic_counts": {"recognitions": fixture.recognitions,
            "translations": fixture.translations, "syntheses": fixture.syntheses},
        "wall_seconds": round(time.perf_counter() - started, 3), "cleanup_errors": cleanup_errors,
        "planned_trials": 11, "fixture_error": fixture_error,
        "limitations": ["Synthetic tones and provider doubles, not human speech or Gnani/Evon performance.",
            "Known source-frame SDK playout to received decoded PCM on one process clock; no physical microphone or speaker.",
            "20-ms decoder frames and callback scheduling limit timing precision.",
            "The fixture waits for 600 ms of silence, then uses fixed 100-ms MT and 50-ms TTS delays.",
            "Warm-route nearest-rank summaries exclude the first route and all failed attempts; failure counts remain visible.",
            "No render estimate, acoustic result, meaning acceptance or under-two-second live claim is inferred."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-local", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--curated-output", type=Path)
    args = parser.parse_args(argv)
    if not args.run_local:
        print(json.dumps(plan(), indent=2))
        return 0
    if not args.output or args.output.exists():
        parser.error("Local execution needs a fresh report path.")
    if args.curated_output and args.curated_output.resolve() != ROOT / "web/src/data/speechEndLatencyResults.json":
        parser.error("Use the designated curated metrics file.")
    try:
        result = asyncio.run(asyncio.wait_for(run_local(), 150))
        encoded = json.dumps(result, indent=2, allow_nan=False) + "\n"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as output:
            output.write(encoded)
        # Bind the bytes actually saved: Windows text mode may use CRLF.
        curated = curate_result(result, hashlib.sha256(args.output.read_bytes()).hexdigest())
        valid_run = len(result["samples"]) == 11 and result["fixture_error"] is None and not result["cleanup_errors"]
        if args.curated_output and valid_run:
            args.curated_output.write_text(json.dumps(curated, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"summary": result["summary"], "cleanup_errors": result["cleanup_errors"],
                          "fixture_error": result["fixture_error"], "planned_trials": 11}))
        return 0 if valid_run and not result["summary"]["failed"] else 1
    except Exception as error:
        if not args.output.exists():
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as output:
                json.dump({"schema_version": 1, "record_type": "speech_end_latency_fixture_failure",
                           "status": "error", "provider_calls": 0, "physical_playback_measured": False,
                           "error_class": type(error).__name__, "screening_mode": "off", "voice_cloning": False,
                           "local_stack": [{"file": str(Path(row.filename).relative_to(ROOT)), "line": row.lineno,
                                            "function": row.name} for row in traceback.extract_tb(error.__traceback__)
                                           if Path(row.filename).is_relative_to(ROOT)]}, output, indent=2)
        print("Local fixture stopped; no provider call was made. Inspect local service readiness.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
