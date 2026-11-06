"""Conference admission is local state, not a provider health check or approval."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from charcha.config import Settings
from charcha.main import create_app
from charcha.models import Participant
from charcha.services.pipeline import Pipeline
from charcha.services.usage import RESOURCES, UsageGuard
from charcha.store import Store
from charcha.transport.livekit import RoomTransport


KEYS = [row[0] for row in RESOURCES]


def settings(**changes):
    values = dict(mode="live", _env_file=None, usage_require_flow_approval=True,
                  livekit_url="ws://localhost:7880", livekit_api_key="test-key",
                  livekit_api_secret="test-only-secret-long-enough-for-sha256",
                  gnani_api_key="test-gnani-private", evon_base_url="https://private.example/v1",
                  evon_model="test-model", usage_stt_max_retries=0)
    return Settings(**(values | changes))


def snapshot(*, active=True, status="approved", **remaining):
    budgets = dict.fromkeys(KEYS, 100)
    budgets.update(remaining)
    flow = dict(id="private-flow-id", purpose="live_interpretation", status=status,
                expires_at="2099-01-01T00:00:00+00:00", budgets=budgets,
                used=dict.fromkeys(KEYS, 0), before_balance=999)
    return {"enforcement": {"status": "ready"},
            "approval": {"active_flow_id": flow["id"] if active else None},
            "programme": {"flows": [flow]},
            "resources": [{"key": key, "remaining": 200} for key in KEYS]}


def capacity_fixture(data=None, **config):
    guard = object.__new__(UsageGuard)
    guard.settings = settings(**config)
    guard.host_room_expiry = None
    guard.snapshot = lambda: deepcopy(data if data is not None else snapshot())
    return guard


def test_free_capacity_never_reads_ledger():
    guard = capacity_fixture()
    guard.snapshot = lambda: pytest.fail("Free microphone must not inspect provider approval")
    result = guard.conference_capacity(0)
    assert result["status"] == "not_required" and not result["required"]
    assert set(result["remaining"]) == set(KEYS) - {"voice_enrollments"}
    assert set(result["remaining"].values()) == {None}


@pytest.mark.parametrize("key", ["mt_requests", "tts_requests"])
def test_capacity_requires_each_distinct_output_language(key):
    guard = capacity_fixture(snapshot(**{key: 1}))
    assert guard.conference_capacity(1)["status"] == "approved"
    assert guard.conference_capacity(2)["status"] == "exhausted"


def test_active_source_keeps_reserved_connection_but_cannot_start_another():
    guard = capacity_fixture(snapshot(stt_connections=0))
    assert guard.conference_capacity(1, source_active=True)["status"] == "approved"
    assert guard.conference_capacity(1)["status"] == "exhausted"


@pytest.mark.parametrize("key", ["stt_seconds", "mt_characters", "tts_characters"])
def test_capacity_still_needs_positive_time_and_characters(key):
    assert capacity_fixture(snapshot(**{key: 0})).conference_capacity(1)["status"] == "exhausted"


def test_capacity_respects_daily_limits_and_redacts_private_fields():
    data = snapshot()
    next(row for row in data["resources"] if row["key"] == "tts_requests")["remaining"] = 1
    result = capacity_fixture(data).conference_capacity(2)
    assert result["status"] == "exhausted" and result["remaining"]["tts_requests"] == 1
    assert "private-flow-id" not in str(result) and "balance" not in str(result)


@pytest.mark.parametrize("status,expected", [("expired", "expired"), ("exhausted", "exhausted"), ("closed", "locked")])
def test_latest_inactive_grant_is_described_without_reactivating_it(status, expected):
    assert capacity_fixture(snapshot(active=False, status=status)).conference_capacity(1)["status"] == expected


def test_wrong_purpose_or_unavailable_enforcement_cannot_enable_microphone():
    data = snapshot()
    data["programme"]["flows"][0]["purpose"] = "speech_test"
    assert capacity_fixture(data).conference_capacity(1)["status"] == "locked"
    data["enforcement"]["status"] = "unavailable"
    assert capacity_fixture(data).conference_capacity(1)["status"] == "unavailable"
    assert capacity_fixture(usage_require_flow_approval=False).conference_capacity(1)["status"] == "unavailable"


@pytest.fixture
def conference(monkeypatch, tmp_path):
    """Native SFU and provider calls are forbidden; only ASGI/membership state runs."""
    app = create_app(settings(usage_db_path=tmp_path / "unused-ledger.sqlite3"))
    app.state.test_snapshot = snapshot(active=False, status="closed")
    monkeypatch.setattr(app.state.usage, "snapshot", lambda: deepcopy(app.state.test_snapshot))
    app.state.reconfigurations = []

    async def ensure(state):
        return app.state.transport.rooms.setdefault(state.room.code, SimpleNamespace(
            room=SimpleNamespace(remote_participants={}), closed=False, disconnected=False,
            reconnecting=False, recognition_active={}))

    async def reconfigure(code, speaker_id=None):
        app.state.reconfigurations.append((code, speaker_id))

    async def remove(code, participant_id):
        audio = app.state.transport.rooms.get(code)
        if audio:
            audio.room.remote_participants.pop(participant_id, None)

    async def close_room(code):
        app.state.transport.rooms.pop(code, None)

    async def close_all():
        app.state.transport.rooms.clear()

    def forbidden(*_args, **_kwargs):
        pytest.fail("Readiness and microphone admission must not call a provider")

    monkeypatch.setattr(app.state.transport, "ensure_room", ensure)
    monkeypatch.setattr(app.state.transport, "reconfigure", reconfigure)
    monkeypatch.setattr(app.state.transport, "remove", remove)
    monkeypatch.setattr(app.state.transport, "close_room", close_room)
    monkeypatch.setattr(app.state.transport, "aclose", close_all)
    monkeypatch.setattr(app.state.pipeline.tts, "transcribe", forbidden)
    monkeypatch.setattr(app.state.pipeline.tts, "synthesize", forbidden)
    monkeypatch.setattr(app.state.pipeline.translator, "translate", forbidden)
    with TestClient(app) as client:
        yield client


def join(client, code=None, language="hi", *, connected=True):
    if code is None:
        code = client.post("/api/rooms", json={"title": "Ordinary conversation"}).json()["code"]
    response = client.post(f"/api/rooms/{code}/join", json={
        "name": language, "language": language, "voice_mode": "standard", "consent": True})
    assert response.status_code == 200, response.text
    member = response.json()
    if connected:
        client.app.state.transport.rooms[code].room.remote_participants[member["participant"]["id"]] = object()
    return code, member


def auth(member):
    return {"Authorization": "Bearer " + member["session_token"]}


def test_host_can_toggle_only_their_room_after_prejoin_notice(conference, monkeypatch):
    app = conference.app.state
    app.settings.audio_screening_on_demand = True
    monkeypatch.setattr(app.screening.screener, "status", lambda: {"ready": True})
    create = lambda: conference.post("/api/rooms", json={"title": "Private meeting"}).json()
    room, other = create(), create()
    assert room["screening_switchable"] and room["screening_mode"] == "off"
    base = "/api/rooms/" + room["code"]
    body = {"name": "Speaker", "language": "hi", "consent": True}
    assert conference.post(base + "/join", json=body).status_code == 422
    member = conference.post(base + "/join", json={**body, "screening_consent": True}).json()
    headers = auth(member)
    rtc_room = app.transport.rooms[room["code"]]
    resets = []
    rtc_room.reset_screening_windows = lambda: resets.append(True)
    def change(mode):
        return conference.patch(base + "/screening", headers=headers, json={"mode": mode})
    assert change("enforce").status_code == 422
    assert change("monitor").json()["mode"] == "monitor"
    assert change("monitor").json()["mode"] == "monitor"
    assert app.store.room(other["code"]).room.screening_mode == "off"
    assert app.store.room(room["code"]).room.screening_mode == "monitor"
    app.store.room(room["code"]).screening_latest["old"] = {"score": 0.5}
    assert change("off").json()["mode"] == "off" and len(resets) == 2
    assert conference.get(base + "/screening", headers=headers).json()["latest"] == {}
    assert conference.patch("/api/rooms/" + other["code"] + "/screening", headers=headers,
                            json={"mode": "monitor"}).status_code in (401, 403)
    app.store.room(room["code"]).owner = "another-host"
    assert change("monitor").status_code == 403


def ready(client, code, member):
    response = client.get(f"/api/rooms/{code}/conference-readiness", headers=auth(member))
    assert response.status_code == 200, response.text
    return response.json()


def patch(client, code, member, **changes):
    return client.patch(f"/api/rooms/{code}/participants/me", headers=auth(member), json=changes)


def test_readiness_is_authenticated_redacted_and_not_a_health_probe(conference):
    code, source = join(conference)
    _, outsider = join(conference)
    path = f"/api/rooms/{code}/conference-readiness"
    assert conference.get(path).status_code == 401
    assert conference.get(path, headers=auth(outsider)).status_code == 403
    result = ready(conference, code, source)
    assert result["providers"] == {"configured": True, "missing": [], "verification": "not_checked"}
    assert result["media"] == {"interpreter_connected": True, "member_connected": True}
    for private in ("private-flow-id", "private.example", "test-gnani-private", "balance", source["session_token"]):
        assert private not in str(result)
    conference.post(f"/api/rooms/{code}/leave", headers=auth(source), json={"participant_id": source["participant"]["id"]})
    assert conference.get(path, headers=auth(source)).status_code == 401


def test_alone_and_same_language_microphones_are_free_and_idempotent(conference):
    code, source = join(conference)
    assert ready(conference, code, source)["microphone"]["reason_code"] == "waiting_for_listener"
    _, _listener = join(conference, code)
    result = ready(conference, code, source)
    assert result["microphone"]["can_unmute"]
    assert result["provider_flow"]["status"] == "not_required"
    assert patch(conference, code, source, muted=False).status_code == 200
    after_first = len(conference.app.state.reconfigurations)
    assert patch(conference, code, source, muted=False).status_code == 200
    assert len(conference.app.state.reconfigurations) == after_first


def test_live_original_audio_does_not_require_translation_configuration(conference):
    # Assign through a new Settings instance to preserve SecretStr field typing.
    conference.app.state.store.settings = settings(gnani_api_key="", evon_base_url="", evon_model="")
    code, source = join(conference)
    result = ready(conference, code, source)
    assert result["microphone"]["can_unmute"] and not result["providers"]["configured"]
    assert patch(conference, code, source, muted=False).status_code == 200


def test_original_audio_mode_copy_does_not_claim_shared_language_or_translation(conference):
    conference.app.state.store.settings = settings(mode="transport")
    code, source = join(conference)
    alone = ready(conference, code, source)
    assert alone["microphone"]["detail"] == "You can enable your microphone. Join another participant to hear original audio."
    join(conference, code, "ta")
    paired = ready(conference, code, source)
    assert paired["microphone"]["reason_code"] == "original_audio_only"
    assert paired["microphone"]["detail"] == "Original audio is shared with connected participants. Speech providers are disabled in this mode."


def test_original_meeting_in_live_workspace_needs_no_provider_approval(conference):
    room = conference.post("/api/rooms", json={"title": "Original voices", "audio_mode": "original"}).json()
    assert room["mode"] == "transport"
    code, source = join(conference, room["code"])
    join(conference, code, "ta")
    report = ready(conference, code, source)
    assert report["mode"] == "transport" and report["microphone"]["can_unmute"]
    assert not report["provider_flow"]["required"]


def test_translated_microphone_requires_approval_before_state_changes(conference):
    code, source = join(conference)
    join(conference, code, "ta")
    before = len(conference.app.state.reconfigurations)
    result = ready(conference, code, source)
    assert result["microphone"]["reason_code"] == "provider_flow_locked"
    response = patch(conference, code, source, muted=False)
    assert response.status_code == 409 and response.json()["detail"]["code"] == "provider_flow_locked"
    assert len(conference.app.state.reconfigurations) == before
    assert ready(conference, code, source)["membership"]["muted"]


def test_unique_language_request_caps_and_current_source_are_distinct(conference):
    code, source = join(conference)
    join(conference, code, "ta")
    join(conference, code, "ta")
    conference.app.state.test_snapshot = snapshot(mt_requests=1, tts_requests=1)
    assert ready(conference, code, source)["microphone"]["can_unmute"]
    join(conference, code, "bn")
    assert ready(conference, code, source)["microphone"]["reason_code"] == "provider_flow_exhausted"
    conference.app.state.test_snapshot = snapshot(mt_requests=2, tts_requests=2)
    assert patch(conference, code, source, muted=False).status_code == 200
    conference.app.state.transport.rooms[code].recognition_active[source["participant"]["id"]] = object()
    conference.app.state.test_snapshot = snapshot(stt_connections=0, mt_requests=2, tts_requests=2)
    result = ready(conference, code, source)
    assert result["source"]["recognizer_task_active"]
    assert result["microphone"]["can_unmute"] and not result["microphone"]["may_start_new_source"]
    assert result["microphone"]["reason_code"] == "source_already_active"
    assert patch(conference, code, source, muted=True).status_code == 200


def test_media_and_language_changes_cannot_bypass_admission(conference):
    code, source = join(conference)
    join(conference, code, "hi")
    assert patch(conference, code, source, language="ta", muted=False).status_code == 409
    assert ready(conference, code, source)["membership"]["language"] == "hi"
    assert patch(conference, code, source, muted=False).status_code == 200
    assert patch(conference, code, source, language="ta").status_code == 409
    # Muting is always allowed, including an otherwise blocked language change.
    assert patch(conference, code, source, language="ta", muted=True).status_code == 200


def test_disconnected_listener_and_reconnecting_media_are_not_ready(conference):
    code, source = join(conference)
    join(conference, code, "ta", connected=False)
    conference.app.state.test_snapshot = snapshot()
    result = ready(conference, code, source)
    assert result["audience"]["translation_target_languages"] == ["ta"]
    assert result["audience"]["connected_translation_target_languages"] == []
    assert result["microphone"]["reason_code"] == "listener_media_not_ready"
    conference.app.state.transport.rooms[code].reconnecting = True
    assert ready(conference, code, source)["microphone"]["reason_code"] == "media_not_ready"
    assert patch(conference, code, source, muted=True).status_code == 200


def test_http_only_extra_language_does_not_inflate_connected_audience_budget(conference):
    code, source = join(conference)
    join(conference, code, "ta")
    join(conference, code, "bn", connected=False)
    conference.app.state.test_snapshot = snapshot(mt_requests=1, tts_requests=1)
    result = ready(conference, code, source)
    assert result["audience"]["translation_target_languages"] == ["bn", "ta"]
    assert result["audience"]["connected_translation_target_languages"] == ["ta"]
    assert result["microphone"]["can_unmute"]
    assert patch(conference, code, source, muted=False).status_code == 200


def transport_fixture():
    store = Store(settings())
    state = store.create_room("Admission")
    for language in ("hi", "ta", "bn"):
        member = Participant(id=language, name=language, language=language, muted=False)
        state.room.participants.append(member)
        store.issue_session(state, member.id)
    usage = capacity_fixture(snapshot(active=False, status="closed"))
    transport = RoomTransport(store, state, SimpleNamespace(usage=usage), None)
    transport.room = SimpleNamespace(remote_participants={"hi": object(), "ta": object()})
    return state, transport, usage


def test_audience_changes_cannot_start_asr_without_grant_and_active_stream_does_not_need_second_connection():
    state, transport, usage = transport_fixture()
    assert not transport._recognition_eligible("hi")
    usage.snapshot = lambda: snapshot(stt_connections=0)
    assert not transport._recognition_eligible("hi")
    transport.recognition_active["hi"] = object()
    assert transport._recognition_eligible("hi")
    transport.room.remote_participants.pop("ta")
    assert not transport._recognition_eligible("hi")


def test_recognizer_counts_only_connected_unique_languages_and_stops_during_sfu_outage():
    _state, transport, usage = transport_fixture()
    usage.snapshot = lambda: snapshot(mt_requests=1, tts_requests=1)
    assert transport._recognition_eligible("hi")  # Bengali HTTP member has no media.
    transport.reconnecting = True
    assert not transport._recognition_eligible("hi")
    transport.reconnecting = False
    transport.disconnected = True
    assert not transport._recognition_eligible("hi")


def test_pipeline_excludes_http_only_or_disconnected_members_before_mt_tts():
    state, transport, _usage = transport_fixture()
    pipeline = Pipeline(transport.store, None, None)
    pipeline.transport = SimpleNamespace(rooms={state.room.code: transport})
    assert {row.id for row in pipeline._active_participants(state)} == {"hi", "ta"}
    transport.room.remote_participants.pop("ta")
    assert {row.id for row in pipeline._active_participants(state)} == {"hi"}
    transport.reconnecting = True
    assert pipeline._active_participants(state) == []
