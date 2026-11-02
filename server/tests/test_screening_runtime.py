from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

import pytest

from artha_mesh.services.screening_runtime import ScreeningGate, ScreeningRuntime


class ControlledRuntime:
    def __init__(self, mode="enforce", verdict="allow", failure=False):
        self.mode, self.verdict, self.failure = mode, verdict, failure
        self.screener = SimpleNamespace(window_samples=320, window_ms=20)
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.inputs = []

    async def analyze(self, pcm):
        self.inputs.append(pcm)
        self.started.set()
        await self.release.wait()
        if self.failure:
            raise RuntimeError("inference unavailable")
        payload = {"verdict": self.verdict, "score": None, "compute_ms": 1, "audio_window_ms": 20}
        return SimpleNamespace(verdict=self.verdict, compute_ms=1, as_dict=lambda: dict(payload))


def fixture_gate(runtime):
    audio, results = [], []
    active = [True]

    async def on_audio(pcm):
        audio.append(pcm)

    async def on_result(result):
        results.append(result)

    return ScreeningGate(runtime, on_audio, on_result, lambda: active[0]), audio, results, active


async def test_monitor_forwards_immediately_while_model_runs():
    runtime = ControlledRuntime(mode="monitor", verdict="suspicious")
    gate, audio, results, _ = fixture_gate(runtime)
    pcm = b"\x01\x00" * 320
    try:
        await gate.feed(pcm)
        await runtime.started.wait()
        assert audio == [pcm]
        assert results == []
        runtime.release.set()
        await gate.queue.join()
        assert results[0]["action"] == "observed"
        assert results[0]["hold_ms"] == 0
        assert audio == [pcm]
    finally:
        await gate.close()


async def test_enforce_holds_complete_window_then_releases_only_allow():
    runtime = ControlledRuntime()
    gate, audio, results, _ = fixture_gate(runtime)
    try:
        await gate.feed(b"\x02\x00" * 160)
        assert not runtime.started.is_set()
        await gate.feed(b"\x03\x00" * 160)
        await runtime.started.wait()
        assert audio == []
        runtime.release.set()
        await gate.queue.join()
        assert b"".join(audio) == b"\x02\x00" * 160 + b"\x03\x00" * 160
        assert results[0]["action"] == "released"
        assert results[0]["hold_ms"] >= 20
    finally:
        await gate.close()


async def test_production_window_with_decoder_silence_needs_every_sample_and_verdict():
    runtime = ControlledRuntime()
    runtime.screener = SimpleNamespace(window_samples=64600, window_ms=4037.5)
    gate, audio, results, _ = fixture_gate(runtime)
    startup_silence = b"\x00\x00" * 8000
    signal = b"\x03\x00" * (64600 - 8000)
    try:
        # Decoded startup silence can arrive before a tone/capture timer starts;
        # enforcement is defined by all 64,600 PCM samples, not that later clock.
        await gate.feed(startup_silence)
        await gate.feed(signal[:-2])
        await asyncio.sleep(0)
        assert runtime.inputs == audio == results == []
        await gate.feed(signal[-2:])
        await runtime.started.wait()
        assert runtime.inputs == [startup_silence + signal]
        assert audio == results == []
        runtime.release.set()
        await gate.queue.join()
        assert b"".join(audio) == startup_silence + signal
        assert results[0]["action"] == "released"
        assert results[0]["hold_ms"] >= 4037.5
    finally:
        await gate.close()


@pytest.mark.parametrize("verdict,failure", [("suspicious", False), ("unknown", False), ("allow", True)])
async def test_enforce_never_releases_suspicious_unknown_or_errors(verdict, failure):
    runtime = ControlledRuntime(verdict=verdict, failure=failure)
    runtime.release.set()
    gate, audio, results, _ = fixture_gate(runtime)
    try:
        await gate.feed(b"\x04\x00" * 320)
        await gate.queue.join()
        assert audio == []
        assert results[0]["action"] == "withheld"
        assert results[0]["verdict"] == ("unknown" if failure else verdict)
    finally:
        await gate.close()


async def test_overload_drops_new_window_and_bounds_pending_work():
    runtime = ControlledRuntime()
    gate, audio, results, _ = fixture_gate(runtime)
    first, second, dropped = [bytes([value, 0]) * 320 for value in (1, 2, 3)]
    try:
        await gate.feed(first)
        await runtime.started.wait()
        await gate.feed(second)
        await gate.feed(dropped)
        assert gate.queue.qsize() == 1
        assert len(gate.buffer) < gate.window_bytes
        assert results[0]["status"] == "overload"
        assert results[0]["action"] == "withheld"
        runtime.release.set()
        await gate.queue.join()
        assert runtime.inputs == [first, second]
        assert b"".join(audio) == first + second
    finally:
        await gate.close()


async def test_mute_during_analysis_suppresses_result_and_late_audio():
    runtime = ControlledRuntime()
    gate, audio, results, active = fixture_gate(runtime)
    try:
        await gate.feed(b"\x01\x00" * 320)
        await runtime.started.wait()
        active[0] = False
        runtime.release.set()
        await gate.queue.join()
        await gate.feed(b"\x02\x00" * 320)
        assert audio == results == []
        assert gate.buffer == b""
    finally:
        await gate.close()


async def test_close_discards_partial_and_pending_windows():
    runtime = ControlledRuntime()
    gate, audio, results, _ = fixture_gate(runtime)
    await gate.feed(b"\x01\x00" * 320)
    await runtime.started.wait()
    await gate.feed(b"\x02\x00" * 400)
    await gate.close()
    runtime.release.set()
    await gate.feed(b"\x03\x00" * 320)
    assert gate.closed
    assert gate.queue.empty()
    assert gate.buffer == b""
    assert audio == results == []


async def test_off_passes_without_collecting_or_classifying():
    runtime = ControlledRuntime(mode="off")
    gate, audio, results, _ = fixture_gate(runtime)
    try:
        await gate.feed(b"\x01\x00" * 160)
        assert len(audio) == 1
        assert results == runtime.inputs == []
        assert gate.buffer == b""
    finally:
        await gate.close()


async def test_result_consumer_failure_keeps_worker_alive_and_enforce_closed():
    runtime = ControlledRuntime()
    runtime.release.set()
    audio = []
    fail = [True]

    async def on_audio(pcm):
        audio.append(pcm)

    async def on_result(_result):
        if fail[0]:
            raise RuntimeError("event consumer unavailable")

    gate = ScreeningGate(runtime, on_audio, on_result, lambda: True)
    try:
        await gate.feed(b"\x01\x00" * 320)
        await gate.queue.join()
        assert audio == []
        assert not gate.task.done()
        fail[0] = False
        await gate.feed(b"\x02\x00" * 320)
        await gate.queue.join()
        assert audio == [b"\x02\x00" * 320]
    finally:
        await gate.close()


async def test_cpu_slots_remain_held_after_repeated_cancellation(monkeypatch):
    import artha_mesh.services.screening_runtime as module

    release = threading.Event()
    lock = threading.Lock()
    counters = {"started": 0, "running": 0, "maximum": 0}

    class BlockingScreener:
        def analyze(self, *_):
            with lock:
                counters["started"] += 1
                counters["running"] += 1
                counters["maximum"] = max(counters["maximum"], counters["running"])
            try:
                assert release.wait(5)
                return None
            finally:
                with lock:
                    counters["running"] -= 1

    monkeypatch.setattr(module, "LocalAudioScreener", lambda _path, **_options: BlockingScreener())
    runtime = ScreeningRuntime(SimpleNamespace(audio_screening_mode="monitor", audio_screening_model_path=None))
    tasks = [asyncio.create_task(runtime.analyze(b"xx")) for _ in range(3)]
    try:
        async with asyncio.timeout(2):
            while counters["started"] < 2:
                await asyncio.sleep(.001)
        tasks[0].cancel()
        await asyncio.sleep(.01)
        tasks[0].cancel()
        await asyncio.sleep(.03)
        assert counters["started"] == 2, "Cancellation released a CPU slot while native inference was still running"
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)
    assert counters["maximum"] <= 2
