"""Bounded, local-only screening. Scores are experimental, never identity proof."""
from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from .audio_screening import LocalAudioScreener


class ScreeningRuntime:
    def __init__(self, settings):
        self.mode = settings.audio_screening_mode
        self.screener = LocalAudioScreener(
            settings.audio_screening_model_path,
            load_model=self.mode != "off" or settings.local_audio_lab_enabled,
            cpu_threads=getattr(settings, "audio_screening_cpu_threads", 1),
        )
        self._slots = asyncio.Semaphore(2)

    async def analyze(self, pcm: bytes):
        # Keep CPU work off the RTC/event loop; cancellation must not release a
        # slot while its native inference thread is still running.
        async with self._slots:
            task = asyncio.create_task(asyncio.to_thread(self.screener.analyze, pcm, 16000))
            cancelled = False
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    cancelled = True
                except Exception:
                    if cancelled:
                        raise asyncio.CancelledError from None
                    raise
            if cancelled:
                # Retrieve a late worker error, preserving the caller cancellation.
                if not task.cancelled():
                    task.exception()
                raise asyncio.CancelledError
            return task.result()

    def status(self):
        return {"mode": self.mode, "model": self.screener.status(), "max_seconds": 30,
                "sample_rate": 16000, "provider_calls": 0, "persisted": False}


class ScreeningGate:
    """One bounded worker per microphone. Monitor never holds/blocks audio.

    Enforce is an opt-in experiment: hold each complete window and release only
    an allow verdict. Unknown/overload/incomplete windows remain withheld.
    """

    def __init__(self, runtime, on_audio, on_result, is_active):
        self.runtime, self.on_audio, self.on_result = runtime, on_audio, on_result
        self.is_active = is_active
        self.window_bytes = runtime.screener.window_samples * 2
        self.buffer = bytearray()
        self.queue = asyncio.Queue(maxsize=1)
        self.task = None
        self.closed = False

    async def feed(self, pcm: bytes):
        if self.closed or not self.is_active():
            self.buffer.clear()
            return
        if self.runtime.mode != "enforce":
            await self.on_audio(pcm)
        if self.runtime.mode == "off":
            return
        self.buffer.extend(pcm)
        while len(self.buffer) >= self.window_bytes:
            window = bytes(self.buffer[:self.window_bytes])
            del self.buffer[:self.window_bytes]
            if self.queue.full():
                # Never accumulate a backlog or release unassessed audio.
                await self._unknown("Screening overloaded; this window was not assessed", "overload")
                continue
            self.queue.put_nowait((window, time.perf_counter()))
            if self.task is None:
                self.task = asyncio.create_task(self._run())

    async def _unknown(self, reason, status):
        await self.on_result({
            "verdict": "unknown", "score": None, "reasons": [reason],
            "compute_ms": None, "audio_window_ms": self.runtime.screener.window_ms,
            "queue_ms": None, "hold_ms": None, "status": status,
            "action": "withheld" if self.runtime.mode == "enforce" else "observed",
            "mode": self.runtime.mode, "experimental": True,
            "created_at": datetime.now(UTC).isoformat(),
        })

    async def _run(self):
        while True:
            window, queued = await self.queue.get()
            try:
                result = await self.runtime.analyze(window)
                if self.closed or not self.is_active():
                    continue
                payload = result.as_dict()
                payload.update({
                    "mode": self.runtime.mode, "status": "assessed", "experimental": True,
                    "queue_ms": round(max(0, (time.perf_counter() - queued) * 1000 - result.compute_ms), 2),
                    "hold_ms": (round(self.runtime.screener.window_ms + (time.perf_counter() - queued) * 1000, 2)
                                if self.runtime.mode == "enforce" else 0),
                    "hold_boundary": "estimated_window_duration_plus_screening_elapsed",
                    "action": ("released" if result.verdict == "allow" else "withheld")
                              if self.runtime.mode == "enforce" else "observed",
                    "created_at": datetime.now(UTC).isoformat(),
                })
                await self.on_result(payload)
                if self.runtime.mode == "enforce" and result.verdict == "allow":
                    for offset in range(0, len(window), 640):
                        if self.closed or not self.is_active():
                            break
                        await self.on_audio(window[offset:offset + 640])
            except asyncio.CancelledError:
                raise
            except Exception:
                if not self.closed and self.is_active():
                    try:
                        await self._unknown("Local screening failed; no conclusion available", "error")
                    except Exception:
                        # A broken event consumer cannot kill the worker or
                        # release the unassessed window in enforcement mode.
                        pass
            finally:
                self.queue.task_done()

    async def close(self):
        self.closed = True
        self.buffer.clear()
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        while not self.queue.empty():
            self.queue.get_nowait()
            self.queue.task_done()
