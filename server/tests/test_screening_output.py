from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from artha_mesh.config import Settings
from artha_mesh.errors import ProviderError
from artha_mesh.models import Participant
from artha_mesh.store import Store
from artha_mesh.transport.livekit import OutputTrack, RoomTransport


def transport_fixture(monkeypatch, *, same_language=False):
    store = Store(Settings(mode="live", _env_file=None, audio_screening_mode="enforce"))
    state = store.create_room("Screened output cancellation")
    target = "hi" if same_language else "ta"
    for person in (Participant(id="source", name="Asha", language="hi"),
                   Participant(id="listener", name="Kavya", language=target)):
        state.room.participants.append(person)
        store.issue_session(state, person.id)
    state.screening_latest["source"] = {"action": "released"}
    transport = RoomTransport(store, state, None, None, SimpleNamespace(mode="enforce"))
    monkeypatch.setattr(transport, "_permissions", lambda: None)
    return transport, state, target


def output_fixture(monkeypatch, transport, state, *, flip_during_capture=False, sample_rate=24000):
    captured, cleared, consumed, callbacks = [], [], [], []

    async def capture(frame):
        captured.append(bytes(frame.data))
        if flip_during_capture:
            await asyncio.sleep(0)
            state.screening_latest["source"] = {"action": "withheld"}

    async def noop():
        pass

    output = OutputTrack(
        SimpleNamespace(capture_frame=capture, clear_queue=lambda: cleared.append(True), wait_for_playout=noop),
        SimpleNamespace(wait_for_subscription=noop), "source", "ta", sample_rate,
    )

    async def get_output(*_):
        return output

    async def chunks():
        consumed.append(True)
        yield b"\x10\x00" * 480

    monkeypatch.setattr(transport, "_output", get_output)
    return output, captured, cleared, consumed, callbacks, chunks


@pytest.mark.parametrize("action", ["withheld", None])
async def test_withheld_or_unassessed_tts_never_consumes_provider_generator(monkeypatch, action):
    transport, state, target = transport_fixture(monkeypatch)
    _, captured, _, consumed, callbacks, chunks = output_fixture(monkeypatch, transport, state)
    state.screening_latest["source"] = {"action": action}
    with pytest.raises(ProviderError, match="withholding"):
        await transport.speak("source", target, chunks(), lambda: callbacks.append(True))
    assert consumed == captured == callbacks == []


async def test_tts_inflight_capture_revocation_clears_queue_and_never_announces_first_audio(monkeypatch):
    transport, state, target = transport_fixture(monkeypatch)
    output, captured, cleared, consumed, callbacks, chunks = output_fixture(
        monkeypatch, transport, state, flip_during_capture=True,
    )
    with pytest.raises(ProviderError, match="withheld"):
        await transport.speak("source", target, chunks(), lambda: callbacks.append(True))
    assert len(captured) == len(consumed) == 1
    assert len(cleared) >= 2  # normal initial clear, then clear after revocation
    assert callbacks == []
    assert output.tts_active is False


async def test_tts_rechecks_revocation_after_listener_wait_before_provider_consumption(monkeypatch):
    transport, state, target = transport_fixture(monkeypatch)
    output, captured, _, consumed, callbacks, chunks = output_fixture(monkeypatch, transport, state)

    async def listener_ready():
        await asyncio.sleep(0)
        state.screening_latest["source"] = {"action": "withheld"}

    output.publication.wait_for_subscription = listener_ready
    with pytest.raises(ProviderError, match="withholding"):
        await transport.speak("source", target, chunks(), lambda: callbacks.append(True))
    assert captured == consumed == callbacks == []


async def test_resampler_tail_cannot_bypass_revoked_screening(monkeypatch):
    from livekit import rtc

    transport, state, target = transport_fixture(monkeypatch)
    _, captured, cleared, consumed, callbacks, chunks = output_fixture(monkeypatch, transport, state, sample_rate=16000)

    class TailResampler:
        def __init__(self, *_args, **_kwargs):
            pass

        def push(self, frame):
            self.frame = frame
            return []

        def flush(self):
            state.screening_latest["source"] = {"action": "withheld"}
            return [self.frame]

    monkeypatch.setattr(rtc, "AudioResampler", TailResampler)
    with pytest.raises(ProviderError, match="withheld"):
        await transport.speak("source", target, chunks(), lambda: callbacks.append(True))
    assert consumed == [True]
    assert captured == callbacks == []
    assert len(cleared) >= 2


@pytest.mark.parametrize("flip_stage", ["listener_wait", "capture"])
async def test_same_language_forwarding_rechecks_screening_and_flushes_inflight_audio(monkeypatch, flip_stage):
    from livekit import rtc
    from artha_mesh.transport import livekit

    transport, state, _ = transport_fixture(monkeypatch, same_language=True)
    captured, cleared = [], []
    reached = asyncio.Event()

    class AudioStream:
        def __init__(self, **_kwargs):
            self.sent = False

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.sent:
                await asyncio.Event().wait()
            self.sent = True
            return SimpleNamespace(frame=SimpleNamespace(data=b"\x10\x00" * 320))

        async def aclose(self):
            pass

    class Resampler:
        def __init__(self, *_args, **_kwargs):
            pass

        def push(self, frame):
            return [frame]

    class AlreadyScreenedGate:
        """Supply one previously approved window to exercise the downstream race."""
        def __init__(self, _runtime, dispatch, _result, _active):
            self.dispatch = dispatch

        async def feed(self, data):
            await self.dispatch(data)

        async def close(self):
            pass

    async def capture(frame):
        captured.append(bytes(frame.data))
        if flip_stage == "capture":
            await asyncio.sleep(0)
            state.screening_latest["source"] = {"action": "withheld"}
            reached.set()

    async def ready():
        if flip_stage == "listener_wait":
            await asyncio.sleep(0)
            state.screening_latest["source"] = {"action": "withheld"}
            reached.set()

    async def output(_speaker, language, _rate):
        assert language == "hi"
        return SimpleNamespace(tts_active=False, source=SimpleNamespace(capture_frame=capture, clear_queue=lambda: cleared.append(True)),
                               publication=SimpleNamespace(wait_for_subscription=ready))

    monkeypatch.setattr(rtc, "AudioStream", AudioStream)
    monkeypatch.setattr(rtc, "AudioResampler", Resampler)
    monkeypatch.setattr(livekit, "ScreeningGate", AlreadyScreenedGate)
    monkeypatch.setattr(transport, "_output", output)
    task = asyncio.create_task(transport._read_audio(object(), "source"))
    try:
        async with asyncio.timeout(2):
            await reached.wait()
        await asyncio.sleep(.02)
        if flip_stage == "listener_wait":
            assert captured == []
        else:
            assert len(captured) == 1
            assert cleared == [True]
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
