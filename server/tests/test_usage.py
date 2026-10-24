"""Credit controls use local protocol fixtures only; no billable calls run here."""
import asyncio
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from artha_mesh.config import Settings
from artha_mesh.errors import ProviderError
from artha_mesh.main import create_app
from artha_mesh.models import Participant
from artha_mesh.providers.evon import EvonTranslator
from artha_mesh.providers.gnani import GnaniSpeech
from artha_mesh.services.pipeline import Pipeline
from artha_mesh.services.usage import UsageGuard
from artha_mesh.store import Store, token_digest


def live_settings(**values):
    return Settings(mode="live", evon_base_url="https://fixture.invalid/v1", evon_model="fixture",
                    _env_file=None, **values)


def resource(usage, key):
    return next(row for row in usage.snapshot()["resources"] if row["key"] == key)


def test_reservations_are_atomic_restart_safe_and_reset_only_at_utc_midnight(tmp_path):
    current = [datetime(2026, 10, 23, 23, 59, 59, tzinfo=UTC)]
    settings = live_settings(usage_mt_requests_per_day=2, usage_mt_characters_per_day=5)
    first = UsageGuard(settings, now=lambda: current[0])
    first.reserve({"mt_requests": 1, "mt_characters": 3})
    with pytest.raises(ProviderError):
        first.reserve({"mt_requests": 1, "mt_characters": 3})
    assert resource(first, "mt_requests")["used"] == 1  # Both counters roll back together.
    second = UsageGuard(settings, now=lambda: current[0])
    assert resource(second, "mt_characters")["used"] == 3
    first.close()
    current[0] += timedelta(seconds=1)
    second.reserve({"mt_requests": 1, "mt_characters": 5})
    assert resource(second, "mt_characters")["used"] == 5
    assert second.snapshot()["period"] == {"date": "2026-10-24", "reset_at": "2026-10-25T00:00:00+00:00"}
    with sqlite3.connect(settings.usage_db_path) as connection:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(usage)")]
        assert columns == ["period", "resource", "units"]
        assert connection.execute("SELECT COUNT(DISTINCT period) FROM usage").fetchone()[0] == 2


def test_concurrent_reservations_cannot_overspend_shared_sqlite_ledger():
    settings = live_settings(usage_mt_requests_per_day=7)
    guards = [UsageGuard(settings), UsageGuard(settings)]
    guards[0].reserve({"mt_requests": 0})
    guards[1].reserve({"mt_requests": 0})

    def attempt(index):
        try:
            guards[index % 2].reserve({"mt_requests": 1})
            return True
        except ProviderError as exc:
            assert not exc.retryable
            return False

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert sum(executor.map(attempt, range(30))) == 7
    row = resource(guards[0], "mt_requests")
    assert row["used"] == 7
    assert row["remaining"] == 0
    assert row["status"] == "exhausted"


def test_zero_limit_blocks_feature_and_warning_does_not_claim_provider_balance():
    usage = UsageGuard(live_settings(usage_tts_requests_per_day=0, usage_mt_requests_per_day=5))
    with pytest.raises(ProviderError, match="Daily credit safeguard"):
        usage.reserve({"tts_requests": 1})
    usage.reserve({"mt_requests": 4})
    assert resource(usage, "mt_requests")["status"] == "warning"
    assert resource(usage, "tts_requests")["status"] == "exhausted"
    assert usage.snapshot()["billing"]["balance_available"] is False


@pytest.mark.parametrize("kind", ["unwritable", "corrupt", "ephemeral"])
async def test_storage_failure_blocks_before_translation_network_call(tmp_path, kind):
    path = tmp_path / "ledger.sqlite3"
    if kind == "unwritable":
        path.mkdir()  # A directory cannot become the ledger file on any OS.
    elif kind == "corrupt":
        path.write_bytes(b"not a database")
    else:
        path = ":memory:"
    settings = live_settings(usage_db_path=path)
    usage = UsageGuard(settings)
    translator = EvonTranslator(settings, usage)
    await translator.client.aclose()
    calls = []
    translator.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: calls.append(request)))
    try:
        with pytest.raises(ProviderError) as error:
            await translator.translate("hello", "hi", "ta")
        assert not error.value.retryable
        assert calls == []
        snapshot = usage.snapshot()
        assert snapshot["enforcement"]["status"] == "unavailable"
        assert all(row["used"] is None and row["status"] == "unknown" for row in snapshot["resources"])
        assert str(path) not in json.dumps(snapshot)
    finally:
        await translator.aclose()


async def test_demo_adapters_cannot_call_external_providers_or_create_ledger(monkeypatch, tmp_path):
    settings = Settings(mode="demo", _env_file=None)
    usage = UsageGuard(settings)
    translator, speech = EvonTranslator(settings, usage), GnaniSpeech(settings, usage)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Demo attempted a paid network call")

    monkeypatch.setattr("artha_mesh.providers.gnani.websockets.connect", forbidden)

    async def no_audio():
        yield b"\x00" * 1024

    try:
        with pytest.raises(ProviderError, match="disabled in demo"):
            await translator.translate("text", "hi", "ta")
        with pytest.raises(ProviderError, match="disabled in demo"):
            await speech.enroll(b"reference")
        with pytest.raises(ProviderError, match="disabled in demo"):
            _ = [chunk async for chunk in speech.synthesize("text", "hi")]
        with pytest.raises(ProviderError, match="disabled in demo"):
            _ = [part async for part in speech.transcribe(no_audio(), "hi")]
        assert usage.snapshot()["enforcement"]["status"] == "demo"
        assert all(row["used"] == 0 for row in usage.snapshot()["resources"])
        assert not settings.usage_db_path.exists()
    finally:
        await translator.aclose()
        await speech.aclose()


@pytest.mark.parametrize("status", [401, 403, 429, 500])
async def test_failed_translation_keeps_reservation_without_silent_retry(status):
    settings = live_settings(usage_mt_requests_per_day=1)
    usage = UsageGuard(settings)
    translator = EvonTranslator(settings, usage)
    await translator.client.aclose()
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"private": "must not leak"})

    translator.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ProviderError) as error:
            await translator.translate("hello", "hi", "ta")
        assert error.value.retryable is (status == 500)
        assert "must not leak" not in str(error.value)
        assert len(calls) == 1
        assert resource(usage, "mt_requests")["used"] == 1
        assert resource(usage, "mt_characters")["used"] == 5
        with pytest.raises(ProviderError, match="Daily credit safeguard"):
            await translator.translate("hello", "hi", "ta")
        assert len(calls) == 1
        assert await translator.translate("hello", "hi", "hi") == "hello"
    finally:
        await translator.aclose()


async def test_shared_operation_concurrency_rejects_waiter_before_reserving():
    usage = UsageGuard(live_settings(usage_max_concurrent_operations=1,
                                   usage_provider_admission_timeout_seconds=0.02))
    async with usage.operation({"mt_requests": 1}):
        with pytest.raises(ProviderError, match="concurrency safeguard"):
            async with usage.operation({"voice_enrollments": 1}):
                raise AssertionError("Unexpected admission")
    assert resource(usage, "mt_requests")["used"] == 1
    assert resource(usage, "voice_enrollments")["used"] == 0
    async with usage.operation({"voice_enrollments": 1}):
        pass
    assert resource(usage, "voice_enrollments")["used"] == 1


async def test_tts_and_enrollment_caps_guard_the_adapters_before_network(monkeypatch):
    settings = live_settings(usage_tts_characters_per_day=3, usage_voice_enrollments_per_day=0)
    speech = GnaniSpeech(settings)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Network must not be contacted after cap")

    monkeypatch.setattr("artha_mesh.providers.gnani.websockets.connect", forbidden)
    try:
        with pytest.raises(ProviderError, match="Daily credit safeguard"):
            _ = [chunk async for chunk in speech.synthesize("four", "hi")]
        with pytest.raises(ProviderError, match="Daily credit safeguard"):
            await speech.enroll(b"reference")
        assert resource(speech.usage, "tts_requests")["used"] == 0
        assert resource(speech.usage, "voice_enrollments")["used"] == 0
    finally:
        await speech.aclose()


class IdleSocket:
    def __init__(self):
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        self.closed = True

    async def recv(self):
        return '{"type":"connected"}'

    async def send(self, _data):
        pass

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.Event().wait()


async def test_idle_stt_connection_stops_at_budget_and_is_not_retryable(monkeypatch):
    settings = live_settings(usage_stt_seconds_per_day=1)
    speech = GnaniSpeech(settings)
    socket = IdleSocket()
    monkeypatch.setattr("artha_mesh.providers.gnani.websockets.connect", lambda *_args, **_kwargs: socket)

    async def audio():
        yield b"\x00" * 1024
        await asyncio.Event().wait()

    try:
        with pytest.raises(ProviderError, match="Daily credit safeguard") as error:
            async with asyncio.timeout(2):
                _ = [part async for part in speech.transcribe(audio(), "hi")]
        assert not error.value.retryable
        assert socket.closed
        assert resource(speech.usage, "stt_seconds")["used"] == 1
        assert resource(speech.usage, "stt_connections")["used"] == 1
    finally:
        await speech.aclose()


@pytest.mark.parametrize("body", [
    {"type": "error", "code": 401, "message": "Authentication failed"},
    {"type": "error", "code": "429", "message": "Try later"},
    {"type": "error", "message": "Authentication failed"},
    {"type": "error", "message": "Insufficient balance"},
])
async def test_stt_websocket_auth_and_credit_denials_do_not_request_retry(monkeypatch, body):
    class DeniedSocket(IdleSocket):
        async def recv(self):
            return json.dumps(body)

    socket = DeniedSocket()
    speech = GnaniSpeech(live_settings())
    calls = []

    def connect(*_args, **_kwargs):
        calls.append(True)
        return socket

    monkeypatch.setattr("artha_mesh.providers.gnani.websockets.connect", connect)

    async def audio():
        yield b"\x00" * 1024

    try:
        with pytest.raises(ProviderError) as error:
            _ = [part async for part in speech.transcribe(audio(), "hi")]
        assert error.value.retryable is False
        assert calls == [True]
        assert socket.closed
        assert resource(speech.usage, "stt_connections")["used"] == 1
    finally:
        await speech.aclose()


@pytest.mark.parametrize("kind", ["mt", "tts"])
@pytest.mark.parametrize("change", ["source_expired", "last_listener_left"])
async def test_pipeline_rechecks_delivery_after_provider_admission_before_reservation(monkeypatch, kind, change):
    import time

    settings = live_settings(usage_max_concurrent_operations=1)
    store, usage = Store(settings), UsageGuard(settings)
    state = store.create_room("Queued paid request eligibility")
    source = Participant(id="source", name="Source", language="hi")
    listener = Participant(id="listener", name="Listener", language="ta" if kind == "mt" else "hi")
    state.room.participants.extend((source, listener))
    source_token = store.issue_session(state, source.id)
    store.issue_session(state, listener.id)
    translator, speech = EvonTranslator(settings, usage), GnaniSpeech(settings, usage)
    await translator.client.aclose()
    paid_calls = []

    def translate_request(request):
        paid_calls.append("mt")
        return httpx.Response(200, json={"choices": [{"message": {"content": "fixture"}}]})

    def synthesize_request(*_args, **_kwargs):
        paid_calls.append("tts")
        raise AssertionError("Stale queued synthesis must not reach upstream")

    translator.client = httpx.AsyncClient(transport=httpx.MockTransport(translate_request))
    monkeypatch.setattr("artha_mesh.providers.gnani.websockets.connect", synthesize_request)

    class Transport:
        async def speak(self, _code, _source, _target, chunks, callback):
            async for _chunk in chunks:
                callback()

    pipeline = Pipeline(store, translator, speech)
    pipeline.transport = Transport()
    try:
        async with usage.operation({"voice_enrollments": 1}):
            await pipeline.submit(state, source, "queued sentence")
            async with asyncio.timeout(1):
                while not usage.waiters:
                    await asyncio.sleep(0.01)
            if change == "source_expired":
                store.sessions[token_digest(source_token)].expires_at = time.time() - 1
            else:
                state.room.participants.remove(listener)
        await asyncio.wait_for(pipeline.queues[(state.room.code, source.id)].join(), 1)
        assert state.turns[0].status == "error"
        assert paid_calls == []
        assert resource(usage, "mt_requests")["used"] == 0
        assert resource(usage, "tts_requests")["used"] == 0
        assert usage.waiters == 0
    finally:
        await pipeline.aclose()
        await translator.aclose()
        await speech.aclose()


def test_usage_endpoint_is_redacted_and_reading_does_not_consume_credits(client):
    for _ in range(3):
        response = client.get("/api/usage")
        assert response.status_code == 200
        body = response.json()
        assert body["mode"] == "demo"
        assert body["enforcement"]["enabled"] is True
        assert body["enforcement"]["persistent"] is False
        assert all(row["used"] == 0 for row in body["resources"])
        assert "sqlite" not in response.text
        assert "session_token" not in response.text
        assert "api_key" not in response.text
    assert not client.app.state.settings.usage_db_path.exists()


def test_live_usage_endpoint_reads_existing_reservations_without_provider_probes():
    settings = live_settings(gnani_api_key="private-key", livekit_url="wss://private.invalid")
    app = create_app(settings)
    app.state.usage.reserve({"mt_requests": 1, "mt_characters": 7})
    with TestClient(app) as client:
        response = client.get("/api/usage")
        snapshot = response.json()
        assert snapshot["enforcement"]["persistent"] is True
        assert snapshot["enforcement"]["status"] == "ready"
        assert next(row for row in snapshot["resources"] if row["key"] == "mt_requests")["used"] == 1
        assert "private-key" not in response.text
        assert "private.invalid" not in response.text
        assert "fixture" not in response.text
