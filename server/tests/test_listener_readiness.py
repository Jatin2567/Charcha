import asyncio
from types import SimpleNamespace

import pytest

from charcha.config import Settings
from charcha.errors import ProviderError
from charcha.models import Participant
from charcha.store import Store
from charcha.transport.livekit import OutputTrack, RoomTransport


def fixture(monkeypatch):
    store = Store(Settings(mode="live", _env_file=None))
    state = store.create_room("Local listener readiness fixture")
    for participant in (Participant(id="source", name="A", language="hi"),
                        Participant(id="listener", name="B", language="ta")):
        state.room.participants.append(participant)
        store.issue_session(state, participant.id)
    transport = RoomTransport(store, state, None, None)
    ready = asyncio.Event()
    captured = []
    used = []

    async def capture(frame):
        captured.append(bytes(frame.data))

    async def drain():
        pass

    output = OutputTrack(SimpleNamespace(capture_frame=capture, clear_queue=lambda: None, wait_for_playout=drain),
                         SimpleNamespace(wait_for_subscription=ready.wait), "source", "ta", 24000)

    async def get_output(*_args):
        return output

    async def chunks():
        used.append("tts-generator-started")
        yield b"\x10\x00" * 480

    monkeypatch.setattr(transport, "_output", get_output)
    monkeypatch.setattr(transport, "_permissions", lambda: None)
    return transport, state, ready, captured, used, chunks


async def test_synthesis_is_not_consumed_until_real_listener_subscription(monkeypatch):
    transport, _, ready, captured, used, chunks = fixture(monkeypatch)
    callbacks = []
    task = asyncio.create_task(transport.speak("source", "ta", chunks(), lambda: callbacks.append(True)))
    await asyncio.sleep(0.02)
    assert used == [] and captured == [] and callbacks == []
    ready.set()
    await task
    assert used == ["tts-generator-started"] and len(captured) == 1 and callbacks == [True]


async def test_subscription_timeout_consumes_no_synthesis(monkeypatch):
    from charcha.transport import livekit
    monkeypatch.setattr(livekit, "LISTENER_READY_TIMEOUT_SECONDS", 0.02)
    transport, _, _, captured, used, chunks = fixture(monkeypatch)
    with pytest.raises(ProviderError, match="not ready"):
        await transport.speak("source", "ta", chunks(), lambda: None)
    assert used == [] and captured == []


async def test_cancelled_subscription_wait_consumes_no_synthesis(monkeypatch):
    transport, _, _, captured, used, chunks = fixture(monkeypatch)
    task = asyncio.create_task(transport.speak("source", "ta", chunks(), lambda: None))
    await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert used == [] and captured == []


async def test_listener_leaving_while_negotiating_is_rechecked_before_synthesis(monkeypatch):
    transport, state, ready, captured, used, chunks = fixture(monkeypatch)
    task = asyncio.create_task(transport.speak("source", "ta", chunks(), lambda: None))
    await asyncio.sleep(0.02)
    state.room.participants = [p for p in state.room.participants if p.id != "listener"]
    ready.set()
    with pytest.raises(ProviderError, match="listener left"):
        await task
    assert used == [] and captured == []
