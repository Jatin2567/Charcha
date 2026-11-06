"""Offline lifecycle tests. All providers and model health calls are doubles."""
import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException

from charcha.config import Settings
from charcha.errors import ProviderError
from charcha.models import Participant, UpdateParticipant
from charcha.services.engine import InterpretationEngine
from charcha.services.host_budget import activate, BudgetChange
from charcha.services.pipeline import Pipeline
from charcha.services.readiness import conference_readiness
from charcha.services.rooms import RoomService
from charcha.services.usage import UsageGuard, provider_room, _room
from charcha.services.voice import VoiceService
from charcha.store import Store
from conftest import make_wav


@pytest.mark.asyncio
async def test_startup_single_flight_status_reads_do_not_wake_and_readiness_expires():
    engine = InterpretationEngine(Settings(_env_file=None, evon_serverless=True,
        evon_base_url="https://test.modal.run/v1"), lambda: {"Authorization": "Bearer test"})
    calls, release = [], asyncio.Event()
    async def respond(request):
        calls.append(request)
        await release.wait()
        return httpx.Response(200)
    await engine.client.aclose()
    engine.client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    assert engine.status()["state"] == "idle" and not calls
    engine.begin()
    first = engine.task
    engine.begin()
    assert engine.task is first
    assert engine.status()["state"] == "starting"
    release.set()
    await engine.ensure_ready()
    assert len(calls) == 1
    assert engine.status()["startup_ms"] >= 0
    engine.ready_until = time.monotonic() - 1
    assert engine.status()["state"] == "idle" and len(calls) == 1
    await engine.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("destination", ["https://other.modal.run/health", "https://test.modal.run/leak", "http://test.modal.run/health"])
async def test_startup_rejects_credential_redirect_and_status_does_not_retry(destination):
    engine = InterpretationEngine(Settings(_env_file=None, evon_serverless=True,
        evon_base_url="https://test.modal.run/v1"), lambda: {"Modal-Secret": "private"})
    calls = []
    def redirect(request):
        calls.append(request)
        return httpx.Response(303, headers={"location": destination})
    await engine.client.aclose()
    engine.client = httpx.AsyncClient(transport=httpx.MockTransport(redirect))
    with pytest.raises(ProviderError):
        await engine.ensure_ready()
    assert engine.status()["state"] == "unavailable"
    assert len(calls) == 1
    await engine.aclose()


def test_owner_monitors_billing_but_room_authority_and_service_counts_remain(tmp_path):
    settings = Settings(_env_file=None, mode="live", usage_require_flow_approval=True,
        usage_require_room_scope=True, usage_db_path=tmp_path/"usage.db", usage_stt_seconds_per_day=1)
    usage = UsageGuard(settings, host_room_expiry=lambda code: time.time()+300 if code == "abcd12344321" else None)
    usage._operator_change(activate, host_email="host@example.test", limit_inr=0)
    usage.change_host_budget(BudgetChange(limit_inr=0, revision=1, managed=False))
    assert usage.conference_capacity(9, room_code="abcd12344321")["status"] == "approved"
    with provider_room("abcd12344321"):
        usage.reserve({"voice_enrollments":1, "stt_seconds":1000, "tts_characters":5000})
    assert usage.host_policy()["reserved_inr"] == 0
    report = usage.public_snapshot()
    assert report["approval"]["owner_tracks_billing"]
    assert next(r for r in report["resources"] if r["key"] == "stt_seconds")["used"] == 1000
    with provider_room("abcd12340000"), pytest.raises(ProviderError):
        usage.reserve({"stt_seconds":1})
    usage.change_host_budget(BudgetChange(limit_inr=0, revision=2, managed=True))
    with provider_room("abcd12344321"), pytest.raises(ProviderError):
        usage.reserve({"stt_seconds":1})
    usage.close()


@pytest.mark.asyncio
async def test_required_voice_enrollment_deduplicates_and_deletion_mutes():
    settings = Settings(_env_file=None, mode="live", voice_cloning_required=True)
    store = Store(settings)
    state = store.create_room("Voice meeting", host_funded=True)
    speaker, listener = Participant(name="Speaker", language="hi"), Participant(name="Listener", language="ta")
    state.room.participants = [speaker, listener]
    token = store.issue_session(state, speaker.id)
    store.issue_session(state, listener.id)
    release, entered = asyncio.Event(), asyncio.Event()
    calls = []
    async def enroll(clip):
        calls.append(_room.get())
        entered.set()
        await release.wait()
        return {"embedding":"fake", "shape":[1,768], "dtype":"torch.bfloat16"}
    speech = SimpleNamespace(enroll=enroll)
    voices = VoiceService(store, speech)
    first = asyncio.create_task(voices.enroll(make_wav(), "audio/wav", "My voice", True, token))
    await entered.wait()
    second = asyncio.create_task(voices.enroll(make_wav(), "audio/wav", "My voice", True, token))
    await asyncio.sleep(0)
    release.set()
    a, b = await asyncio.gather(first, second)
    assert a.id == b.id and calls == [state.room.code]
    assert speaker.voice_mode == "cloned" and len(store.voices) == 1
    assert (await voices.enroll(b"", "audio/wav", "My voice", True, token)).id == a.id
    pipeline = Pipeline(store, SimpleNamespace(), speech)
    transport = SimpleNamespace(reconfigure=AsyncMock())
    service = RoomService(store, pipeline, transport, voices)
    with pytest.raises(HTTPException):
        await service.update(state.room.code, UpdateParticipant(voice_mode="standard"), token)
    speaker.muted = False
    await service.delete_voice(a.id, token)
    assert speaker.muted and not store.voices
    with pytest.raises(ProviderError, match="voice setup"):
        pipeline._require_delivery_active(state, speaker.id, "ta")
    await voices.aclose()
