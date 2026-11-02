"""Explicit raw-audio testing is a real RTC path with no speech-provider clients."""
import asyncio
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from artha_mesh.config import Settings
from artha_mesh.errors import ProviderError
from artha_mesh.models import Participant
from artha_mesh.services.usage import UsageGuard
from artha_mesh.store import Store, token_digest
from artha_mesh.transport.livekit import OutputTrack, RoomTransport


def transport_settings(**values):
    return Settings(mode="transport", livekit_url="ws://127.0.0.1:7880",
                    livekit_api_key="devkey", livekit_api_secret="local-transport-fixture-secret-for-tests",
                    gnani_api_key="", evon_base_url="", evon_model="", _env_file=None, **values)


class ConnectedTransport:
    def __init__(self):
        self.connected = 0

    async def ensure_room(self, _state):
        self.connected += 1

    async def reconfigure(self, *_args):
        pass

    async def aclose(self):
        pass


def test_transport_constructs_no_paid_provider_clients_and_disables_interpretation(monkeypatch):
    from artha_mesh import main

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Transport mode must never construct a paid provider client or open a usage ledger")

    monkeypatch.setattr(main, "GnaniSpeech", forbidden)
    monkeypatch.setattr(main, "EvonTranslator", forbidden)
    monkeypatch.setattr(UsageGuard, "_connection", forbidden)
    app = main.create_app(transport_settings())
    transport = ConnectedTransport()
    app.state.service.transport = transport
    with TestClient(app) as client:
        health = client.get("/api/health").json()
        assert health["mode"] == "transport"
        assert [p["status"] for p in health["providers"]] == ["configured", "disabled", "disabled", "disabled"]
        code = client.post("/api/rooms", json={"title": "Original audio test"}).json()["code"]
        def join(consent):
            return client.post(f"/api/rooms/{code}/join", json={
                "name": "Asha", "language": "hi", "consent": consent,
            })
        assert join(False).status_code == 422
        assert transport.connected == 0
        response = join(True)
        assert response.status_code == 200, response.text
        member = response.json()
        assert member["room"]["mode"] == "transport"
        assert member["participant"]["muted"] is True
        assert member["livekit"]["url"] == "ws://127.0.0.1:7880"
        assert transport.connected == 1
        headers = {"Authorization": "Bearer " + member["session_token"]}
        text = client.post(f"/api/rooms/{code}/text", headers=headers, json={"text": "नमस्ते"})
        assert text.status_code == 409
        clone = client.patch(f"/api/rooms/{code}/participants/me", headers=headers, json={"voice_mode": "cloned"})
        assert clone.status_code == 409
        enroll = client.post("/api/voice-profiles", files={"audio_file": ("own.wav", b"not audio", "audio/wav")},
                             data={"name": "Own voice", "consent": "true", "owner_token": member["session_token"]})
        assert enroll.status_code == 409
        usage = client.get("/api/usage").json()
        assert usage["enforcement"]["status"] == "disabled"
        assert usage["approval"]["status"] == "disabled"
        assert all(resource["used"] == 0 for resource in usage["resources"])
        assert client.get(f"/api/rooms/{code}/performance", headers=headers).json()["samples"] == []


def test_transport_missing_configuration_mentions_only_livekit():
    from artha_mesh.main import create_app

    settings = Settings(mode="transport", livekit_url="", livekit_api_key="", livekit_api_secret="",
                        gnani_api_key="", evon_base_url="", evon_model="", _env_file=None)
    with TestClient(create_app(settings)) as client:
        code = client.post("/api/rooms", json={"title": "Missing local room server"}).json()["code"]
        response = client.post(f"/api/rooms/{code}/join", json={"name": "A", "language": "hi", "consent": True})
        assert response.status_code == 503
        assert "LIVEKIT_URL" in response.json()["detail"]
        assert "GNANI" not in response.text and "EVON" not in response.text


def room_fixture():
    store = Store(transport_settings())
    state = store.create_room("Original audio across languages")
    participants = [
        Participant(id="source", name="Asha", language="hi"),
        Participant(id="tamil", name="Kavya", language="ta"),
        Participant(id="bengali", name="Ritam", language="bn"),
        Participant(id="expired", name="Expired", language="en"),
        Participant(id="demo", name="Scripted", language="hi", is_demo=True),
    ]
    state.room.participants.extend(participants)
    for participant in participants:
        token = store.issue_session(state, participant.id)
        if participant.id == "expired":
            store.sessions[token_digest(token)].expires_at = time.time() - 1
    return store, state, participants


def test_raw_routing_excludes_self_scripted_and_expired_members_and_language_is_ignored():
    store, state, _ = room_fixture()
    transport = RoomTransport(store, state, None, None)
    assert transport._output_recipients("source", "all") == ["tamil", "bengali"]
    assert transport._output_recipients("source", "hi") == []
    assert transport._output_recipients("expired", "all") == []
    assert transport._recognition_eligible("source") is False
    permissions = []
    local = SimpleNamespace(set_track_subscription_permissions=lambda **kwargs: permissions.append(kwargs))
    transport.room = SimpleNamespace(local_participant=local)
    transport.outputs[("source", "all")] = OutputTrack(None, SimpleNamespace(sid="raw-source"), "source", "all", 24000)
    transport._permissions()
    allowed = {p.participant_identity: list(p.allowed_track_sids) for p in permissions[-1]["participant_permissions"]}
    assert allowed == {"source": [], "tamil": ["raw-source"], "bengali": ["raw-source"]}


async def test_raw_frames_reach_different_language_listener_without_starting_recognition(monkeypatch):
    from livekit import rtc

    class AudioStream:
        def __init__(self, **_kwargs):
            pass

        def __aiter__(self):
            return self

        async def __anext__(self):
            await asyncio.sleep(0.01)
            return SimpleNamespace(frame=SimpleNamespace(data=b"\x11\x00" * 160))

        async def aclose(self):
            pass

    class Resampler:
        def __init__(self, *_args, **_kwargs):
            pass

        def push(self, frame):
            return [frame]

    class ForbiddenSpeech:
        async def transcribe(self, *_args, **_kwargs):
            raise AssertionError("Raw transport must never invoke STT")
            yield

    monkeypatch.setattr(rtc, "AudioStream", AudioStream)
    monkeypatch.setattr(rtc, "AudioResampler", Resampler)
    store, state, participants = room_fixture()
    transport = RoomTransport(store, state, ForbiddenSpeech(), None)
    forwarded = []

    async def capture(frame):
        forwarded.append(bytes(frame.data))

    async def output(speaker_id, language, _rate):
        assert speaker_id == "source" and language == "all"
        async def ready():
            pass
        return SimpleNamespace(tts_active=False, source=SimpleNamespace(capture_frame=capture),
                               publication=SimpleNamespace(wait_for_subscription=ready))

    monkeypatch.setattr(transport, "_output", output)
    task = asyncio.create_task(transport._read_audio(object(), "source"))
    try:
        async with asyncio.timeout(1):
            while len(forwarded) < 3:
                await asyncio.sleep(0.01)
        assert forwarded[0] == b"\x11\x00" * 160
        assert not task.done()
        participants[0].muted = True
        count = len(forwarded)
        await asyncio.sleep(0.05)
        assert len(forwarded) == count
        assert state.turns == [] and list(state.performance_samples) == []
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def test_usage_guard_blocks_any_accidental_reservation_before_storage():
    guard = UsageGuard(transport_settings())
    with pytest.raises(ProviderError, match="disabled in transport"):
        guard.reserve({"tts_requests": 1})


async def test_muting_unpublishes_raw_track_and_closes_its_source():
    store, state, participants = room_fixture()
    transport = RoomTransport(store, state, None, None)
    cleared, closed, unpublished = [], [], []

    async def close():
        closed.append(True)

    async def unpublish(sid):
        unpublished.append(sid)

    transport.room = SimpleNamespace(
        remote_participants={}, local_participant=SimpleNamespace(
            unpublish_track=unpublish, set_track_subscription_permissions=lambda **_: None))
    output = OutputTrack(SimpleNamespace(clear_queue=lambda: cleared.append(True), aclose=close),
                         SimpleNamespace(sid="negotiated-raw"), "source", "all", 24000)
    transport.outputs[("source", "all")] = output
    participants[0].muted = True
    await transport.reconfigure("source")
    assert transport.outputs == {}
    assert cleared == [True] and closed == [True] and unpublished == ["negotiated-raw"]
    participants[0].muted = False
    await transport.reconfigure("source")
    assert transport.outputs == {}
    state.room.participants.remove(participants[0])
    await transport.reconfigure("source")
    assert transport.outputs == {}
    assert closed == [True] and unpublished == ["negotiated-raw"]
