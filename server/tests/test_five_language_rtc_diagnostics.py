"""Offline verifier evidence must preserve partial failures without secrets."""
import importlib.util
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace


def verifier():
    path = Path(__file__).resolve().parents[2] / "scripts/verify_five_language_routing.py"
    spec = importlib.util.spec_from_file_location("five_language_rtc_diagnostics", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def environment():
    runtime = SimpleNamespace(
        transport=SimpleNamespace(rooms={"room": SimpleNamespace(outputs={("speaker-hi", "ta"): None})}),
        pipeline=SimpleNamespace(queues={}),
    )
    state = SimpleNamespace(room=SimpleNamespace(code="room"), performance_samples=[])
    memberships = [{"participant": SimpleNamespace(id="speaker-hi", language="hi"),
                    "session_token": "must-not-appear"},
                   {"participant": SimpleNamespace(id="listener-ta", language="ta"),
                    "session_token": "must-not-appear"}]
    return runtime, state, memberships


def test_failure_snapshot_distinguishes_capture_stall_from_missing_delivery():
    module = verifier()
    runtime, state, memberships = environment()
    fixture = module.Providers()
    fixture.recognition_opened.update({"hi": 1})
    fixture.translations.append(("hi", "ta"))
    progress = {"hi": {"requested_frames": 42, "captured_frames": 41,
                       "source_playout_completed": False}}
    snapshot = module.fixture_snapshot(runtime, state, fixture, memberships, {}, progress, [])
    assert snapshot["source_progress"]["hi"]["captured_frames"] == 41
    assert snapshot["source_progress"]["hi"]["requested_frames"] == 42
    assert snapshot["received_route_count"] == 0
    assert snapshot["missing_recipient_routes"] == [
        {"source_language": "hi", "target_language": "ta", "listener_peer": 2},
        {"source_language": "ta", "target_language": "hi", "listener_peer": 1},
    ]
    encoded = json.dumps(snapshot)
    assert "must-not-appear" not in encoded
    assert "speaker-hi" not in encoded
    assert "latency" not in encoded
    progress["hi"]["captured_frames"] = 100
    assert snapshot["source_progress"]["hi"]["captured_frames"] == 41


def test_failure_snapshot_does_not_replace_setup_failure_with_missing_transport():
    module = verifier()
    runtime, state, memberships = environment()
    runtime.transport.rooms.clear()
    snapshot = module.fixture_snapshot(runtime, state, module.Providers(), [], {}, {}, [])
    assert snapshot["output_tracks"] == []
    assert snapshot["missing_recipient_routes"] == []


def test_failure_snapshot_counts_observed_routes_without_calling_them_full_acceptance():
    module = verifier()
    runtime, state, memberships = environment()
    received = {"listener-ta": {"translated:speaker-hi:ta": 320}}
    snapshot = module.fixture_snapshot(runtime, state, module.Providers(), memberships, received, {}, [])
    assert snapshot["received_route_count"] == 1
    assert snapshot["missing_recipient_routes"] == [
        {"source_language": "ta", "target_language": "hi", "listener_peer": 1},
    ]
    assert "passed" not in snapshot


def audio_observer(monkeypatch):
    module = verifier()
    frames = asyncio.Queue()
    closed = asyncio.Event()
    consumed = []
    parameters = []

    class Stream:
        def __init__(self, _track, **kwargs):
            parameters.append(kwargs)

        def __aiter__(self):
            return self

        async def __anext__(self):
            data = await frames.get()
            consumed.append(data)
            return SimpleNamespace(frame=SimpleNamespace(data=memoryview(data), samples_per_channel=len(data) // 2))

        async def aclose(self):
            closed.set()

    monkeypatch.setattr(module.rtc, "AudioStream", Stream)
    received, first_pcm, streams = {"listener": {}}, {}, []
    task = asyncio.create_task(module.observe_first_audio(
        object(), "route", "listener", received, first_pcm, streams,
    ))
    return task, frames, closed, consumed, parameters, received, first_pcm, streams


async def test_decoder_silence_does_not_complete_first_pcm_observation(monkeypatch):
    task, frames, closed, consumed, parameters, received, first_pcm, streams = audio_observer(monkeypatch)
    frames.put_nowait(b"\x00\x00" * 320)
    frames.put_nowait(b"\x01\x00" * 320)
    try:
        await asyncio.sleep(.01)
        assert len(consumed) == 2
        assert not task.done() and not closed.is_set()
        assert received == {"listener": {}} and first_pcm == {}
        assert parameters[0]["capacity"] == 8
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert closed.is_set() and streams == []


async def test_first_nonzero_proof_closes_observer_without_consuming_later_frames(monkeypatch):
    task, frames, closed, consumed, _, received, first_pcm, streams = audio_observer(monkeypatch)
    frames.put_nowait(b"\x00\x00" * 320)
    frames.put_nowait(b"\x00\x10" * 320)
    frames.put_nowait(b"\x00\x20" * 320)
    await asyncio.wait_for(task, 1)
    assert len(consumed) == 2 and frames.qsize() == 1
    assert received == {"listener": {"route": 320}}
    assert first_pcm[("listener", "route")] > 0
    assert closed.is_set() and streams == []


async def test_cancelled_pcm_observer_closes_without_recording_audible_route(monkeypatch):
    task, _, closed, _, _, received, first_pcm, streams = audio_observer(monkeypatch)
    await asyncio.sleep(.01)
    assert len(streams) == 1
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert closed.is_set() and streams == []
    assert received == {"listener": {}} and first_pcm == {}
