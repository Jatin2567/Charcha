"""A provider's valid short first PCM chunk must not await a later chunk."""
import asyncio
from types import SimpleNamespace

import pytest

from charcha.config import Settings
from charcha.models import Participant
from charcha.store import Store
from charcha.transport.livekit import OutputTrack, RoomTransport


def fixture(monkeypatch, rate=24000):
    store = Store(Settings(mode="live", audio_sample_rate=rate, _env_file=None))
    state = store.create_room("First PCM fixture")
    for person in (Participant(id="source", name="Source", language="ta"),
                   Participant(id="listener", name="Listener", language="hi")):
        state.room.participants.append(person)
        store.issue_session(state, person.id)
    transport = RoomTransport(store, state, None, None)
    captured, callbacks, clears = [], [], []

    async def capture(frame):
        assert frame.sample_rate == rate and frame.num_channels == 1
        captured.append(bytes(frame.data))

    async def ready_or_drain():
        pass

    output = OutputTrack(
        SimpleNamespace(capture_frame=capture, clear_queue=lambda: clears.append(True),
                        wait_for_playout=ready_or_drain),
        SimpleNamespace(wait_for_subscription=ready_or_drain), "source", "hi", rate,
    )

    async def get_output(*_args):
        return output

    monkeypatch.setattr(transport, "_output", get_output)
    monkeypatch.setattr(transport, "_permissions", lambda: None)
    return transport, output, captured, callbacks, clears


@pytest.mark.parametrize("rate", [16000, 24000])
async def test_short_first_pcm_is_dispatched_before_delayed_second_provider_chunk(monkeypatch, rate):
    transport, _, captured, callbacks, _ = fixture(monkeypatch, rate)
    waiting, release = asyncio.Event(), asyncio.Event()
    prefix = b"\x10\x00" * (rate // 100)  # 10ms, smaller than normal20ms batching.
    tail = b"\x20\x00" * (rate // 50 * 2)

    async def chunks():
        yield prefix
        waiting.set()
        await release.wait()
        yield tail

    task = asyncio.create_task(transport.speak("source", "hi", chunks(), lambda: callbacks.append(True)))
    try:
        await asyncio.wait_for(waiting.wait(), 1)
        assert captured == [prefix], "First PCM was held until the next provider chunk"
        assert callbacks == [True]
        release.set()
        await asyncio.wait_for(task, 1)
        assert b"".join(captured) == prefix + tail
        assert [len(chunk) for chunk in captured[1:]] == [rate // 50 * 2] * 2
        assert callbacks == [True]
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


async def test_short_first_pcm_preserves_odd_byte_carry_without_padding_or_reordering(monkeypatch):
    transport, _, captured, callbacks, _ = fixture(monkeypatch)
    waiting, release = asyncio.Event(), asyncio.Event()
    prefix, tail = b"\x01\x02\x03", b"\x04\x05\x06"

    async def chunks():
        yield prefix
        waiting.set()
        await release.wait()
        yield tail

    task = asyncio.create_task(transport.speak("source", "hi", chunks(), lambda: callbacks.append(True)))
    try:
        await asyncio.wait_for(waiting.wait(), 1)
        assert captured == [prefix[:2]] and callbacks == [True]
        release.set()
        await asyncio.wait_for(task, 1)
        assert captured == [b"\x01\x02", b"\x03\x04\x05\x06"]
        assert b"".join(captured) == prefix + tail and callbacks == [True]
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


async def test_incomplete_single_byte_waits_for_a_whole_sample(monkeypatch):
    transport, _, captured, callbacks, _ = fixture(monkeypatch)
    waiting, release = asyncio.Event(), asyncio.Event()

    async def chunks():
        yield b"\x01"
        waiting.set()
        await release.wait()
        yield b"\x00"

    task = asyncio.create_task(transport.speak("source", "hi", chunks(), lambda: callbacks.append(True)))
    try:
        await asyncio.wait_for(waiting.wait(), 1)
        assert captured == [] and callbacks == []
        release.set()
        await asyncio.wait_for(task, 1)
        assert captured == [b"\x01\x00"] and callbacks == [True]
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


async def test_cancellation_after_first_pcm_clears_output_and_closes_waiting_source(monkeypatch):
    transport, output, captured, callbacks, clears = fixture(monkeypatch)
    waiting, closed = asyncio.Event(), asyncio.Event()

    async def chunks():
        try:
            yield b"\x10\x00" * 240
            waiting.set()
            await asyncio.Event().wait()
        finally:
            closed.set()

    task = asyncio.create_task(transport.speak("source", "hi", chunks(), lambda: callbacks.append(True)))
    await asyncio.wait_for(waiting.wait(), 1)
    try:
        assert captured and callbacks == [True]
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert closed.is_set() and output.tts_active is False and len(clears) == 2
