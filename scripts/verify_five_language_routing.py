"""Real loopback RTC, five source languages and six peers; all providers are doubles.

Checks twenty translation branches, shared-language fan-out, original-source
isolation and first decoded synthetic audio per recipient, plus camera delivery.
Completed receiver PCM observers close; RTC subscriptions and permission checks
remain. This is not a continuous-playback or audio-quality stress benchmark.
No microphone, camera device, API,
cloned voice, learned screening or remote server is used. A loopback LiveKit
development server must already be running on port7880.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from contextlib import asynccontextmanager
import json
import logging
import math
from pathlib import Path
import struct
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from livekit import rtc

from artha_mesh.config import Settings
from artha_mesh.models import JoinRoom, UpdateParticipant
from artha_mesh.providers.gnani import Transcript
from artha_mesh.services.pipeline import Pipeline
from artha_mesh.services.rooms import RoomService
from artha_mesh.store import Store
from artha_mesh.transport.livekit import TransportManager

LANGUAGES = ("hi", "ta", "bn", "te", "mr")


def progress(stage, **values):
    print(json.dumps({"stage": stage, **values}), file=sys.stderr, flush=True)


class Providers:
    """Synthetic PCM and deterministic text only; records call topology."""
    def __init__(self):
        self.recognition_opened = Counter()
        self.recognition_closed = Counter()
        self.translations = []
        self.synthesis = []

    async def transcribe(self, audio, language, on_processing=None):
        self.recognition_opened[language] += 1
        observed, emitted = 0, False
        try:
            async for chunk in audio:
                if not any(abs(value) > 80 for value in memoryview(chunk).cast("h")):
                    continue
                observed += len(chunk)
                if observed >= 16000 and not emitted:
                    emitted = True
                    if on_processing:
                        on_processing()
                    yield Transcript("Synthetic route fixture " + language, language, 0)
        finally:
            self.recognition_closed[language] += 1

    async def translate(self, text, source, target):
        self.translations.append((source, target))
        return f"Synthetic route fixture {source} to {target}"

    async def synthesize(self, text, language, embedding=None):
        assert embedding is None, "Voice cloning is outside this test"
        self.synthesis.append((text, language))
        for offset in range(0, 24000 * 2, 480):
            yield struct.pack("<480h", *[
                int(5000 * math.sin(2 * math.pi * 440 * (offset + n) / 24000))
                for n in range(480)
            ])


async def until(predicate, seconds=20):
    async with asyncio.timeout(seconds):
        while not predicate():
            await asyncio.sleep(.05)


async def observe_first_audio(track, name, identity, received, first_pcm, streams):
    """Stop Python per-frame observation once this route's first PCM is proved.

    Keeping every completed decoder open in one Python process multiplies SDK
    FFI event fan-out; browsers do not use these Python receiver observers.
    Subscription/permission event monitoring stays alive at the room level.
    """
    stream = rtc.AudioStream(track, sample_rate=16000, num_channels=1, capacity=8, frame_size_ms=20)
    streams.append(stream)
    try:
        async for event in stream:
            if any(abs(value) > 80 for value in event.frame.data.cast("B").cast("h")):
                received[identity][name] = event.frame.samples_per_channel
                first_pcm.setdefault((identity, name), time.perf_counter())
                return
    finally:
        await stream.aclose()
        streams.remove(stream)


def fixture_snapshot(runtime, state, fixture, memberships, received, source_progress, tasks):
    """Keep failure topology without session tokens, text or invented latency."""
    language_by_id = {m["participant"].id: m["participant"].language for m in memberships}
    transport = runtime.transport.rooms.get(state.room.code)
    pending_routes = []
    for speaker in memberships[:5]:
        source = speaker["participant"]
        for listener_index, listener in enumerate(memberships, 1):
            target = listener["participant"]
            if source.id == target.id:
                continue
            name = f"translated:{source.id}:{target.language}"
            if name not in received.get(target.id, {}):
                pending_routes.append({"source_language": source.language,
                                       "target_language": target.language, "listener_peer": listener_index})
    failures = []
    for task in tasks:
        if task.done() and not task.cancelled() and task.exception() is not None:
            failures.append(type(task.exception()).__name__)
    return {
        "source_progress": {language: dict(values) for language, values in source_progress.items()},
        "recognition_opened": dict(fixture.recognition_opened),
        "recognition_closed": dict(fixture.recognition_closed),
        "translation_pairs": [list(pair) for pair in fixture.translations],
        "synthesis_jobs": len(fixture.synthesis),
        "received_route_count": sum(len(tracks) for tracks in received.values()),
        "missing_recipient_routes": pending_routes,
        "output_tracks": [{"source_language": language_by_id.get(source), "target_language": language}
                          for source, language in (transport.outputs if transport else {})],
        "pipeline_queue_sizes": {language_by_id.get(source, "unknown"): queue.qsize()
                                 for (code, source), queue in runtime.pipeline.queues.items() if code == state.room.code},
        "terminal_branches": [{"source_language": sample.source_language,
                               "target_language": sample.target_language,
                               "status": sample.status, "error_stage": sample.error_stage}
                              for sample in state.performance_samples],
        "receiver_task_failure_kinds": failures,
    }


@asynccontextmanager
async def fixture_runtime(settings, fixture, diagnostics):
    # Construct only the actual room/pipeline/RTC services with explicit
    # settings and doubles. Importing main.py would construct its global app
    # from the operator's environment, which this isolated verifier avoids.
    store = Store(settings)
    pipeline = Pipeline(store, fixture, fixture)
    transport = TransportManager(store, fixture, pipeline)
    pipeline.transport = transport
    service = RoomService(store, pipeline, transport, None)
    try:
        yield SimpleNamespace(store=store, pipeline=pipeline, transport=transport, service=service)
    finally:
        for name, close in (("pipeline_close", pipeline.aclose), ("interpreter_close", transport.aclose)):
            try:
                await asyncio.wait_for(close(), 5)
            except Exception as error:
                diagnostics["cleanup_failures"].append({"resource": name, "kind": type(error).__name__})
        store.sessions.clear()


async def run(*, sequential=False, diagnostics=None) -> dict:
    diagnostics = diagnostics if diagnostics is not None else {"cleanup_failures": []}
    settings = Settings(
        _env_file=None, mode="live", livekit_url="ws://127.0.0.1:7880",
        livekit_internal_url="ws://127.0.0.1:7880", livekit_api_key="devkey",
        livekit_api_secret="secret", gnani_api_key="test-double-never-sent",
        evon_base_url="http://127.0.0.1:9/v1", evon_api_key="", evon_model="test-double",
        evon_modal_key="", evon_modal_secret="", audio_screening_mode="off",
        usage_db_path=ROOT / "work/local/five-language-rtc-usage.sqlite3",
        usage_require_flow_approval=False,  # Providers below are local doubles, never services.
    )
    fixture = Providers()
    clients, audio_sources, tasks, streams = [], [], [], []
    received, first_pcm, sent_at, video_frames = {}, {}, {}, {}
    source_progress = {}
    errors = []
    camera_source, camera_publication = None, None
    started = time.perf_counter()
    async with fixture_runtime(settings, fixture, diagnostics) as runtime:
        app = SimpleNamespace(state=runtime)
        state = app.state.store.create_room("Five-language synthetic RTC fixture")
        memberships = []
        try:
            # Peer6 is a muted second Tamil listener. Its shared translations
            # must not create duplicate MT/TTS or an extra recognizer.
            for index, language in enumerate((*LANGUAGES, "ta")):
                member = await app.state.service.join(state.room.code, JoinRoom(
                    name=f"Synthetic peer {index + 1}", language=language, consent=True,
                ))
                memberships.append(member)
                if index < 5:
                    await app.state.service.update(state.room.code, UpdateParticipant(muted=False), member["session_token"])
            progress("memberships_ready", participants=len(memberships))
            source_ids = {m["participant"].id for m in memberships[:5]}
            camera_owner = memberships[0]["participant"].id
            for index, member in enumerate(memberships):
                identity, language = member["participant"].id, member["participant"].language
                received[identity], video_frames[identity] = {}, 0
                client = rtc.Room()

                async def consume_audio(track, name, identity=identity):
                    await observe_first_audio(track, name, identity, received, first_pcm, streams)

                async def consume_video(track, identity=identity):
                    stream = rtc.VideoStream(track)
                    streams.append(stream)
                    async for event in stream:
                        if event.frame.width > 0 and event.frame.height > 0:
                            video_frames[identity] += 1

                def subscribed(track, publication, remote, identity=identity, language=language,
                               audio=consume_audio, video=consume_video, agent=member["livekit"]["agent_identity"]):
                    if track.kind == rtc.TrackKind.KIND_VIDEO:
                        if publication.source != rtc.TrackSource.SOURCE_CAMERA or remote.identity != camera_owner or identity == camera_owner:
                            errors.append("unexpected_camera_subscription")
                        tasks.append(asyncio.create_task(video(track)))
                        return
                    pieces = publication.name.split(":")
                    if (len(pieces) != 3 or pieces[0] != "translated" or pieces[1] not in source_ids
                            or pieces[1] == identity or pieces[2] != language or remote.identity != agent):
                        errors.append("unexpected_source_or_language_subscription")
                    tasks.append(asyncio.create_task(audio(track, publication.name)))

                client.on("track_subscribed", subscribed)
                async with asyncio.timeout(15):
                    await client.connect(member["livekit"]["url"], member["livekit"]["token"])
                client.local_participant.set_track_subscription_permissions(
                    allow_all_participants=False,
                    participant_permissions=[rtc.ParticipantTrackPermission(
                        participant_identity=member["livekit"]["agent_identity"], allow_all=True,
                    )],
                )
                if index < 5:
                    source = rtc.AudioSource(16000, 1, queue_size_ms=100)
                    audio_sources.append(source)
                    async with asyncio.timeout(15):
                        await client.local_participant.publish_track(
                            rtc.LocalAudioTrack.create_audio_track("synthetic microphone", source),
                            rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE),
                        )
                clients.append(client)
                progress("peer_connected", peer=index + 1)
            await asyncio.sleep(.5)

            async def publish(index):
                language = LANGUAGES[index]
                source_progress[language] = {"requested_frames": 0, "captured_frames": 0,
                                             "source_playout_completed": False}
                sent_at[memberships[index]["participant"].id] = time.perf_counter()
                for offset in range(0, 16000 * 3, 320):
                    data = struct.pack("<320h", *[
                        int(4000 * math.sin(2 * math.pi * (300 + 70 * index) * (offset + n) / 16000))
                        for n in range(320)
                    ])
                    source_progress[language]["requested_frames"] += 1
                    await audio_sources[index].capture_frame(rtc.AudioFrame(data, 16000, 1, 320))
                    source_progress[language]["captured_frames"] += 1
                    if source_progress[language]["captured_frames"] % 50 == 0:
                        progress("source_capture_progress", language=language,
                                 captured_frames=source_progress[language]["captured_frames"])
                progress("source_capture_complete", language=language)
                await audio_sources[index].wait_for_playout()
                source_progress[language]["source_playout_completed"] = True

            expected = {}
            for listener in memberships:
                participant = listener["participant"]
                expected[participant.id] = {
                    f"translated:{speaker['participant'].id}:{participant.language}"
                    for speaker in memberships[:5] if speaker["participant"].id != participant.id
                }
            diagnostics["phase"] = "synthetic_audio_send"
            progress("publishing_synthetic_audio", pattern="sequential" if sequential else "concurrent")
            if sequential:
                for index in range(5):
                    source_id = memberships[index]["participant"].id
                    diagnostics["phase"] = "source_capture:" + LANGUAGES[index]
                    async with asyncio.timeout(50):
                        await publish(index)
                    diagnostics["phase"] = "pipeline_queue_drain:" + LANGUAGES[index]
                    queue = app.state.pipeline.queues.get((state.room.code, source_id))
                    if queue is not None:
                        await asyncio.wait_for(queue.join(), 50)
                    diagnostics["phase"] = "receiver_delivery:" + LANGUAGES[index]
                    await until(lambda: all(
                        f"translated:{source_id}:{member['participant'].language}" in received[member["participant"].id]
                        for member in memberships if member["participant"].id != source_id
                    ), 50)
                    progress("sequential_source_delivered", language=LANGUAGES[index], translations=len(fixture.translations))
            else:
                async with asyncio.timeout(15):
                    await asyncio.gather(*(publish(index) for index in range(5)))
            progress("synthetic_audio_sent", translations=len(fixture.translations), received_tracks=[len(received[m["participant"].id]) for m in memberships])
            diagnostics["phase"] = "audio_route_assertions"
            await until(lambda: all(set(received[identity]) == tracks for identity, tracks in expected.items()), 50 if sequential else 20)
            for queue in app.state.pipeline.queues.values():
                await asyncio.wait_for(queue.join(), 20)
            expected_pairs = {(a, b) for a in LANGUAGES for b in LANGUAGES if a != b}
            assert set(fixture.translations) == expected_pairs and len(fixture.translations) == 20
            assert len(fixture.synthesis) == 20
            assert fixture.recognition_opened == Counter({language: 1 for language in LANGUAGES})
            assert not errors, errors
            progress("audio_routing_verified", translations=20, recognizers=sum(fixture.recognition_opened.values()))
            diagnostics["phase"] = "camera_routes"

            # A real synthetic video track exercises the camera token and direct
            # peer delivery; no device is opened. Only its SID is shared.
            camera_source = rtc.VideoSource(64, 48)
            camera_track = rtc.LocalVideoTrack.create_video_track(f"camera:{camera_owner}", camera_source)
            camera_publication = await clients[0].local_participant.publish_track(
                camera_track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_CAMERA),
            )
            clients[0].local_participant.set_track_subscription_permissions(
                allow_all_participants=False,
                participant_permissions=[
                    rtc.ParticipantTrackPermission(participant_identity=memberships[0]["livekit"]["agent_identity"], allow_all=True),
                    *(rtc.ParticipantTrackPermission(participant_identity=m["participant"].id, allow_all=False,
                                                    allowed_track_sids=[camera_publication.sid]) for m in memberships[1:]),
                ],
            )
            for _ in range(50):
                camera_source.capture_frame(rtc.VideoFrame(64, 48, rtc.VideoBufferType.RGBA, b"\x20\x80\xc0\xff" * (64 * 48)))
                await asyncio.sleep(.1)
                if all(video_frames[m["participant"].id] > 0 for m in memberships[1:]):
                    break
            assert all(video_frames[m["participant"].id] > 0 for m in memberships[1:]), "Missing camera receiver"
            await clients[0].local_participant.unpublish_track(camera_publication.sid)
            camera_publication = None
            await asyncio.sleep(.2)
            assert not fixture.recognition_closed, "Camera unsubscribe cancelled an active microphone"
            assert fixture.recognition_opened == Counter({language: 1 for language in LANGUAGES})
            assert not errors, errors
            progress("camera_routing_verified", receivers=sum(count > 0 for count in video_frames.values()))
            for task in tasks:
                if task.done() and not task.cancelled() and task.exception():
                    raise task.exception()
            directions = []
            for listener_index, listener in enumerate(memberships):
                for speaker_index, speaker in enumerate(memberships[:5]):
                    if listener_index == speaker_index:
                        continue
                    source, target = speaker["participant"], listener["participant"]
                    forwarded = source.language == target.language
                    name = f"translated:{source.id}:{target.language}"
                    directions.append({"source_peer": speaker_index + 1, "listener_peer": listener_index + 1,
                                       "source_language": source.language, "target_language": target.language,
                                       "measurement": "synthetic_source_forwarded" if forwarded else "synthetic_translation_route",
                                       "capture_to_first_received_pcm_ms": round((first_pcm[(target.id, name)] - sent_at[source.id]) * 1000, 2)})
            return {"schema_version": 1, "record_type": "five_language_synthetic_rtc", "passed": True,
                    "languages": list(LANGUAGES), "participants": 6, "microphone_publishers": 5,
                    "speaking_pattern": "sequential_one_at_a_time" if sequential else "five_simultaneous_synthetic_sources",
                    "simultaneous_speech_verified": not sequential,
                    "recognition_streams": dict(fixture.recognition_opened), "translation_branches": 20,
                    "synthesis_jobs": 20, "audible_recipient_routes": len(directions),
                    "same_language_forwarding_routes": 1, "shared_tamil_receivers": 2,
                    "synthetic_camera_receivers": sum(count > 0 for count in video_frames.values()),
                    "camera_toggle_preserved_microphones": True,
                    "provider_requests": 0, "synthetic": True, "screening": "off", "voice_cloning": False,
                    "live_provider_capacity_verified": False,
                    "receiver_observation": "First nonzero decoded PCM per route; observer then closes while RTC subscription and permission monitoring remain. Continuous playback, sustained load and audio quality are not verified.",
                    "live_provider_requirements": {"five_active_sources_need_stt_slots": 5,
                        "default_stt_slots": 3, "default_operation_slots": 2, "default_queued_operations": 16,
                        "note": "Real five-speaker approval/configuration must respect provider quota and size admission queues deliberately; fixture success does not establish live provider capacity."},
                    "boundary": "Same-process source capture to received decoded PCM. Includes fixture recognition threshold, local RTC negotiation/codec/buffering and test-double synthesis; not human/listener/hardware/Gnani/Evon or real translation latency.",
                    "directions": directions, "wall_seconds": round(time.perf_counter() - started, 3),
                    "checks": ["all twenty directed language pairs", "one recognizer per active source", "one MT/TTS job per unique listener language", "shared translated-track fan-out", "same-language original forwarding", "no self, original-peer or wrong-language audio leak", "camera source grant and SID-isolated direct peer video", "camera unsubscribe preserves microphone readers"]}
        finally:
            diagnostics["fixture_snapshot"] = fixture_snapshot(
                runtime, state, fixture, memberships, received, source_progress, tasks,
            )
            progress("closing_fixture")
            async def close_resource(name, operation, timeout):
                try:
                    await asyncio.wait_for(operation(), timeout)
                except Exception as error:
                    diagnostics["cleanup_failures"].append({"resource": name, "kind": type(error).__name__})
            if camera_publication is not None and clients:
                await close_resource("camera_unpublish", lambda: clients[0].local_participant.unpublish_track(camera_publication.sid), 3)
            for task in tasks:
                task.cancel()
            await close_resource("receiver_tasks", lambda: asyncio.gather(*tasks, return_exceptions=True), 5)
            for stream in streams:
                await close_resource("receiver_stream", stream.aclose, 3)
            for client in clients:
                await close_resource("peer_disconnect", client.disconnect, 5)
            for source in audio_sources:
                await close_resource("audio_source", source.aclose, 3)
            if camera_source is not None:
                await close_resource("camera_source", camera_source.aclose, 3)
            progress("fixture_closed", cleanup_failures=diagnostics["cleanup_failures"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sequential", action="store_true", help="One source at a time; does not verify simultaneous speech")
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error("Use a new report filename; existing evidence is preserved")
    logging.basicConfig(level=logging.ERROR)
    diagnostics = {"cleanup_failures": [], "phase": "peer_setup"}
    async def bounded():
        async with asyncio.timeout(240 if args.sequential else 90):
            return await run(sequential=args.sequential, diagnostics=diagnostics)
    try:
        report = asyncio.run(bounded())
    except Exception as error:
        report = {"schema_version": 1, "record_type": "five_language_synthetic_rtc", "passed": False,
                  "failure_kind": type(error).__name__, "provider_requests": 0, "synthetic": True,
                  "screening": "off", "voice_cloning": False, "latency": None,
                  "note": "Bounded local fixture failed; no successful route or live-provider claim follows. Preserve progress and use a new filename for an independently reviewed retry."}
    report["cleanup_failures"] = diagnostics["cleanup_failures"]
    if report["passed"] and diagnostics["cleanup_failures"]:
        report.update(passed=False, checks_passed_before_cleanup=True, failure_kind="cleanup_incomplete")
    if not report["passed"]:
        report["failed_phase"] = diagnostics["phase"]
        report["fixture_snapshot"] = diagnostics.get("fixture_snapshot")
    report["maximum_wall_seconds"] = 240 if args.sequential else 90
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
