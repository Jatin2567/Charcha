"""HTTP integration for reviewer-owned meetings. Network is locally mocked."""
import secrets
import time
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from charcha.accounts import Account, COOKIE
from charcha.config import Settings
from charcha.main import create_app
from charcha.models import Participant
from charcha.services.readiness import conference_readiness
from charcha.services.usage import provider_room
from charcha.store import token_digest


@pytest.fixture
def site(tmp_path, monkeypatch):
    # Fail any accidental outbound HTTP in this integration suite. Evon readiness
    # is explicitly replaced below when exercising the authorized preparation POST.
    async def no_network(*a, **kw):
        raise AssertionError("Unexpected external request")
    monkeypatch.setattr(httpx.AsyncClient, "send", no_network)
    app = create_app(Settings(_env_file=None, mode="live", evon_serverless=True,
        gnani_api_key="", evon_base_url="", evon_model="", usage_require_flow_approval=True,
        usage_require_room_scope=True, livekit_url="wss://rtc.example.test",
        livekit_api_key="fixture", livekit_api_secret="fixture",
        usage_db_path=tmp_path/"usage.sqlite3", charcha_public_origin="https://meet.example.test",
        charcha_meeting_host_email="host@example.test"))
    with TestClient(app, base_url="https://meet.example.test", headers={"X-Charcha-Request":"1"}) as client:
        yield app, client


def sign_in(site, subject, *, admin=False):
    app, client = site
    cookie = secrets.token_hex(16)
    who = Account(token_digest(cookie), subject, subject+"@example.test", admin, time.time()+1800)
    app.state.accounts.sessions[who.key] = who
    client.cookies.set(COOKIE, cookie)
    return who, cookie


def reviewer(site, *, shared=False):
    _, client = site
    sign_in(site, "administrator", admin=True)
    invitation = client.post("/api/admin/reviewer-invitations", json={"share_resources":shared}).json()
    who, cookie = sign_in(site, "judge")
    assert client.post("/api/reviewer/access/redeem", json={"invitation":invitation["invitation"]}).is_success
    return who, cookie, invitation["id"]


def own_resources(client):
    response = client.post("/api/reviewer/workspace", json={
        "gnani_source":"own", "evon_source":"own", "gnani_api_key":"reviewer-private-key",
        "evon_base_url":"https://judge--evon.modal.run/v1", "evon_model":"evon-review",
        "evon_api_key":"reviewer-model-key", "resource_consent":True})
    assert response.is_success, response.text
    assert response.json()["configured"]
    assert "private-key" not in response.text and "model-key" not in response.text


def make_room(client):
    response = client.post("/api/rooms", json={"title":"Private reviewer meeting",
        "audio_mode":"interpreted", "resource_mode":"reviewer"})
    assert response.status_code == 201, response.text
    return response.json()["code"]


def test_byo_meeting_works_with_unavailable_owner_ledger(site, monkeypatch):
    app, client = site
    reviewer(site)
    own_resources(client)
    def unavailable():
        raise AssertionError("A fully personal meeting must not consult the owner ledger")
    monkeypatch.setattr(app.state.usage, "host_policy", unavailable)
    code = make_room(client)
    resources = app.state.reviewer_resources
    assert app.state.service.usage.conference_capacity(2, room_code=code)["status"] == "approved"
    with provider_room(code):
        assert resources.selected("speech").headers["X-API-Key-ID"] == "reviewer-private-key"
        resources.selected("speech").usage.reserve({"stt_seconds":1})
        resources.selected("translator").usage.reserve({"mt_requests":1})
    assert client.get(f"/api/rooms/{code}/preparation").json()["state"] == "idle"
    assert app.state.meeting_engine.preparations == {}
    assert client.get("/api/admin").status_code == 403


def test_preparation_explicit_owner_only_and_bounded(site, monkeypatch):
    app, client = site
    who, cookie, _ = reviewer(site)
    own_resources(client)
    code = make_room(client)
    engine = app.state.reviewer_resources.engine_for(code)
    probes = []
    async def models(url, **kwargs):
        probes.append((url, kwargs["headers"]))
        return httpx.Response(200, json={"data":[{"id":"evon-review"}]})
    monkeypatch.setattr(engine.client, "get", models)
    for _ in range(3):
        assert client.get(f"/api/rooms/{code}/preparation").json()["can_prepare"]
    assert not probes
    sign_in(site,"stranger")
    assert client.post(f"/api/rooms/{code}/preparation").status_code == 403
    assert client.get(f"/api/rooms/{code}/preparation").status_code == 403
    assert not probes
    client.cookies.set(COOKIE,cookie)
    first=client.post(f"/api/rooms/{code}/preparation")
    assert first.is_success, first.text
    assert first.json()["preparation_active"]
    for _ in range(20):
        status=client.get(f"/api/rooms/{code}/preparation").json()
        if status["state"] == "ready":
            break
        time.sleep(.01)
    assert status["state"] == "ready" and status["observed_at"] and status["startup_ms"] is not None
    second=client.post(f"/api/rooms/{code}/preparation").json()
    assert second["preparation_expires_at"] == first.json()["preparation_expires_at"]
    assert len(probes) == 1 and probes[0][1]["Authorization"] == "Bearer reviewer-model-key"
    assert client.delete(f"/api/rooms/{code}/preparation").json()["preparation_active"] is False
    assert engine.meeting_rooms == set()


@pytest.mark.parametrize("action", ["delete", "logout", "revoke"])
def test_resource_revocation_ends_room_and_clears_profile(site, action):
    app, client = site
    who, _, invitation_id = reviewer(site)
    own_resources(client)
    code = make_room(client)
    if action == "delete":
        response = client.delete("/api/reviewer/workspace")
    elif action == "logout":
        response = client.post("/api/account/logout")
    else:
        sign_in(site,"administrator",admin=True)
        response = client.delete("/api/admin/reviewers/"+invitation_id)
    assert response.is_success, response.text
    assert code not in app.state.reviewer_resources.rooms
    assert code not in app.state.store.rooms
    assert who.key not in app.state.reviewer_resources.profiles


def test_automatic_domain_grant_revocation_ends_room_and_clears_profile(site):
    app,client=site
    who,_=sign_in(site,"gnani-reviewer")
    who=replace(who,email="reviewer@gnani.ai")
    app.state.accounts.sessions[who.key]=who
    access=client.get('/api/reviewer/access').json()
    assert access['access_source']=='domain'
    own_resources(client)
    code=make_room(client)
    sign_in(site,'administrator',admin=True)
    result=client.post(f"/api/admin/reviewer-requests/{access['request']['id']}/decision",json={'decision':'revoke'})
    assert result.is_success,result.text
    assert code not in app.state.reviewer_resources.rooms
    assert code not in app.state.store.rooms
    assert who.key not in app.state.reviewer_resources.profiles


def test_saved_profile_and_room_snapshot_are_session_scoped(site):
    app, client = site
    _, cookie, _ = reviewer(site)
    own_resources(client)
    code = make_room(client)
    r = app.state.reviewer_resources.rooms[code]
    # A second sign-in to the same account does not expose the first session's key.
    sign_in(site,"judge")
    assert client.get("/api/reviewer/workspace").json()["configured"] is False
    client.cookies.set(COOKIE,cookie)
    response=client.post("/api/reviewer/workspace",json={
        "gnani_source":"own", "evon_source":"own", "gnani_api_key":"new-key",
        "evon_base_url":"https://different--evon.modal.run/v1", "evon_model":"evon-review",
        "resource_consent":True})
    assert response.is_success, response.text
    assert not response.json()["profile"]["evon_key_set"]
    assert r.speech.headers["X-API-Key-ID"] == "reviewer-private-key"
    assert r.translator.settings.evon_api_key.get_secret_value() == "reviewer-model-key"


def test_cold_model_prevents_new_translated_microphone_source(site, monkeypatch):
    app, client = site
    reviewer(site)
    own_resources(client)
    code = make_room(client)
    store = app.state.store
    state = store.rooms[code]
    speaker = Participant(name="Reviewer", language="hi", muted=True)
    listener = Participant(name="Listener", language="te", muted=True)
    state.room.participants.extend([speaker, listener])
    monkeypatch.setattr(store, "is_active", lambda *args: True)
    transport = SimpleNamespace(rooms={code:SimpleNamespace(closed=False, disconnected=False,
        recognition_active=set(), room=SimpleNamespace(remote_participants={speaker.id:object(),listener.id:object()}))})
    result = conference_readiness(store, state, speaker, transport, app.state.service.usage)
    assert not result.microphone.can_unmute and result.microphone.reason_code == "engine_not_ready"
    app.state.reviewer_resources.engine_for(code).touch()  # Fixture readiness only; no probe.
    result = conference_readiness(store, state, speaker, transport, app.state.service.usage)
    assert result.microphone.can_unmute and result.microphone.reason_code == "ready_for_attempt"
