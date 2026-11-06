"""HTTP contracts using an in-process fake RTC emitter, never speech providers."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from charcha.config import Settings
from charcha.errors import ProviderError
from charcha.models import Participant


@pytest.fixture
def probe_client(monkeypatch):
    from charcha import main

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Receiver probes must not construct a paid speech provider")

    monkeypatch.setattr(main, "GnaniSpeech", forbidden)
    monkeypatch.setattr(main, "EvonTranslator", forbidden)
    app = main.create_app(Settings(mode="transport", _env_file=None))
    state = app.state.store.create_room("Local receiver probe")
    tokens = []
    for person in [Participant(name="Listener", language="hi"), Participant(name="Other", language="ta")]:
        state.room.participants.append(person)
        tokens.append(app.state.store.issue_session(state, person.id))
    other_state = app.state.store.create_room("Another room")
    outsider = Participant(name="Outside", language="en")
    other_state.room.participants.append(outsider)
    other_token = app.state.store.issue_session(other_state, outsider.id)
    emitted = []
    audio_room = SimpleNamespace(closed=False, disconnected=False, failure=False)

    async def send_probe(challenge):
        if audio_room.failure:
            raise ProviderError("Receiver tone was not delivered", False)
        emitted.append(challenge)

    async def close():
        audio_room.closed = True

    audio_room.send_probe = send_probe
    audio_room.aclose = close
    app.state.transport.rooms[state.room.code] = audio_room
    with TestClient(app) as client:
        yield client, state.room.code, tokens, other_token, emitted, audio_room


def auth(token):
    return {"Authorization": "Bearer " + token}


@pytest.mark.parametrize("nonfinite", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_json_is_rejected_without_echoing_input_or_crashing(probe_client, nonfinite):
    client, code, tokens, _, _, _ = probe_client
    response = client.post(f"/api/rooms/{code}/audio-probes/report",
                           content='{"probe_id":"abcdefghijklmnop","elapsed_ms":' + nonfinite + '}',
                           headers={**auth(tokens[0]), "Content-Type": "application/json"})
    assert response.status_code == 422
    assert all("input" not in error for error in response.json()["detail"])


def test_probe_routes_require_room_membership_and_exact_listener(probe_client):
    client, code, tokens, outsider, emitted, _ = probe_client
    base = f"/api/rooms/{code}/audio-probes"
    assert client.post(base).status_code == 401
    assert client.get(base).status_code == 401
    assert client.post(base, headers=auth(outsider)).status_code == 403
    challenge = client.post(base, headers=auth(tokens[0])).json()
    assert client.post(f"{base}/{challenge['probe_id']}/start", headers=auth(tokens[1])).status_code == 403
    assert emitted == []
    assert client.post(f"{base}/{challenge['probe_id']}/start", headers=auth(tokens[0])).status_code == 202
    assert len(emitted) == 1
    assert client.post(f"{base}/{challenge['probe_id']}/start", headers=auth(tokens[0])).status_code == 409
    body = {"probe_id": challenge["probe_id"], "elapsed_ms": 345.5}
    assert client.post(f"{base}/report", headers=auth(tokens[1]), json=body).status_code == 403
    response = client.post(f"{base}/report", headers=auth(tokens[0]), json=body)
    assert response.status_code == 200, response.text
    assert response.json()["elapsed_ms"] == 345.5
    assert client.post(f"{base}/report", headers=auth(tokens[0]), json=body).status_code == 404
    summary = client.get(base, headers=auth(tokens[0])).json()
    assert summary["summary"]["p50_ms"] == 345.5
    assert summary["measurement"]["physical_speaker_output_measured"] is False
    assert summary["measurement"]["translation_end_to_end_measured"] is False
    assert client.get(f"/api/rooms/{code}/performance", headers=auth(tokens[0])).json()["samples"] == []
    assert all(row["used"] == 0 for row in client.get("/api/usage").json()["resources"])


def test_probe_refuses_disconnected_room_and_records_delivery_failure(probe_client):
    client, code, tokens, _, emitted, audio_room = probe_client
    base = f"/api/rooms/{code}/audio-probes"
    challenge = client.post(base, headers=auth(tokens[0])).json()
    audio_room.disconnected = True
    assert client.post(f"{base}/{challenge['probe_id']}/start", headers=auth(tokens[0])).status_code == 409
    assert emitted == []
    audio_room.disconnected = False
    audio_room.failure = True
    response = client.post(f"{base}/{challenge['probe_id']}/start", headers=auth(tokens[0]))
    assert response.status_code >= 400
    snapshot = client.get(base, headers=auth(tokens[0])).json()
    assert snapshot["samples"][0]["status"] == "delivery_error"
    assert snapshot["summary"]["p95_ms"] is None
    assert emitted == []


@pytest.mark.parametrize("changes", [
    {"elapsed_ms": -1}, {"elapsed_ms": 30001}, {"elapsed_ms": "NaN"},
    {"elapsed_ms": None}, {"output_enabled": False}, {"participant_id": "forged"},
])
def test_invalid_probe_reports_never_create_latency(probe_client, changes):
    client, code, tokens, _, _, _ = probe_client
    base = f"/api/rooms/{code}/audio-probes"
    challenge = client.post(base, headers=auth(tokens[0])).json()
    client.post(f"{base}/{challenge['probe_id']}/start", headers=auth(tokens[0]))
    payload = {"probe_id": challenge["probe_id"], "elapsed_ms": 100, **changes}
    assert client.post(f"{base}/report", headers=auth(tokens[0]), json=payload).status_code == 422
    assert client.get(base, headers=auth(tokens[0])).json()["summary"]["sample_count"] == 0
