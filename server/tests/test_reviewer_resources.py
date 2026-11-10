"""Private reviewer routing and model checks; no external provider traffic."""
from dataclasses import replace
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException
import httpx
import pytest
import pytest_asyncio
from pydantic import SecretStr

from charcha.accounts import Account, Accounts
from charcha.config import Settings
from charcha.errors import ProviderError
from charcha.providers.evon import EvonTranslator
from charcha.providers.gnani import GnaniSpeech
from charcha.reviewer_access import ReviewerInvitation
from charcha.services import host_budget
from charcha.services.bounded_http import BoundedResponseTransport, MODEL_LIST_BYTES, TRANSLATION_BYTES
from charcha.services.meeting_engine import MeetingEngineLifecycle
from charcha.services.reviewer_resources import (
    ResourceSelection, ReviewerEngine, ReviewerResources, RoutedSpeech,
    RoutedTranslator, RoutedUsage, validate_endpoint,
)
from charcha.services.usage import UsageGuard, provider_room
from charcha.store import Store


@pytest_asyncio.fixture
async def workspace(tmp_path):
    cfg = Settings(_env_file=None, mode="live", usage_db_path=tmp_path / "owner.sqlite3",
        usage_require_flow_approval=True, usage_require_room_scope=True,
        charcha_meeting_host_email="owner@example.com", charcha_auth_domain="id.example.com",
        gnani_api_key="owner-gnani", evon_api_key="owner-evon",
        evon_base_url="https://owner.modal.run/v1", evon_model="owner-model", evon_serverless=True)
    store = Store(cfg)
    accounts = Accounts(cfg, store)
    usage = UsageGuard(cfg, host_room_expiry=lambda c: store.rooms[c].expires_at
                       if c in store.rooms and store.rooms[c].host_funded else None)
    # Deliberately exhausted: private reviewers must not consume or replenish it.
    usage._operator_change(host_budget.activate, host_email="owner@example.com", limit_inr=0)
    speech, translator = GnaniSpeech(cfg, usage), EvonTranslator(cfg, usage)
    registry = ReviewerResources(cfg, store, accounts, usage, speech, translator)
    try:
        yield registry
    finally:
        await registry.aclose()
        await speech.aclose()
        await translator.aclose()
        usage.close()


def reviewer(registry, subject="judge", *, shared=True):
    admin = Account("admin", "admin", "admin@example.com", True, time.time() + 600)
    invitation = registry.accounts.reviewers.create(admin, ReviewerInvitation(share_resources=shared))
    who = Account(subject + "-session", subject, subject + "@example.com", False, time.time() + 600)
    registry.accounts.sessions[who.key] = who
    registry.accounts.reviewers.redeem(who, invitation["invitation"])
    return who, invitation


def own_profile(**updates):
    return ResourceSelection(gnani_source="own", evon_source="own", gnani_api_key="judge-gnani",
        evon_base_url="https://judge.modal.run/v1", evon_model="judge-model",
        evon_api_key="judge-evon", resource_consent=True).model_copy(update=updates)


async def room(registry, who, profile=None):
    registry.save(who, profile or own_profile())
    state = registry.store.create_room("Review", audio_mode="interpreted", host_funded=True)
    state.owner = who.subject
    await registry.bind(who, state)
    return state


@pytest.mark.parametrize("endpoint", [
    "http://judge.modal.run/v1", "https://localhost/v1", "https://127.0.0.1/v1",
    "https://169.254.169.254/v1", "https://[::1]/v1", "https://judge.modal.run:8443/v1",
    "https://judge.modal.run.evil.com/v1", "https://evil.com/v1", "https://a.b.modal.run/v1",
    "https://key@judge.modal.run/v1", "https://judge.modal.run/private",
    "https://judge.modal.run/v1?token=secret", "https://judge.modal.run/v1#secret",
    "https://judge.modal.run/%76%31", "https://judge.modal.run\\@evil.com/v1",
])
def test_endpoint_rejects_untrusted_destinations(endpoint):
    with pytest.raises(HTTPException) as error:
        validate_endpoint(endpoint, ["https://127.0.0.1", "https://169.254.169.254"])
    assert error.value.status_code == 422
    assert endpoint not in error.value.detail


def test_endpoint_requires_explicit_custom_origin_and_canonicalizes_modal():
    assert validate_endpoint("https://JUDGE.modal.run:443/", []) == "https://judge.modal.run/v1"
    assert validate_endpoint("https://gpu.example.com/v1/", ["https://gpu.example.com"]) == "https://gpu.example.com/v1"
    with pytest.raises(HTTPException):
        validate_endpoint("https://other.example.com/v1", ["https://gpu.example.com"])


@pytest.mark.asyncio
async def test_private_profile_never_returns_keys_and_endpoint_change_clears_old_keys(workspace):
    who, _ = reviewer(workspace)
    workspace.save(who, own_profile(evon_modal_key=SecretStr("private-proxy-key"),
                                   evon_modal_secret=SecretStr("private-proxy-secret")))
    public = json.dumps(workspace.snapshot(who))
    assert "judge-gnani" not in public and "judge-evon" not in public and "owner-" not in public
    assert "private-proxy" not in public
    same = ResourceSelection(gnani_source="own", evon_source="own",
        evon_base_url="https://judge.modal.run", evon_model="judge-model", resource_consent=True)
    workspace.save(who, same)
    assert workspace.profiles[who.key].evon_api_key.get_secret_value() == "judge-evon"
    assert workspace.profiles[who.key].evon_modal_secret.get_secret_value() == "private-proxy-secret"
    changed = same.model_copy(update={"evon_base_url":"https://new.modal.run"})
    workspace.save(who, changed)
    profile = workspace.profiles[who.key]
    assert profile.gnani_api_key.get_secret_value() == "judge-gnani"
    assert not profile.evon_api_key.get_secret_value()
    assert not profile.evon_modal_key.get_secret_value()
    assert not profile.evon_modal_secret.get_secret_value()


@pytest.mark.asyncio
async def test_profiles_bind_to_session_and_shared_requires_grant(workspace):
    who, _ = reviewer(workspace, shared=False)
    before = workspace.snapshot(who)
    assert before["profile"] is None
    assert not before["access"]["reviewer_shared_allowed"]
    assert before["access"]["expires_at"] > time.time()
    with pytest.raises(HTTPException) as error:
        workspace.save(who, ResourceSelection(resource_consent=True))
    assert error.value.status_code == 403
    workspace.save(who, own_profile())
    next_session = replace(who, key="new-session")
    workspace.accounts.sessions[next_session.key] = next_session
    assert workspace.snapshot(next_session)["configured"] is False
    ordinary = Account("guest", "guest", "guest@example.com", False, time.time() + 600)
    workspace.accounts.sessions[ordinary.key] = ordinary
    with pytest.raises(HTTPException):
        workspace.save(ordinary, own_profile())


@pytest.mark.asyncio
async def test_consent_secret_validation_and_proxy_pair_fail_before_binding(workspace):
    who, _ = reviewer(workspace)
    cases = [own_profile(resource_consent=False), own_profile(gnani_api_key=SecretStr("key\r\nHeader:x")),
             own_profile(evon_modal_key=SecretStr("proxy-key")), own_profile(evon_model="bad model")]
    for profile in cases:
        with pytest.raises(HTTPException):
            workspace.save(who, profile)
    assert not workspace.rooms and who.key not in workspace.profiles


@pytest.mark.asyncio
async def test_own_ledger_survives_exhausted_owner_and_cannot_spend_cross_room(workspace):
    who, _ = reviewer(workspace)
    state = await room(workspace, who)
    runtime = workspace.rooms[state.room.code]
    owner_before = workspace.shared_usage.snapshot()
    with provider_room(state.room.code):
        runtime.speech.usage.reserve({"stt_connections":1, "stt_seconds":3})
        runtime.translator.usage.reserve({"mt_requests":1, "mt_characters":8})
        runtime.speech.usage.reserve({"voice_enrollments":1})
    assert workspace.shared_usage.snapshot() == owner_before
    counts = {r["key"]:r["used"] for r in runtime.own_usage.snapshot()["resources"]}
    assert counts["stt_seconds"] == 3 and counts["mt_requests"] == 1 and counts["voice_enrollments"] == 1
    assert runtime.own_usage.host_policy()["managed"] is False
    assert runtime.own_usage.path != workspace.shared_usage.path
    other, _ = reviewer(workspace, "second")
    other_state = await room(workspace, other)
    with provider_room(other_state.room.code), pytest.raises(ProviderError):
        runtime.speech.usage.reserve({"stt_seconds":1})
    with provider_room(other_state.room.code), pytest.raises(ProviderError):
        runtime.own_usage.reserve({"stt_seconds":1})
    with pytest.raises(ProviderError):
        runtime.speech.usage.require_live()


@pytest.mark.asyncio
async def test_bind_checks_owner_and_snapshots_credentials_for_existing_rooms(workspace):
    who, _ = reviewer(workspace)
    workspace.save(who, own_profile())
    state = workspace.store.create_room("Other host", audio_mode="interpreted", host_funded=True)
    state.owner = "another"
    with pytest.raises(HTTPException) as error:
        await workspace.bind(who, state)
    assert error.value.status_code == 403
    state = await room(workspace, who)
    workspace.save(who, own_profile(evon_base_url="https://new.modal.run/v1"))
    r = workspace.rooms[state.room.code]
    assert r.settings.evon_base_url == "https://judge.modal.run/v1"
    assert r.speech.headers == {"X-API-Key-ID":"judge-gnani"}
    assert r.translator._headers()["Authorization"] == "Bearer judge-evon"
    assert workspace.shared_speech.headers == {"X-API-Key-ID":"owner-gnani"}
    assert isinstance(r.translator.client._transport, BoundedResponseTransport)
    assert r.translator.client._transport.max_bytes == TRANSLATION_BYTES
    assert isinstance(r.translator.engine.client._transport, BoundedResponseTransport)
    assert r.translator.engine.client._transport.max_bytes == MODEL_LIST_BYTES
    assert not r.translator.client.follow_redirects
    assert not isinstance(workspace.shared_translator.client._transport, BoundedResponseTransport)


@pytest.mark.asyncio
async def test_closed_room_never_falls_back_to_owner_and_other_room_keeps_working(workspace):
    who, _ = reviewer(workspace)
    a, b = await room(workspace, who), await room(workspace, who)
    captured = workspace.rooms[a.room.code].speech
    await workspace.close_room(a.room.code)
    assert a.room.code in workspace.store.rooms  # Simulates delayed cleanup elsewhere.
    for kind in ("speech", "translator"):
        with pytest.raises(ProviderError):
            workspace.selected(kind, a.room.code)
    with pytest.raises(ProviderError):
        workspace.engine_for(a.room.code)
    with provider_room(a.room.code), pytest.raises(ProviderError):
        captured.usage.reserve({"stt_seconds":1})
    assert workspace.selected("speech", b.room.code) is workspace.rooms[b.room.code].speech


@pytest.mark.asyncio
async def test_revoke_or_logout_closes_private_clients_and_profiles(workspace):
    who, invitation = reviewer(workspace)
    state = await room(workspace, who)
    runtime = workspace.rooms[state.room.code]
    admin = Account("admin", "admin", "admin@example.com", True, time.time() + 600)
    workspace.accounts.reviewers.revoke(admin, invitation["id"])
    assert workspace.snapshot(who)["configured"] is False
    with pytest.raises(ProviderError):
        workspace.engine_for(state.room.code)
    await workspace.revoke_subject(who.subject)
    assert who.key not in workspace.profiles and state.room.code not in workspace.rooms
    assert runtime.speech.client.is_closed and runtime.translator.client.is_closed and runtime.own_usage.closed
    other, _ = reviewer(workspace, "other")
    state = await room(workspace, other)
    service = SimpleNamespace(reviewer_resources=workspace, prune_expired=AsyncMock())
    await workspace.accounts.revoke(other, service)
    assert other.key not in workspace.profiles and state.room.code not in workspace.rooms
    service.prune_expired.assert_awaited_once()


@pytest.mark.asyncio
async def test_routed_adapters_choose_only_server_context_and_retain_payloads(workspace):
    who, _ = reviewer(workspace)
    a = await room(workspace, who)
    other, _ = reviewer(workspace, "other")
    b = await room(workspace, other)
    ra, rb = workspace.rooms[a.room.code], workspace.rooms[b.room.code]
    ra.speech.synthesize, rb.speech.synthesize = AsyncMock(return_value="audio-a"), AsyncMock(return_value="audio-b")
    ra.translator.translate, rb.translator.translate = AsyncMock(return_value="text-a"), AsyncMock(return_value="text-b")
    speech = RoutedSpeech(workspace, RoutedUsage(workspace))
    translation = RoutedTranslator(workspace)
    with provider_room(a.room.code):
        assert await speech.synthesize("text", "te") == "audio-a"
        assert await translation.translate("text", "hi", "te") == "text-a"
        assert translation.engine is ra.translator.engine
    with provider_room(b.room.code):
        assert await speech.synthesize("text", "pa") == "audio-b"
        assert await translation.translate("text", "hi", "pa") == "text-b"
    assert ra.speech.synthesize.await_count == rb.speech.synthesize.await_count == 1


@pytest.mark.asyncio
async def test_expired_reviewer_cannot_prepare_or_keep_gpu_alive(workspace):
    who, invitation = reviewer(workspace)
    state = await room(workspace, who)
    engine = workspace.rooms[state.room.code].translator.engine
    engine.ensure_ready = AsyncMock()
    lifecycle = MeetingEngineLifecycle(workspace.store, SimpleNamespace(rooms={}), None,
        resolve_engine=workspace.engine_for, is_authorized=lambda s: workspace.valid(s.room.code))
    with workspace.accounts.reviewers.connection() as db:
        db.execute("UPDATE reviewer_invitations SET expires_at=? WHERE id=?",
                   (time.time()-1, invitation["id"]))
    with pytest.raises(ProviderError):
        lifecycle.prepare(state.room.code, account_deadline=who.expires)
    lifecycle.sync()
    assert not engine.meeting_rooms and engine.meeting_task is None
    engine.ensure_ready.assert_not_awaited()
    assert not workspace.snapshot(who)["configured"]


@pytest.mark.asyncio
@pytest.mark.parametrize("redirect", ["https://evil.com/v1/models", "http://judge.modal.run/v1/models", "/other"])
async def test_model_probe_rejects_redirects_without_forwarding_auth(redirect):
    engine = ReviewerEngine(Settings(_env_file=None, evon_serverless=True,
        evon_base_url="https://judge.modal.run/v1", evon_model="wanted"), lambda:{"Authorization":"Bearer private-key"})
    await engine.client.aclose()
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(303, headers={"Location":redirect})
    engine.client = httpx.AsyncClient(transport=httpx.MockTransport(respond), follow_redirects=False)
    try:
        with pytest.raises(ProviderError) as error:
            await engine._start()
        assert len(calls) == 1 and calls[0].url.host == "judge.modal.run"
        assert "private-key" not in str(error.value)
    finally:
        await engine.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("model,works", [("wanted",True), ("different",False)])
async def test_model_probe_requires_exact_served_model_without_translation_tokens(model, works):
    engine = ReviewerEngine(Settings(_env_file=None, evon_serverless=True,
        evon_base_url="https://judge.modal.run/v1", evon_model="wanted"), lambda:{})
    await engine.client.aclose()
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"data":[{"id":model}]})
    engine.client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    try:
        if works:
            await engine._start()
            assert engine.status()["state"] == "ready"
        else:
            with pytest.raises(ProviderError):
                await engine._start()
        assert len(calls) == 1 and calls[0].method == "GET" and calls[0].url.path == "/v1/models"
    finally:
        await engine.aclose()
