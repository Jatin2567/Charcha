"""Refresh reconnect credentials with local identities and no provider/network calls."""

import datetime
import secrets
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import jwt
import pytest
from fastapi.testclient import TestClient
from livekit import api

from charcha import main
from charcha.accounts import COOKIE, Account
from charcha.config import Settings
from charcha.models import VoiceProfile
from charcha.store import StoredVoice, token_digest

JOIN = {"name": "Asha", "language": "hi", "consent": True}
SECRET = "local-connection-fixture-secret-for-tests"


def sign_in(app, client, subject="host"):
    cookie = secrets.token_urlsafe(32)
    key = token_digest(cookie)
    account = Account(key, subject, subject + "@example.test", False, time.time() + 600)
    app.state.accounts.sessions[key] = account
    client.cookies.set(COOKIE, cookie)
    return cookie, account


@pytest.fixture
def site(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Connection refresh must not start paid providers or call LiveKit")

    monkeypatch.setattr(main, "GnaniSpeech", forbidden)
    monkeypatch.setattr(main, "EvonTranslator", forbidden)
    monkeypatch.setattr(api, "LiveKitAPI", forbidden)
    app = main.create_app(Settings(
        _env_file=None, mode="transport", livekit_url="ws://127.0.0.1:7880",
        livekit_api_key="local-key", livekit_api_secret=SECRET,
        charcha_meeting_host_email="host@example.test",
        charcha_public_origin="https://meet.example.test",
    ))
    app.state.service.transport = SimpleNamespace(
        ensure_room=AsyncMock(), reconfigure=AsyncMock(), remove=AsyncMock(), close_room=AsyncMock(),
    )
    with TestClient(app, base_url="https://meet.example.test", headers={"X-Charcha-Request": "1"}) as client:
        sign_in(app, client)
        yield app, client


def join_host(site):
    _, client = site
    code = client.post("/api/rooms", json={"title": "Refresh test"}).json()["code"]
    response = client.post(f"/api/rooms/{code}/join", json=JOIN)
    assert response.status_code == 200, response.text
    member = response.json()
    return code, member, {"Authorization": "Bearer " + member["session_token"]}


def claims(token):
    return jwt.decode(token, SECRET, algorithms=["HS256"], options={"verify_exp": False})


def test_refresh_replaces_expired_media_token_without_rejoining_or_starting_providers(site, monkeypatch):
    app, client = site

    class EarlierDateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return super().now(tz) - datetime.timedelta(seconds=120)

    with monkeypatch.context() as earlier:
        earlier.setattr(api.access_token, "datetime", SimpleNamespace(
            datetime=EarlierDateTime, timedelta=datetime.timedelta, timezone=datetime.timezone,
        ))
        code, member, headers = join_host(site)
    assert claims(member["livekit"]["token"])["exp"] < time.time()
    state = app.state.store.room(code)
    seat = app.state.store.sessions[token_digest(member["session_token"])]
    original_expiry = seat.expires_at
    transport = app.state.service.transport
    transport.ensure_room.reset_mock()
    transport.reconfigure.reset_mock()

    response = client.post(f"/api/rooms/{code}/connection", headers=headers)
    assert response.status_code == 200, response.text
    resumed = response.json()
    assert resumed["session_token"] == member["session_token"]
    assert resumed["participant"] == member["participant"]
    assert resumed["is_host"] is True
    refreshed_claims = claims(resumed["livekit"]["token"])
    assert time.time() < refreshed_claims["exp"] <= time.time() + 60
    assert refreshed_claims["sub"] == member["participant"]["id"]
    assert refreshed_claims["video"]["room"] == code
    assert len(state.room.participants) == len(app.state.store.sessions) == 1
    assert seat.expires_at == original_expiry
    transport.ensure_room.assert_not_called()
    transport.reconfigure.assert_not_called()
    transport.remove.assert_not_called()


@pytest.mark.parametrize("deadline", ["membership", "room", "account"])
def test_refreshed_media_token_cannot_outlive_existing_deadlines(site, deadline):
    app, client = site
    code, member, headers = join_host(site)
    expires = time.time() + 8
    if deadline == "membership":
        app.state.store.sessions[token_digest(member["session_token"])].expires_at = expires
    elif deadline == "room":
        app.state.store.room(code).expires_at = expires
    else:
        account = app.state.accounts.current(client)
        app.state.accounts.sessions[account.key] = replace(account, expires=expires)
    response = client.post(f"/api/rooms/{code}/connection", headers=headers)
    assert response.status_code == 200, response.text
    assert time.time() < claims(response.json()["livekit"]["token"])["exp"] <= expires


def test_refresh_requires_original_account_sign_in_and_room(site):
    app, client = site
    code, _, headers = join_host(site)
    other_code, _, _ = join_host(site)
    assert client.post(f"/api/rooms/{other_code}/connection", headers=headers).status_code == 403
    sign_in(app, client, "other")
    assert client.post(f"/api/rooms/{code}/connection", headers=headers).status_code == 403
    sign_in(app, client, "host")
    assert client.post(f"/api/rooms/{code}/connection", headers=headers).status_code == 403
    client.cookies.clear()
    assert client.post(f"/api/rooms/{code}/connection", headers=headers).status_code == 401


@pytest.mark.parametrize("revoked", ["left", "expired", "room_expired", "account_expired", "logout"])
def test_refresh_cannot_revive_ended_membership(site, revoked):
    app, client = site
    code, member, headers = join_host(site)
    if revoked == "left":
        response = client.post(f"/api/rooms/{code}/leave", headers=headers,
                               json={"participant_id": member["participant"]["id"]})
        assert response.status_code == 200
    elif revoked == "expired":
        app.state.store.sessions[token_digest(member["session_token"])].expires_at = time.time() - 1
    elif revoked == "room_expired":
        app.state.store.room(code).expires_at = time.time() - 1
    elif revoked == "account_expired":
        account = app.state.accounts.current(client)
        app.state.accounts.sessions[account.key] = replace(account, expires=time.time() - 1)
    else:
        assert client.post("/api/account/logout").status_code == 200
    response = client.post(f"/api/rooms/{code}/connection", headers=headers)
    assert response.status_code == (404 if revoked == "room_expired" else 401)
    assert "livekit" not in response.json()


def test_guest_refresh_preserves_admission_and_enrolled_voice(site):
    app, client = site
    code, _, _ = join_host(site)
    host_cookie = client.cookies.get(COOKIE)
    guest_cookie, _ = sign_in(app, client, "guest")
    base = f"/api/rooms/{code}"
    assert client.post(base + "/connection").status_code == 401
    assert client.post(base + "/admission").json()["status"] == "pending"
    client.cookies.set(COOKIE, host_cookie)
    [entry] = client.get(base + "/admission/requests").json()["requests"]
    assert client.post(base + "/admission/requests/" + entry["id"],
                       json={"decision": "approve"}).status_code == 200
    client.cookies.set(COOKIE, guest_cookie)
    member = client.post(base + "/join", json=JOIN).json()
    participant_id = member["participant"]["id"]
    store = app.state.store
    state = store.room(code)
    admission = dict(state.admissions["guest"])
    # Seed an already enrolled profile; refreshing must never re-enroll or reassign it.
    profile = VoiceProfile(name="Own voice", mode="live")
    stored = StoredVoice(profile, token_digest(member["session_token"]), {"embedding": "fixture"})
    store.voices[profile.id] = stored
    state.voice_profiles[participant_id] = profile.id
    participant = next(p for p in state.room.participants if p.id == participant_id)
    participant.voice_mode = "cloned"
    headers = {"Authorization": "Bearer " + member["session_token"]}
    response = client.post(base + "/connection", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["participant"]["voice_mode"] == "cloned"
    assert response.json()["is_host"] is False
    assert state.admissions["guest"] == admission
    assert state.voice_profiles[participant_id] == profile.id
    assert store.voices[profile.id] is stored
    assert len(state.room.participants) == len(store.sessions) == 2

