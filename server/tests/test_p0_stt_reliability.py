"""P0: mute grace, idle header, documented language header, retry counting, grant cap."""
import asyncio
import sqlite3
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from charcha.config import Settings
from charcha.services import approvals
from tests.test_credit_transport import transport_fixture, until


class Pipeline:
    def __init__(self):
        self.submitted = []

    async def submit(self, _state, speaker, text, *_args, **_kwargs):
        self.submitted.append((speaker.id, text))

    async def cancel_speaker(self, *_args):
        raise AssertionError("mute grace must not cancel spoken phrases")


async def test_mute_grace_feeds_silence_and_delivers_last_phrase(monkeypatch):
    class Speech:
        opened = closed = 0
        silence_bytes = 0

        async def transcribe(self, audio, *_args):
            self.opened += 1
            try:
                async for chunk in audio:
                    if not any(chunk):
                        self.silence_bytes += len(chunk)
                        if self.silence_bytes >= 640 * 30:  # ~600 ms of VAD silence
                            yield SimpleNamespace(text="last phrase", stt_ms=5)
                            self.silence_bytes = -10**9
            finally:
                self.closed += 1

    speech = Speech()
    _, state, speaker, _, consumer, transport = transport_fixture(monkeypatch, speech, stt_mute_grace_seconds=2.5)
    transport.pipeline = Pipeline()
    speaker.muted = False
    task = asyncio.create_task(transport._read_audio(object(), speaker.id))
    try:
        await until(lambda: speech.opened == 1)
        speaker.muted = True
        await until(lambda: transport.pipeline.submitted, 3)
        assert transport.pipeline.submitted == [("source", "last phrase")]
        await until(lambda: speech.closed == 1, 3)  # Ends early after the final.
        await asyncio.sleep(0.4)
        assert speech.opened == 1
        events = []
        while not consumer.queue.empty():
            events.append(str(consumer.queue.get_nowait()))
        stages = [e for e in events if "pipeline.status" in e]
        assert any("finishing" in e for e in stages) and "idle" in stages[-1]
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_mute_grace_closes_after_deadline_and_unmute_keeps_socket(monkeypatch):
    class Speech:
        opened = closed = 0

        async def transcribe(self, audio, *_args):
            self.opened += 1
            try:
                async for _ in audio:
                    pass
                yield None
            finally:
                self.closed += 1

    speech = Speech()
    _, _, speaker, _, _, transport = transport_fixture(monkeypatch, speech, stt_mute_grace_seconds=0.6)
    speaker.muted = False
    task = asyncio.create_task(transport._read_audio(object(), speaker.id))
    try:
        await until(lambda: speech.opened == 1)
        speaker.muted = True
        await asyncio.sleep(0.2)
        speaker.muted = False  # Unmute inside grace: same connection continues.
        await asyncio.sleep(0.8)
        assert (speech.opened, speech.closed) == (1, 0)
        speaker.muted = True
        await until(lambda: speech.closed == 1, 2)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_healthy_normal_close_reconnects_without_spending_retries(monkeypatch):
    class Speech:
        opened = 0

        async def transcribe(self, *_args):
            self.opened += 1
            if False:
                yield None  # Normal provider close (idle timeout / session cap).

    speech = Speech()
    _, state, speaker, _, consumer, transport = transport_fixture(
        monkeypatch, speech, stt_healthy_seconds=0, usage_stt_max_retries=0)
    speaker.muted = False
    task = asyncio.create_task(transport._read_audio(object(), speaker.id))
    try:
        await until(lambda: speech.opened >= 5)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    events = []
    while not consumer.queue.empty():
        events.append(consumer.queue.get_nowait())
    assert not any("pipeline.error" in str(event) for event in events)


async def test_quick_normal_close_still_counts_toward_retry_limit(monkeypatch):
    class Speech:
        opened = 0

        async def transcribe(self, *_args):
            self.opened += 1
            if False:
                yield None

    speech = Speech()
    _, _, speaker, _, _, transport = transport_fixture(
        monkeypatch, speech, stt_healthy_seconds=60, usage_stt_max_retries=0)
    speaker.muted = False
    task = asyncio.create_task(transport._read_audio(object(), speaker.id))
    try:
        await until(lambda: speech.opened == 1)
        await asyncio.sleep(0.5)
        assert speech.opened == 1  # Terminal after the single allowed attempt.
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_gnani_sends_documented_language_and_idle_headers(monkeypatch):
    from charcha.providers import gnani

    seen = {}

    class Closed(Exception):
        pass

    def fake_connect(_url, additional_headers=None, **_kwargs):
        seen.update(additional_headers or {})
        raise Closed()

    monkeypatch.setattr(gnani.websockets, "connect", fake_connect, raising=False)

    from contextlib import asynccontextmanager

    class Usage:
        def reserve(self, *_a, **_k):
            return None

        @asynccontextmanager
        async def operation(self, *_a, **_k):
            yield

    settings = Settings(mode="live", _env_file=None, gnani_api_key="k", gnani_stt_idle_timeout_sec=900)
    client = gnani.GnaniSpeech(settings, Usage())

    async def audio():
        yield b"\x00" * 1024

    with pytest.raises(Exception):
        async for _ in client.transcribe(audio(), "hi", lambda: None):
            pass
    assert seen["language_code"] == seen["lang_code"] == "hi-IN"
    assert seen["x-idle-timeout-sec"] == "900"


def test_approval_cap_is_configurable():
    connection = sqlite3.connect(":memory:")
    approvals.create_schema(connection)
    now = datetime(2026, 11, 3, tzinfo=timezone.utc)
    budgets = {key: 1 for key in approvals.RESOURCE_KEYS} if hasattr(approvals, "RESOURCE_KEYS") else None
    if budgets is None:
        pytest.skip("budget keys unavailable")
    with pytest.raises(ValueError, match="1 to 300"):
        approvals.approve(connection, now, purpose=sorted(approvals.PURPOSES)[0], seconds=900, budgets=budgets)
    result = approvals.approve(connection, now, purpose=sorted(approvals.PURPOSES)[0], seconds=900,
                               budgets=budgets, max_seconds=1800)
    assert result
    assert Settings(_env_file=None).usage_approval_max_seconds == 300
    assert Settings(_env_file=None, usage_approval_max_seconds=1800).usage_approval_max_seconds == 1800
