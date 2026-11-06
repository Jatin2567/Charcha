import asyncio
import time

from charcha.config import Settings
from charcha.models import Participant, VoiceProfile
from charcha.providers.demo import SAMPLES
from charcha.services.pipeline import Pipeline
from charcha.services.rooms import RoomService
from charcha.store import Consumer, Store, StoredVoice, token_digest
from charcha.transport.livekit import RoomTransport


class RecordingTransport:
    def __init__(self):
        self.removed = []
        self.closed = []

    async def remove(self, code, participant_id):
        self.removed.append((code, participant_id))

    async def close_room(self, code):
        self.closed.append(code)


def test_media_source_gate_rejects_expired_session_before_periodic_sweep():
    store = Store(Settings(mode="live", session_ttl_seconds=60, room_ttl_seconds=120, _env_file=None))
    state = store.create_room("Prompt media expiry")
    speaker = Participant(id="source", name="Source", language="hi")
    state.room.participants.append(speaker)
    token = store.issue_session(state, speaker.id)
    transport = RoomTransport(store, state, None, None)
    assert transport._speaker(speaker.id) is speaker
    store.sessions[token_digest(token)].expires_at = time.time() - 1
    # Roster is intentionally still present: the per-frame gate must not trust it.
    assert state.room.participants == [speaker]
    assert transport._speaker(speaker.id) is None
    assert not store.is_active(state.room.code, speaker.id)


async def test_shorter_membership_expiry_tears_down_source_work_and_voice_before_room_expiry():
    entered = asyncio.Event()

    class BlockedTranslator:
        async def translate(self, *_args):
            entered.set()
            await asyncio.Event().wait()

    store = Store(Settings(mode="demo", session_ttl_seconds=60, room_ttl_seconds=120, _env_file=None))
    state = store.create_room("Membership ends before room")
    speaker = Participant(id="source", name="Source", language="hi", voice_mode="cloned")
    listener = Participant(id="listener", name="Listener", language="ta")
    state.room.participants.extend((speaker, listener))
    token = store.issue_session(state, speaker.id)
    listener_token = store.issue_session(state, listener.id)
    profile = VoiceProfile(name="Consented fixture", mode="demo")
    store.voices[profile.id] = StoredVoice(profile, token_digest(token), {"embedding": "fixture"})
    state.voice_profiles[speaker.id] = profile.id
    pipeline = Pipeline(store, BlockedTranslator(), None)
    transport = RecordingTransport()
    service = RoomService(store, pipeline, transport, None)
    consumer = Consumer(asyncio.Queue(maxsize=20))
    state.consumers.add(consumer)
    try:
        await pipeline.submit(state, speaker, SAMPLES[0]["hi"])
        await asyncio.wait_for(entered.wait(), 1)
        await pipeline.submit(state, speaker, SAMPLES[1]["hi"])
        store.sessions[token_digest(token)].expires_at = time.time() - 1
        await service.prune_expired()
        assert state.expires_at > time.time()
        assert store.authenticate(listener_token).participant_id == listener.id
        assert state.room.participants == [listener]
        assert speaker.id not in state.voice_profiles
        assert profile.id not in store.voices
        assert token_digest(token) not in store.sessions
        assert all(turn.status == "error" for turn in state.turns)
        assert not pipeline.workers
        assert transport.removed == [(state.room.code, speaker.id)]
        assert transport.closed == []
        events = []
        while not consumer.queue.empty():
            events.append(consumer.queue.get_nowait())
        assert any(event["type"] == "participant.left" and event["payload"]["participant_id"] == speaker.id for event in events)
    finally:
        await pipeline.aclose()


async def test_expired_room_closes_pipeline_transport_and_consumers():
    store = Store(Settings(mode="demo", _env_file=None))
    state = store.create_room("Expired room")
    consumer = Consumer(asyncio.Queue(maxsize=1))
    state.consumers.add(consumer)
    speaker = Participant(id="source", name="Source", language="hi")
    state.room.participants.append(speaker)
    token = store.issue_session(state, speaker.id)
    pipeline = Pipeline(store, None, None)
    transport = RecordingTransport()
    service = RoomService(store, pipeline, transport, None)
    service.locks[state.room.code] = asyncio.Lock()
    state.expires_at = time.time() - 1
    await service.prune_expired()
    assert state.room.code not in store.rooms
    assert state.room.code not in service.locks
    assert token_digest(token) not in store.sessions
    assert transport.closed == [state.room.code]
    assert consumer.overflow.is_set()


async def test_expiry_between_enqueue_and_processing_never_starts_provider_work():
    class ForbiddenTranslator:
        def __init__(self):
            self.calls = 0

        async def translate(self, *_args):
            self.calls += 1
            raise AssertionError("Expired membership must not start translation")

    store = Store(Settings(mode="live", _env_file=None))
    state = store.create_room("Queued work expired")
    source = Participant(id="source", name="Source", language="hi")
    listener = Participant(id="listener", name="Listener", language="ta")
    state.room.participants.extend((source, listener))
    token = store.issue_session(state, source.id)
    store.issue_session(state, listener.id)
    translator = ForbiddenTranslator()
    pipeline = Pipeline(store, translator, None)
    try:
        await pipeline.submit(state, source, "queued source text")
        store.sessions[token_digest(token)].expires_at = time.time() - 1
        await asyncio.wait_for(pipeline.queues[(state.room.code, source.id)].join(), 1)
        assert state.turns[0].status == "error"
        assert state.turns[0].translations == {}
        assert translator.calls == 0
    finally:
        await pipeline.aclose()


async def test_expiry_during_translation_prevents_subsequent_voice_synthesis():
    store = Store(Settings(mode="live", _env_file=None))
    state = store.create_room("Expired while translating")
    source = Participant(id="source", name="Source", language="hi")
    listener = Participant(id="listener", name="Listener", language="ta")
    state.room.participants.extend((source, listener))
    token = store.issue_session(state, source.id)
    store.issue_session(state, listener.id)

    class ExpiringTranslator:
        async def translate(self, *_args):
            store.sessions[token_digest(token)].expires_at = time.time() - 1
            return "fixture Tamil output"

    class Speech:
        def __init__(self):
            self.calls = 0

        async def synthesize(self, *_args):
            self.calls += 1
            yield b"\x01\x00"

    class Transport:
        async def speak(self, _code, _speaker_id, _target, chunks, callback):
            async for _chunk in chunks:
                callback()

    speech = Speech()
    pipeline = Pipeline(store, ExpiringTranslator(), speech)
    pipeline.transport = Transport()
    try:
        await pipeline.submit(state, source, "accepted while membership was active")
        await asyncio.wait_for(pipeline.queues[(state.room.code, source.id)].join(), 1)
        assert state.turns[0].status == "error"
        assert speech.calls == 0
    finally:
        await pipeline.aclose()
