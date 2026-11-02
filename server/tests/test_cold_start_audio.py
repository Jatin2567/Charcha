"""A slow first subscriber must not turn decoder startup silence into speech delay."""
import asyncio
from types import SimpleNamespace

import pytest

from artha_mesh.config import Settings
from artha_mesh.models import Participant
from artha_mesh.store import Store
from artha_mesh.transport.livekit import RoomTransport


ZERO = b"\x00\x00" * 320


def room(mode="transport"):
    store = Store(Settings(mode=mode, _env_file=None))
    state = store.create_room("Cold source subscription")
    source = Participant(id="source", name="Source", language="hi", muted=False)
    listener = Participant(id="listener", name="Listener", language="ta", muted=False)
    for person in (source, listener):
        state.room.participants.append(person)
        store.issue_session(state, person.id)
    return RoomTransport(store, state, None, None), source


def delayed_receiver(monkeypatch):
    from livekit import rtc

    transport, source = room()
    input_frames = asyncio.Queue()
    received = []
    captured = []
    stream_closed = asyncio.Event()
    negotiating = asyncio.Event()
    ready = asyncio.Event()
    ready_resolved = asyncio.Event()
    captured_event = asyncio.Event()

    class InputStream:
        def __init__(self, **_kwargs):
            pass

        def __aiter__(self):
            return self

        async def __anext__(self):
            data = await input_frames.get()
            received.append(data)
            input_frames.task_done()
            return SimpleNamespace(frame=SimpleNamespace(data=data))

        async def aclose(self):
            stream_closed.set()

    class Resampler:
        def __init__(self, *_args, **_kwargs):
            pass

        def push(self, frame):
            return [frame]

    async def capture(frame):
        captured.append(bytes(frame.data))
        captured_event.set()

    async def wait_for_subscription():
        negotiating.set()
        await ready.wait()
        ready_resolved.set()

    output = SimpleNamespace(
        tts_active=False,
        source=SimpleNamespace(capture_frame=capture, clear_queue=lambda: None),
        publication=SimpleNamespace(wait_for_subscription=wait_for_subscription),
    )

    async def get_output(*_args):
        return output

    monkeypatch.setattr(rtc, "AudioStream", InputStream)
    monkeypatch.setattr(rtc, "AudioResampler", Resampler)
    monkeypatch.setattr(transport, "_output", get_output)
    monkeypatch.setattr(transport, "_permissions", lambda: None)
    return SimpleNamespace(
        transport=transport, source=source, input=input_frames, received=received,
        captured=captured, negotiating=negotiating, ready=ready,
        ready_resolved=ready_resolved, captured_event=captured_event,
        closed=stream_closed,
    )


@pytest.mark.parametrize("sample", [b"\x01\x00", b"\xff\xff"])
async def test_delayed_subscriber_skips_only_leading_exact_zero_and_preserves_quiet_audio(monkeypatch, sample):
    fixture = delayed_receiver(monkeypatch)
    task = asyncio.create_task(fixture.transport._read_audio(object(), "source"))
    quiet = sample * 320  # +/-1 PCM: much quieter than a speech/activity threshold.
    tail = b"\x09\x00" * 320
    try:
        # Negotiate using an empty decoder frame before the source speaks.
        fixture.input.put_nowait(ZERO)
        async with asyncio.timeout(1):
            await fixture.negotiating.wait()
        assert fixture.captured == []
        assert fixture.received == [ZERO]
        for frame in [ZERO] * 80 + [quiet, ZERO, tail]:
            fixture.input.put_nowait(frame)
        async with asyncio.timeout(1):
            await fixture.input.join()
        assert fixture.captured == []  # No audio before actual subscription.
        fixture.ready.set()
        async with asyncio.timeout(1):
            while len(fixture.captured) < 3:
                fixture.captured_event.clear()
                await fixture.captured_event.wait()
        # The onset and following pause survive unchanged; old silence does not.
        assert fixture.captured == [quiet, ZERO, tail]
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert fixture.closed.is_set()


@pytest.mark.parametrize("stop", ["mute", "cancel"])
async def test_mute_or_cancel_during_startup_readiness_cannot_release_buffered_audio(monkeypatch, stop):
    fixture = delayed_receiver(monkeypatch)
    task = asyncio.create_task(fixture.transport._read_audio(object(), "source"))
    try:
        fixture.input.put_nowait(ZERO)
        fixture.input.put_nowait(b"\x10\x00" * 320)
        async with asyncio.timeout(1):
            await fixture.negotiating.wait()
            await fixture.input.join()
        assert fixture.captured == []
        if stop == "mute":
            fixture.source.muted = True
            fixture.ready.set()
            async with asyncio.timeout(1):
                await fixture.ready_resolved.wait()
        else:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            fixture.ready.set()
            assert fixture.closed.is_set()
        assert fixture.captured == []
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("mode,language,expected_ms", [("transport", "all", 60), ("live", "ta", 250)])
async def test_raw_output_has_short_queue_without_changing_synthesized_output_buffer(monkeypatch, mode, language, expected_ms):
    from livekit import rtc

    transport, _ = room(mode)
    created = []

    class Source:
        def __init__(self, rate, channels, queue_size_ms):
            created.append((rate, channels, queue_size_ms))

        async def aclose(self):
            pass

    async def publish(*_args):
        return SimpleNamespace(sid="output")

    monkeypatch.setattr(rtc, "AudioSource", Source)
    monkeypatch.setattr(rtc.LocalAudioTrack, "create_audio_track", lambda *_: object())
    monkeypatch.setattr(transport, "_permissions", lambda: None)
    transport.room = SimpleNamespace(local_participant=SimpleNamespace(publish_track=publish))
    output = await transport._output("source", language, 24000)
    assert created == [(24000, 1, expected_ms)]
    assert output is await transport._output("source", language, 24000)
    assert len(created) == 1  # No replacement buffer per PCM frame.
