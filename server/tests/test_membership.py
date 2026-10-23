import time

import pytest
from conftest import auth, create_member
from fastapi import HTTPException
from starlette.websockets import WebSocketDisconnect

from artha_mesh.store import token_digest


def test_health_identifies_demo_and_never_exposes_credentials(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    health = response.json()
    assert health["mode"] == "demo"
    assert {language["code"] for language in health["languages"]} == {"hi", "ta", "bn", "en"}
    assert "session_token" not in response.text
    assert "embedding" not in response.text


def test_transcript_requires_membership_for_the_exact_room(client):
    first, member = create_member(client)
    second, outsider = create_member(client)
    assert first != second
    assert client.get(f"/api/rooms/{first}/transcript").status_code == 401
    assert client.get(f"/api/rooms/{first}/transcript", headers={"Authorization": "Bearer invalid"}).status_code == 401
    assert client.get(f"/api/rooms/{first}/transcript", headers=auth(outsider)).status_code == 403
    assert client.get(f"/api/rooms/{first}/transcript", headers=auth(member)).status_code == 200
    public = client.get(f"/api/rooms/{first}")
    assert public.status_code == 200
    assert "turns" not in public.json()
    assert "session_token" not in public.text
    assert member["session_token"] not in public.text


def test_member_can_only_leave_themself_and_token_is_revoked(client):
    code, first = create_member(client)
    _, second = create_member(client, code, name="Meena", language="ta")
    attempted = client.post(f"/api/rooms/{code}/leave", json={"participant_id": second["participant"]["id"]}, headers=auth(first))
    assert attempted.status_code == 403
    left = client.post(f"/api/rooms/{code}/leave", json={"participant_id": first["participant"]["id"]}, headers=auth(first))
    assert left.status_code == 200
    assert client.get(f"/api/rooms/{code}/transcript", headers=auth(first)).status_code == 401
    assert client.get(f"/api/rooms/{code}/transcript", headers=auth(second)).status_code == 200


def test_unknown_language_and_client_injected_identity_are_rejected(client):
    code = client.post("/api/rooms", json={"title": "Validation"}).json()["code"]
    assert client.post(f"/api/rooms/{code}/join", json={"name": "A", "language": "xx"}).status_code == 422
    response = client.post(f"/api/rooms/{code}/join", json={
        "name": "A", "language": "hi", "is_agent": True,
    })
    assert response.status_code == 422


def test_session_store_retains_only_digest_and_expiry_is_enforced(client):
    code, member = create_member(client)
    token = member["session_token"]
    store = client.app.state.store
    assert token not in store.sessions
    assert token_digest(token) in store.sessions
    store.sessions[token_digest(token)].expires_at = time.time() - 1
    assert client.get(f"/api/rooms/{code}/transcript", headers=auth(member)).status_code == 401


def test_websocket_rejects_foreign_member_and_untrusted_origin(client):
    code, member = create_member(client)
    _, outsider = create_member(client)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/api/rooms/{code}/events?token={outsider['session_token']}", headers={"origin": "http://localhost:5173"}):
            pass
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/api/rooms/{code}/events?token={member['session_token']}", headers={"origin": "https://untrusted.example"}):
            pass
    with client.websocket_connect(f"/api/rooms/{code}/events?token={member['session_token']}", headers={"origin": "http://localhost:5173"}) as socket:
        snapshot = socket.receive_json()
        assert snapshot["type"] == "room.snapshot"
        assert snapshot["payload"]["room"]["code"] == code


def test_expired_room_prunes_sessions_and_voices(client):
    code, member = create_member(client)
    store = client.app.state.store
    store.rooms[code].expires_at = time.time() - 1
    assert code in store.prune()
    assert token_digest(member["session_token"]) not in store.sessions
    with pytest.raises(HTTPException) as error:
        store.authenticate(member["session_token"])
    assert error.value.status_code == 401


def test_expired_websocket_membership_cannot_receive_new_room_events(client):
    code, member = create_member(client)
    _, other = create_member(client, code, name="Listener", language="ta")
    with client.websocket_connect(f"/api/rooms/{code}/events?token={member['session_token']}", headers={"origin": "http://localhost:5173"}) as socket:
        assert socket.receive_json()["type"] == "room.snapshot"
        client.app.state.store.sessions[token_digest(member["session_token"])].expires_at = time.time() - 1
        client.patch(f"/api/rooms/{code}/participants/me", headers=auth(other), json={"muted": True})
        with pytest.raises(WebSocketDisconnect):
            socket.receive_json()


def test_clone_cannot_be_selected_at_public_join_without_owned_session_reference(client):
    code, _ = create_member(client)
    response = client.post(f"/api/rooms/{code}/join", json={
        "name": "Another member", "language": "ta", "voice_mode": "cloned",
        "voice_profile_id": "someone-elses-profile", "consent": True,
    })
    assert response.status_code == 422


def test_live_setup_fails_honestly_and_processing_consent_precedes_media_connection():
    from fastapi.testclient import TestClient

    from artha_mesh.config import Settings
    from artha_mesh.main import create_app

    settings = Settings(mode="live", livekit_url="", livekit_api_key="", livekit_api_secret="",
                        gnani_api_key="", evon_base_url="", evon_model="", _env_file=None)
    with TestClient(create_app(settings)) as live:
        code = live.post("/api/rooms", json={"title": "Incomplete setup"}).json()["code"]
        response = live.post(f"/api/rooms/{code}/join", json={"name": "A", "language": "hi", "consent": True})
        assert response.status_code == 503
        assert live.get(f"/api/rooms/{code}").json()["participants"] == []
        health = live.get("/api/health").json()
        assert health["mode"] == "live"
        assert any(provider["status"] == "missing" for provider in health["providers"])
    configured = Settings(mode="live", livekit_url="wss://fixture.invalid", livekit_api_key="fake-key",
                          livekit_api_secret="fake-secret-for-test-only", gnani_api_key="fake-gnani",
                          evon_base_url="https://fixture.invalid/v1", evon_model="fixture-evon", _env_file=None)
    with TestClient(create_app(configured)) as live:
        code = live.post("/api/rooms", json={"title": "Consent gate"}).json()["code"]
        response = live.post(f"/api/rooms/{code}/join", json={"name": "A", "language": "hi", "consent": False})
        assert response.status_code == 422
        assert "fake-secret" not in live.get("/api/health").text
        assert "fake-gnani" not in live.get("/api/health").text
