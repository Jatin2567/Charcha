from __future__ import annotations

import io
import wave

import pytest
from fastapi.testclient import TestClient

from artha_mesh.config import Settings
from artha_mesh.models import Participant


def wav(pcm=b"\x01\x00" * 640, rate=16000, channels=1):
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(2)
        target.setframerate(rate)
        target.writeframes(pcm)
    return output.getvalue()


@pytest.fixture
def app(monkeypatch, tmp_path):
    from artha_mesh import main

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Local audio lab must not construct provider clients")

    monkeypatch.setattr(main, "GnaniSpeech", forbidden)
    monkeypatch.setattr(main, "EvonTranslator", forbidden)
    return main.create_app(Settings(
        _env_file=None, mode="transport", local_audio_lab_enabled=True,
        audio_screening_mode="monitor", audio_screening_model_path=tmp_path / "missing.onnx",
        cors_origins=["http://127.0.0.1:5180"], gnani_api_key="", evon_api_key="",
    ))


def analyze(client, raw=None, **kwargs):
    return client.post("/api/audio-lab/analyze", files={"audio": ("sample.wav", wav() if raw is None else raw, "audio/wav")}, **kwargs)


def test_local_analysis_requires_consent_and_never_uses_providers(app):
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        assert client.get("/api/audio-lab/status").status_code == 200
        assert analyze(client).status_code == 422
        response = analyze(client, data={"consent": "true"}, headers={"Origin": "http://127.0.0.1:5180"})
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["provider_calls"] == 0
        assert payload["persisted"] is False
        assert payload["result"]["verdict"] == "unknown"
        assert payload["result"]["score"] is None
        assert all(resource["used"] == 0 for resource in client.get("/api/usage").json()["resources"])


@pytest.mark.parametrize("ip", ["192.168.1.10", "8.8.8.8", "testclient"])
def test_nonloopback_clients_denied(app, ip):
    with TestClient(app, client=(ip, 50000)) as client:
        assert client.get("/api/audio-lab/status").status_code == 403
        assert analyze(client, data={"consent": "true"}).status_code == 403


def test_foreign_origin_denied_even_over_loopback(app):
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        headers = {"Origin": "https://unrelated.example"}
        assert client.get("/api/audio-lab/status", headers=headers).status_code == 403
        assert analyze(client, data={"consent": "true"}, headers=headers).status_code == 403


def test_disabled_and_live_modes_reject_lab(app):
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        app.state.settings.local_audio_lab_enabled = False
        assert client.get("/api/audio-lab/status").status_code == 403
        app.state.settings.local_audio_lab_enabled = True
        app.state.settings.mode = "live"
        assert analyze(client, data={"consent": "true"}).status_code == 403


@pytest.mark.parametrize("raw", [b"notwav", wav()[:-1], wav(rate=8000), wav(channels=2)])
def test_invalid_truncated_and_wrong_format_uploads_rejected(app, raw):
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        assert analyze(client, raw, data={"consent": "true"}).status_code == 422


def test_oversized_upload_rejected_before_analysis(app):
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        assert analyze(client, b"x" * 1_024_001, data={"consent": "true"}).status_code == 413


def test_room_screening_report_requires_matching_active_membership(app):
    state = app.state.store.create_room("Screening report access")
    participant = Participant(name="Asha", language="hi")
    state.room.participants.append(participant)
    token = app.state.store.issue_session(state, participant.id)
    unrelated = app.state.store.create_room("Unrelated room")
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        path = f"/api/rooms/{state.room.code}/screening"
        assert client.get(path).status_code == 401
        headers = {"Authorization": "Bearer " + token}
        response = client.get(path, headers=headers)
        assert response.status_code == 200
        assert response.json()["samples"] == []
        assert response.json()["experimental"] is True
        assert client.get(f"/api/rooms/{unrelated.room.code}/screening", headers=headers).status_code in {401, 403}


def test_room_snapshot_exposes_real_detector_status_without_provider_calls(app):
    state = app.state.store.create_room("VoiceShield readiness")
    participant = Participant(name="Asha", language="hi")
    state.room.participants.append(participant)
    token = app.state.store.issue_session(state, participant.id)
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        with client.websocket_connect(
            f"/api/rooms/{state.room.code}/events",
            subprotocols=["artha-events", f"artha-token.{token}"],
            headers={"origin": "http://127.0.0.1:5180"},
        ) as socket:
            payload = socket.receive_json()["payload"]
            assert payload["screening"] == {}
            assert payload["screening_status"]["mode"] == "monitor"
            assert payload["screening_status"]["model"]["ready"] is False
            assert payload["screening_status"]["provider_calls"] == 0
            assert "speech" not in payload["screening_status"]
