"""Meeting occupancy, silent periods and disconnects; no paid provider calls."""
import asyncio
import time
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from charcha.config import Settings
from charcha.errors import ProviderError
from charcha.main import create_app
from charcha.models import Participant
from charcha.services.engine import InterpretationEngine
from charcha.services.meeting_engine import MeetingEngineLifecycle
from charcha.store import Store, token_digest


def meeting(store, transport, *, connected=True, funded=True, mode=None):
    state = store.create_room("Meeting", audio_mode=mode, host_funded=funded)
    person = Participant(name="Host", language="hi", muted=True)
    state.room.participants.append(person)
    token = store.issue_session(state, person.id)
    transport.rooms[state.room.code] = SimpleNamespace(
        room=SimpleNamespace(remote_participants={person.id: object()} if connected else {}),
        closed=False, disconnected=False, reconnecting=False)
    return state, person, token


def fixture():
    store = Store(Settings(_env_file=None, mode="live", evon_serverless=True))
    transport = SimpleNamespace(rooms={})
    engine = SimpleNamespace(meeting_managed=False, meeting_rooms=set())
    engine.hold_meetings = lambda codes: setattr(engine, "meeting_rooms", set(codes))
    lifecycle = MeetingEngineLifecycle(store, transport, engine)
    return store, transport, engine, lifecycle


def test_only_connected_authorized_interpreted_meetings_hold_compute():
    store, transport, engine, lifecycle = fixture()
    store.create_room("Unused invitation", host_funded=True)
    meeting(store, transport, connected=False)
    meeting(store, transport, funded=False)
    meeting(store, transport, mode="original")
    lifecycle.sync()
    assert engine.meeting_managed and not engine.meeting_rooms
    active, _, _ = meeting(store, transport)
    lifecycle.sync()
    assert engine.meeting_rooms == {active.room.code}  # Muted and solo still means meeting.


def test_two_meetings_share_lifetime_and_explicit_last_leave_releases():
    store, transport, engine, lifecycle = fixture()
    a, _, ta = meeting(store, transport)
    b, _, tb = meeting(store, transport)
    lifecycle.sync()
    assert engine.meeting_rooms == {a.room.code, b.room.code}
    store.forget_session(ta)
    lifecycle.sync()
    assert engine.meeting_rooms == {b.room.code}
    store.forget_session(tb)
    lifecycle.sync()
    assert not engine.meeting_rooms  # No reconnect grace for revoked membership.


def test_crashed_tab_gets_bounded_reconnect_grace_not_full_session_lifetime(monkeypatch):
    store, transport, engine, lifecycle = fixture()
    stamp = [100.0]
    monkeypatch.setattr("charcha.services.meeting_engine.time.monotonic", lambda: stamp[0])
    state, person, _ = meeting(store, transport)
    lifecycle.sync()
    remote = transport.rooms[state.room.code].room.remote_participants
    remote.clear()
    stamp[0] = 129
    lifecycle.sync()
    assert engine.meeting_rooms
    remote[person.id] = object()
    lifecycle.sync()  # Recovery renews presence without a new inference container.
    remote.clear()
    stamp[0] = 160
    lifecycle.sync()
    assert not engine.meeting_rooms


@pytest.mark.parametrize("reason", ["room_expired", "membership_expired", "closed", "removed", "agent_only"])
def test_expired_or_closed_rooms_never_retain_gpu(reason):
    store, transport, engine, lifecycle = fixture()
    state, person, token = meeting(store, transport)
    lifecycle.sync()
    if reason == "room_expired":
        state.expires_at = time.time() - 1
    elif reason == "membership_expired":
        store.sessions[token_digest(token)].expires_at = time.time() - 1
    elif reason == "closed":
        transport.rooms[state.room.code].closed = True
    elif reason == "removed":
        del store.rooms[state.room.code]
    else:
        person.is_agent = True
    lifecycle.sync()
    assert not engine.meeting_rooms


@pytest.mark.asyncio
async def test_silence_keeps_shared_engine_ready_and_last_leave_stops_pings(monkeypatch):
    monkeypatch.setattr("charcha.services.engine.MEETING_KEEPALIVE_SECONDS", .01)
    engine = InterpretationEngine(Settings(_env_file=None, evon_serverless=True,
        evon_base_url="https://test.modal.run/v1"), lambda: {})
    engine.meeting_managed = True
    calls, refreshed = [], asyncio.Event()
    async def respond(request):
        calls.append(request)
        if len(calls) == 3:
            refreshed.set()
        return httpx.Response(200)
    await engine.client.aclose()
    engine.client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(ProviderError):
            await engine.ensure_ready()
        assert not calls
        engine.hold_meetings({"first", "second"})
        await engine.ensure_ready()
        measured_startup = engine.duration_ms
        task = engine.meeting_task
        engine.hold_meetings({"second"})
        assert engine.meeting_task is task
        await asyncio.wait_for(refreshed.wait(), 1)
        assert engine.duration_ms == measured_startup  # Health pings aren't startup benchmarks.
        assert engine.status()["active_meetings"] == 1
        engine.hold_meetings(set())
        await asyncio.gather(task, return_exceptions=True)
        count = len(calls)
        for _ in range(20):
            engine.status()
        await asyncio.sleep(.03)
        assert len(calls) == count and engine.status()["active_meetings"] == 0
    finally:
        await engine.aclose()


@pytest.mark.asyncio
async def test_last_departure_cancels_cold_start_and_clean_rejoin_can_start():
    engine = InterpretationEngine(Settings(_env_file=None, evon_serverless=True,
        evon_base_url="https://test.modal.run/v1"), lambda: {})
    engine.meeting_managed = True
    entered, released = asyncio.Event(), asyncio.Event()
    async def respond(request):
        entered.set()
        await released.wait()
        return httpx.Response(200)
    await engine.client.aclose()
    engine.client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    try:
        engine.hold_meetings({"one"})
        await asyncio.wait_for(entered.wait(), 1)
        old, startup = engine.meeting_task, engine.task
        engine.hold_meetings(set())
        await asyncio.gather(old, startup, return_exceptions=True)
        assert old.cancelled() and startup.cancelled()
        released.set()
        engine.hold_meetings({"new"})
        await engine.ensure_ready()
        assert engine.status()["state"] == "ready"
    finally:
        await engine.aclose()


def test_public_status_and_admitted_but_unconnected_seat_cannot_start_gpu():
    app = create_app(Settings(_env_file=None, mode="live", evon_serverless=True))
    with TestClient(app) as client:
        state, _, token = meeting(app.state.store, app.state.transport, connected=False)
        headers = {"Authorization": "Bearer " + token}
        engine = app.state.pipeline.translator.engine
        for _ in range(3):
            result = client.get(f"/api/rooms/{state.room.code}/engine", headers=headers)
            assert result.status_code == 200
            assert result.json()["active_meetings"] == 0
        result = client.post(f"/api/rooms/{state.room.code}/engine", headers=headers)
        assert result.status_code == 409
        assert engine.task is None and engine.meeting_task is None
        app.state.transport.rooms.clear()  # No real LiveKit transport was created.
