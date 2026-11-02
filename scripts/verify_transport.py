"""Two real local RTC peers; raw PCM relay only, no microphone or provider API.

The reported boundary is source capture -> received non-silent PCM in this
single Python process. It includes RTC setup/codec buffering and is not a human
listener, hardware, speech recognition, translation or synthesis benchmark.
"""
from __future__ import annotations

import asyncio
import argparse
import json
import logging
import math
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from livekit import rtc

from artha_mesh.config import Settings
from artha_mesh.main import create_app
from artha_mesh.models import JoinRoom, UpdateParticipant


def has_signal(frame):
    return any(abs(value) > 100 for value in frame.data.cast("B").cast("h"))


class StartupTrace:
    """First-event timestamps only; no audio or participant identifiers exported."""

    def __init__(self, enabled):
        self.enabled = enabled
        self.events = {}
        self.track_speakers = {}
        self.stream_factory = rtc.AudioStream

    def mark(self, speaker_id, name):
        if self.enabled and speaker_id:
            self.events.setdefault(speaker_id, {}).setdefault(name, time.perf_counter())

    def instrument(self, transport):
        if not self.enabled:
            return
        original_output = transport._output
        original_wait = transport._wait_for_listener
        trace = self

        async def output(speaker_id, language, rate):
            if (speaker_id, language) not in transport.outputs:
                trace.mark(speaker_id, "output_publish_start")
            result = await original_output(speaker_id, language, rate)
            trace.mark(speaker_id, "output_publish_finished")
            if not getattr(result.source, "_startup_trace_installed", False):
                original_capture = result.source.capture_frame

                async def capture(frame):
                    events = trace.events.setdefault(speaker_id, {})
                    if "agent_first_signal_forwarded" not in events and has_signal(frame):
                        trace.mark(speaker_id, "agent_first_signal_forwarded")
                    return await original_capture(frame)

                result.source.capture_frame = capture
                result.source._startup_trace_installed = True
            return result

        async def ready(output, speaker_id, language):
            await original_wait(output, speaker_id, language)
            trace.mark(speaker_id, "first_subscriber_ready")

        class TracedStream:
            def __init__(self, stream, track):
                self.stream, self.track = stream, track

            def __aiter__(self):
                return self

            async def __anext__(self):
                event = await self.stream.__anext__()
                speaker_id = trace.track_speakers.get(self.track.sid)
                events = trace.events.get(speaker_id, {})
                if speaker_id and "agent_first_signal_received" not in events and has_signal(event.frame):
                    trace.mark(speaker_id, "agent_first_signal_received")
                return event

            async def aclose(self):
                await self.stream.aclose()

        def stream_factory(*args, **kwargs):
            stream = trace.stream_factory(*args, **kwargs)
            # Production reads use the named track argument; fixture receivers
            # use a positional argument and retain the original SDK stream.
            return TracedStream(stream, kwargs["track"]) if "track" in kwargs else stream

        transport._output = output
        transport._wait_for_listener = ready
        rtc.AudioStream = stream_factory

    def restore(self):
        rtc.AudioStream = self.stream_factory

    def report(self, memberships, sent_at, first_pcm):
        if not self.enabled:
            return None
        rows = []
        for index, member in enumerate(memberships):
            speaker_id = member["participant"].id
            track = f"raw:{speaker_id}:all"
            started = sent_at[track]
            events = self.events.get(speaker_id, {})
            rows.append({
                "route": f"peer {index + 1} -> peer {2 - index}",
                "events_ms_from_source_capture": {
                    **{name: round((when - started) * 1000, 2) for name, when in events.items()},
                    "receiver_first_signal": round((first_pcm[track] - started) * 1000, 2),
                },
                "output_publish_elapsed_ms": round((events["output_publish_finished"] - events["output_publish_start"]) * 1000, 2)
                    if "output_publish_start" in events and "output_publish_finished" in events else None,
            })
        return {"boundary": "Same-process monotonic clock; negative offsets mean setup occurred before source capture. First events only; includes diagnostic wrapper overhead.", "routes": rows}


async def run(destination, trace_enabled=False):
    settings = Settings(
        _env_file=None, mode="transport", livekit_url="ws://127.0.0.1:7880",
        livekit_internal_url="ws://127.0.0.1:7880", livekit_api_key="devkey",
        livekit_api_secret="secret", gnani_api_key="", evon_base_url="", evon_model="",
        usage_db_path=ROOT / "work/local/rtc-verification.sqlite3",
    )
    app = create_app(settings)
    clients, sources, tasks, streams = [], [], [], []
    memberships, received, first_pcm, sent_at, errors = [], {}, {}, {}, []
    subscriptions, unsubscribed = {}, set()
    trace = StartupTrace(trace_enabled)
    async with app.router.lifespan_context(app):
        state = app.state.store.create_room("Local two-peer raw audio check")
        try:
            for index, language in enumerate(("hi", "ta")):
                member = await app.state.service.join(state.room.code, JoinRoom(
                    name=f"Synthetic local peer {index + 1}", language=language, consent=True,
                ))
                memberships.append(member)
                await app.state.service.update(state.room.code, UpdateParticipant(muted=False), member["session_token"])

            trace.instrument(app.state.transport.rooms[state.room.code])

            for member in memberships:
                identity = member["participant"].id
                received[identity] = {}
                client = rtc.Room()

                async def consume(track, name, identity=identity):
                    stream = rtc.AudioStream(track, sample_rate=16000, num_channels=1, capacity=50)
                    streams.append(stream)
                    try:
                        async for event in stream:
                            samples = event.frame.data.cast("B").cast("h")
                            if any(abs(value) > 100 for value in samples):
                                received[identity][name] = received[identity].get(name, 0) + len(samples)
                                first_pcm.setdefault(name, time.perf_counter())
                    finally:
                        await stream.aclose()

                def subscribed(track, publication, remote, identity=identity, consume=consume, agent=member["livekit"]["agent_identity"]):
                    pieces = publication.name.split(":")
                    if len(pieces) != 3 or pieces[0] != "raw" or pieces[1] == identity or pieces[2] != "all" or remote.identity != agent:
                        errors.append(f"Unexpected subscribed track: {publication.name}")
                    task = asyncio.create_task(consume(track, publication.name))
                    subscriptions[(identity, publication.sid)] = task
                    tasks.append(task)

                def detached(track, publication, remote, identity=identity):
                    # Match the browser's TrackUnsubscribed detach behavior;
                    # a removed receiver must not keep consuming old PCM.
                    task = subscriptions.pop((identity, publication.sid), None)
                    if task:
                        task.cancel()
                    unsubscribed.add((identity, publication.name))

                client.on("track_subscribed", subscribed)
                client.on("track_unsubscribed", detached)
                await client.connect(member["livekit"]["url"], member["livekit"]["token"])
                client.local_participant.set_track_subscription_permissions(
                    allow_all_participants=False,
                    participant_permissions=[rtc.ParticipantTrackPermission(
                        participant_identity=member["livekit"]["agent_identity"], allow_all=True,
                    )],
                )
                source = rtc.AudioSource(16000, 1, queue_size_ms=100)
                sources.append(source)
                source_publication = await client.local_participant.publish_track(
                    rtc.LocalAudioTrack.create_audio_track("local test tone", source),
                    rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE),
                )
                trace.track_speakers[source_publication.sid] = identity
                clients.append(client)

            # Allow source/agent publication negotiation before starting the clock.
            await asyncio.sleep(1)

            async def publish(index, seconds=2, audible=True):
                identity = memberships[index]["participant"].id
                if audible:
                    sent_at.setdefault(f"raw:{identity}:all", time.perf_counter())
                for offset in range(0, int(16000 * seconds), 320):
                    data = struct.pack("<320h", *[
                        int(6000 * math.sin(2 * math.pi * (620 + 290 * index) * (offset + n) / 16000)) if audible else 0
                        for n in range(320)
                    ])
                    await source_for(index).capture_frame(rtc.AudioFrame(data, 16000, 1, 320))
                await source_for(index).wait_for_playout()

            def source_for(index):
                return sources[index]

            await asyncio.gather(*(publish(index) for index in range(2)))
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline and not all(len(items) == 1 for items in received.values()):
                await asyncio.sleep(0.1)
            assert not errors, errors
            for index, member in enumerate(memberships):
                other = memberships[1 - index]["participant"].id
                assert set(received[member["participant"].id]) == {f"raw:{other}:all"}, received
            assert not state.turns, "Transport-only mode must not generate transcript or translation turns"

            # The server must enforce mute even if a deliberately misbehaving test
            # publisher continues sending non-silent PCM after its UI mute.
            listener = memberships[1]["participant"].id
            speaker_id = memberships[0]["participant"].id
            track = f"raw:{speaker_id}:all"
            muted_at = time.perf_counter()
            await app.state.service.update(state.room.code, UpdateParticipant(muted=True), memberships[0]["session_token"])
            assert (speaker_id, "all") not in app.state.transport.rooms[state.room.code].outputs
            assert speaker_id not in app.state.transport.rooms[state.room.code].readers
            async with asyncio.timeout(5):
                while (listener, track) not in unsubscribed:
                    await asyncio.sleep(0.02)
            mute_detach_ms = round((time.perf_counter() - muted_at) * 1000, 2)
            before = received[listener].get(track, 0)
            await publish(0, 0.6)
            await asyncio.sleep(0.2)
            assert received[listener].get(track, 0) == before, "Muted publisher was still relayed"
            assert (speaker_id, "all") not in app.state.transport.rooms[state.room.code].outputs
            await app.state.service.update(state.room.code, UpdateParticipant(muted=False), memberships[0]["session_token"])
            await publish(0, 0.8)
            recovery_deadline = time.monotonic() + 6
            while received[listener].get(track, 0) <= before and time.monotonic() < recovery_deadline:
                await asyncio.sleep(0.05)
            assert received[listener].get(track, 0) > before, "Unmute did not restore relay"

            measurements = [
                {"route": f"peer {index + 1} -> peer {2 - index}", "capture_to_first_received_pcm_ms": round((first_pcm[f"raw:{member['participant'].id}:all"] - sent_at[f"raw:{member['participant'].id}:all"]) * 1000, 2)}
                for index, member in enumerate(memberships)
            ]
            report = {
                "passed": True, "mode": "transport", "synthetic": True, "provider_requests": 0,
                "boundary": "source capture to received non-silent PCM in one local process; includes negotiation/buffering; not listener or translation latency",
                "directions": measurements, "mute_request_to_receiver_track_detached_ms": mute_detach_ms,
                "checks": ["two audible directed raw routes", "different selected languages preserve raw audio", "no self echo or original peer subscription", "server mute unpublishes and receiver detaches", "muted publisher cannot relay new PCM", "unmute restores audio", "no transcript or interpretation"],
            }
            if trace_enabled:
                report["startup_trace"] = trace.report(memberships, sent_at, first_pcm)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print("PASS: two real local RTC peers, two raw audio directions, no self echo.")
            print("PASS: server mute/unmute; no interpretation or provider requests.")
            print(json.dumps(measurements, ensure_ascii=True))
            print("Boundary: capture -> received PCM, includes setup/buffering; not listener or translation latency.")
            if trace_enabled:
                print(json.dumps(report["startup_trace"], ensure_ascii=True))
        finally:
            trace.restore()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for stream in streams:
                await stream.aclose()
            for client in clients:
                await client.disconnect()
            for source in sources:
                await source.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "work/local/transport-check.json")
    parser.add_argument("--trace", action="store_true", help="Record anonymous first-event startup timing without retaining audio")
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.ERROR)
    try:
        asyncio.run(run(arguments.output, arguments.trace))
    except Exception as error:
        destination = arguments.output
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps({
            "passed": False, "mode": "transport", "synthetic": True, "provider_requests": 0,
            "error_type": type(error).__name__,
            "detail": str(error) if isinstance(error, AssertionError) else "Local RTC check failed; inspect local media setup",
        }, indent=2) + "\n", encoding="utf-8")
        raise
