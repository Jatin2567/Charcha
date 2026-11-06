"""Two RTC peers, one recorded source, one standard-voice conference turn.

Shared by the offline rehearsal and the bounded operator batch. This module
does not grant credit, provision compute, open a device or read private settings.
"""
import asyncio
from contextlib import AsyncExitStack, aclosing
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from livekit import rtc
from charcha.models import JoinRoom, UpdateParticipant
from charcha.services.pipeline import Pipeline
from charcha.services.rooms import RoomService
from charcha.store import Store
from charcha.transport.livekit import TransportManager


class OneUtterance:
    """Release the provider socket on the first final, before starting MT."""
    def __init__(self, speech, usage):
        self.speech, self.usage = speech, usage
        self.started = asyncio.Event()
        self.failed = False

    async def transcribe(self, audio, language, on_processing=None):
        self.started.set()
        try:
            async with asyncio.timeout(23), aclosing(
                self.speech.transcribe(audio, language, on_processing)
            ) as stream:
                segment = await anext(stream)
            yield segment
            # Leave the room reader alive until teardown, without reopening STT.
            await asyncio.Event().wait()
        except Exception:
            self.failed = True
            raise


async def wait_until(predicate, seconds):
    async with asyncio.timeout(seconds):
        while not predicate():
            await asyncio.sleep(.04)


async def conference_turn(settings, guard, speech, translator, source, target, pcm, row, *, prepared_room=None):
    if prepared_room is None:
        store = Store(settings)
        state = store.create_room("Recorded five-language conference test")
    else:
        store, state = prepared_room
    reader = OneUtterance(speech, guard)
    pipeline = Pipeline(store, translator, speech)
    transport = TransportManager(store, reader, pipeline)
    pipeline.transport = transport
    service = RoomService(store, pipeline, transport, None, guard)
    receiver_pcm = bytearray()
    receive_tasks = []
    wrong_track = False
    first_sound = None
    started = None

    async def collect(track):
        nonlocal first_sound
        async with aclosing(rtc.AudioStream(track, sample_rate=16000, num_channels=1)) as stream:
            async for event in stream:
                frame = bytes(event.frame.data)
                if first_sound is None and max(map(abs, memoryview(frame).cast("h")), default=0) > 80:
                    first_sound = time.perf_counter()
                if first_sound is not None and len(receiver_pcm) < 16000 * 2 * 60:
                    receiver_pcm.extend(frame)

    async def stop_observers():
        for task in receive_tasks:
            task.cancel()
        await asyncio.gather(*receive_tasks, return_exceptions=True)

    async with AsyncExitStack() as stack:
        stack.push_async_callback(transport.aclose)
        stack.push_async_callback(pipeline.aclose)
        row["stage"] = "rtc_join"
        speaker, listener = [await service.join(state.room.code, JoinRoom(
            name=f"Test {language}", language=language, consent=True,
            screening_consent=state.room.screening_switchable)) for language in (source, target)]
        agent = speaker["livekit"]["agent_identity"]
        expected = f"translated:{speaker['participant'].id}:{target}"
        peers = []
        for member in (speaker, listener):
            peer = rtc.Room()
            def subscribed(track, publication, remote, member=member):
                nonlocal wrong_track
                if member is not listener or remote.identity != agent or publication.name != expected:
                    wrong_track = True
                    return
                receive_tasks.append(asyncio.create_task(collect(track)))
            peer.on("track_subscribed", subscribed)
            stack.push_async_callback(peer.disconnect)
            await peer.connect(member["livekit"]["url"], member["livekit"]["token"])
            peer.local_participant.set_track_subscription_permissions(allow_all_participants=False, participant_permissions=[
                rtc.ParticipantTrackPermission(participant_identity=agent, allow_all=True)])
            peers.append(peer)
        stack.push_async_callback(stop_observers)
        room = transport.rooms[state.room.code].room
        await wait_until(lambda: all(m["participant"].id in room.remote_participants for m in (speaker, listener)), 10)
        await service.update(state.room.code, UpdateParticipant(muted=False), speaker["session_token"])
        audio = rtc.AudioSource(16000, 1, queue_size_ms=60)
        stack.push_async_callback(audio.aclose)
        mic = rtc.LocalAudioTrack.create_audio_track("Recorded test input", audio)
        await peers[0].local_participant.publish_track(mic, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
        row["stage"] = "speech_recognition"
        await asyncio.wait_for(reader.started.wait(), 8)
        started = time.perf_counter()
        # Pace via the RTC source. A brief pre-roll lets Opus start up.
        frames = bytes(640 * 10) + pcm + bytes(640 * 55)
        for offset in range(0, len(frames), 640):
            if reader.failed or wrong_track:
                raise RuntimeError("Recognition failed or an unexpected track was delivered")
            data = frames[offset:offset + 640].ljust(640, b"\0")
            await audio.capture_frame(rtc.AudioFrame(data, 16000, 1, 320))
        await audio.wait_for_playout()
        await wait_until(lambda: state.performance_samples or reader.failed or wrong_track, 35)
        if reader.failed or wrong_track or not state.performance_samples:
            raise RuntimeError("Missing final turn or unexpected media")
        sample = state.performance_samples[-1]
        row["stage"] = sample.error_stage or "listener_decode"
        if sample.status != "complete" or sample.source_language != source or sample.target_language != target:
            raise RuntimeError("Conference branch did not complete")
        row.update(mt_ms=sample.mt_ms, stt_processing_ms=sample.stt_ms,
                   tts_first_pcm_ms=sample.tts_first_pcm_ms, server_first_pcm_ms=sample.total_ms)
        await wait_until(lambda: first_sound is not None or wrong_track, 8)
        if wrong_track:
            raise RuntimeError("Unexpected media route")
        await asyncio.sleep(.35)
        row["capture_start_to_receiver_first_pcm_ms"] = round((first_sound - started) * 1000, 1)
        row["received_non_silent_pcm"] = True
        turn = state.turns[-1]
        return {"recognized": turn.text, "translated": turn.translations[target]}, bytes(receiver_pcm)
