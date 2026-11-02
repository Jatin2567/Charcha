"""Transport credit admission/lifecycle checks with synthetic in-process frames."""
import asyncio
import time
from types import SimpleNamespace

import pytest

from artha_mesh.config import Settings
from artha_mesh.errors import ProviderError
from artha_mesh.models import Participant
from artha_mesh.services.pipeline import Pipeline
from artha_mesh.services.rooms import RoomService
from artha_mesh.store import Consumer, Store
from artha_mesh.transport.livekit import RoomTransport


class FakeAudioStream:
    def __init__(self, **_kwargs):
        self.closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.sleep(0.01)
        return SimpleNamespace(frame=SimpleNamespace(data=b"\x00" * 320))

    async def aclose(self):
        self.closed = True


class FakeResampler:
    def __init__(self, *_args, **_kwargs):
        pass


def transport_fixture(monkeypatch, speech, **settings):
    from livekit import rtc

    monkeypatch.setattr(rtc, "AudioStream", FakeAudioStream)
    monkeypatch.setattr(rtc, "AudioResampler", FakeResampler)
    store = Store(Settings(mode="live", _env_file=None, **settings))
    state = store.create_room("Credit-efficient stream")
    speaker = Participant(id="source", name="Source", language="hi", muted=True)
    listener = Participant(id="listener", name="Listener", language="ta")
    state.room.participants.extend((speaker, listener))
    for member in state.room.participants:
        store.issue_session(state, member.id)
    consumer = Consumer(asyncio.Queue(maxsize=100))
    state.consumers.add(consumer)
    return store, state, speaker, listener, consumer, RoomTransport(store, state, speech, None)


async def until(predicate, seconds=1):
    async with asyncio.timeout(seconds):
        while not predicate():
            await asyncio.sleep(0.01)


async def test_muted_empty_room_and_listener_departure_do_not_burn_stt(monkeypatch):
    class Speech:
        opened = 0
        closed = 0

        async def transcribe(self, *_args):
            self.opened += 1
            try:
                await asyncio.Event().wait()
                yield None
            finally:
                self.closed += 1

    speech = Speech()
    store, state, speaker, listener, _, transport = transport_fixture(monkeypatch, speech, stt_mute_grace_seconds=0)
    task = asyncio.create_task(transport._read_audio(object(), speaker.id))
    try:
        await asyncio.sleep(0.3)
        assert speech.opened == 0  # Source starts server-muted.
        state.room.participants.remove(listener)
        speaker.muted = False
        await asyncio.sleep(0.3)
        assert speech.opened == 0  # Unmuted alone also stays free.
        state.room.participants.append(listener)
        await until(lambda: speech.opened == 1)
        speaker.muted = True
        await until(lambda: speech.closed == 1)
        speaker.muted = False
        await until(lambda: speech.opened == 2)
        state.room.participants.remove(listener)
        await until(lambda: speech.closed == 2)
        await asyncio.sleep(0.3)
        assert speech.opened == 2
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_same_language_only_roster_skips_stt_until_translation_is_needed(monkeypatch):
    class Speech:
        opened = 0
        closed = 0

        async def transcribe(self, *_args):
            self.opened += 1
            try:
                await asyncio.Event().wait()
                yield None
            finally:
                self.closed += 1

    speech = Speech()
    _, _, speaker, listener, _, transport = transport_fixture(monkeypatch, speech)
    speaker.muted = False
    listener.language = speaker.language
    # Keep this test focused on recognizer admission; the existing real RTC
    # same-language routing check separately verifies forwarded audio playout.
    monkeypatch.setattr("artha_mesh.transport.livekit.recipients_for", lambda *_args: [])
    task = asyncio.create_task(transport._read_audio(object(), speaker.id))
    try:
        await asyncio.sleep(0.3)
        assert speech.opened == 0
        listener.language = "ta"
        await until(lambda: speech.opened == 1)
        listener.language = "hi"
        await until(lambda: speech.closed == 1)
        await asyncio.sleep(0.3)
        assert speech.opened == 1
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("retryable,max_retries,expected", [(False, 3, 1), (True, 2, 3), (True, 0, 1)])
async def test_stt_auth_quota_errors_and_repeated_transient_failures_stop(monkeypatch, retryable, max_retries, expected):
    class FailingSpeech:
        calls = 0

        async def transcribe(self, *_args):
            self.calls += 1
            raise ProviderError("Sanitized provider failure", retryable)
            yield None

    speech = FailingSpeech()
    _, _, speaker, _, consumer, transport = transport_fixture(
        monkeypatch, speech, usage_stt_max_retries=max_retries,
    )
    speaker.muted = False
    real_sleep = asyncio.sleep

    async def fast_sleep(seconds):
        await real_sleep(min(seconds, 0.01))

    monkeypatch.setattr("artha_mesh.transport.livekit.asyncio.sleep", fast_sleep)
    task = asyncio.create_task(transport._read_audio(object(), speaker.id))
    try:
        await until(lambda: speech.calls == expected)
        await real_sleep(0.05)
        assert speech.calls == expected
        errors = []
        while not consumer.queue.empty():
            event = consumer.queue.get_nowait()
            if event["type"] == "pipeline.error":
                errors.append(event["payload"])
        assert errors[-1]["retryable"] is False
        assert not task.done()  # The free forwarding/receive path remains available.
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_live_room_duration_caps_membership_and_expiry_removes_humans_from_sfu():
    class Transport:
        def __init__(self):
            self.removed = []
            self.closed = []

        async def remove(self, code, participant_id):
            self.removed.append((code, participant_id))

        async def close_room(self, code):
            self.closed.append(code)

    settings = Settings(mode="live", room_ttl_seconds=14400,
                        usage_max_live_room_seconds=900, _env_file=None)
    store = Store(settings)
    started = time.time()
    state = store.create_room("Bounded LiveKit room")
    human = Participant(id="human", name="Human", language="hi")
    state.room.participants.extend((human, Participant(id="agent", name="Agent", language="en", is_agent=True)))
    token = store.issue_session(state, human.id)
    assert 899 <= state.expires_at - started <= 901
    assert store.authenticate(token).expires_at == state.expires_at
    pipeline, transport = Pipeline(store, None, None), Transport()
    service = RoomService(store, pipeline, transport, None)
    state.expires_at = time.time() - 1
    await service.prune_expired()
    assert transport.removed == [(state.room.code, human.id)]
    assert transport.closed == [state.room.code]
    assert not store.sessions
