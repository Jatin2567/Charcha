"""Host preparation leases and isolated engine occupancy; no provider calls."""
import asyncio
import time
from types import SimpleNamespace

import httpx
import pytest

from charcha.config import Settings
from charcha.errors import ProviderError
from charcha.models import Participant
from charcha.services.engine import InterpretationEngine
from charcha.services.meeting_engine import MeetingEngineLifecycle
from charcha.store import Store


class RecordingEngine:
    def __init__(self):
        self.settings = SimpleNamespace(evon_serverless=True)
        self.meeting_managed = False
        self.meeting_rooms = set()
        self.preparing_rooms = set()
        self.holds = []

    def hold_meetings(self, codes):
        self.meeting_rooms = set(codes)
        self.holds.append(set(codes))

    def status(self):
        return {"state": "idle", "active_meetings": len(self.meeting_rooms - self.preparing_rooms),
                "preparing_meetings": len(self.meeting_rooms & self.preparing_rooms)}


def setup(**kwargs):
    store = Store(Settings(_env_file=None, mode="live", evon_serverless=True))
    transport = SimpleNamespace(rooms={})
    engine = RecordingEngine()
    lifecycle = MeetingEngineLifecycle(store, transport, engine, **kwargs)
    state = store.create_room("Prejoin", host_funded=True)
    return store, transport, engine, lifecycle, state


def connect(store, transport, state):
    person = Participant(name="Host", language="hi", muted=True)
    state.room.participants.append(person)
    token = store.issue_session(state, person.id)
    transport.rooms[state.room.code] = SimpleNamespace(
        room=SimpleNamespace(remote_participants={person.id: object()}),
        closed=False, disconnected=False, reconnecting=False)
    return token


def test_start_and_status_reads_never_renew_prejoin_deadline(monkeypatch):
    _, _, engine, lifecycle, state = setup()
    wall, clock = [time.time()], [1000.0]
    monkeypatch.setattr("charcha.services.meeting_engine.time.time", lambda: wall[0])
    monkeypatch.setattr("charcha.services.meeting_engine.time.monotonic", lambda: clock[0])
    first = lifecycle.prepare(state.room.code, account_deadline=wall[0] + 2000)
    assert first["preparation_active"] and first["preparation_remaining_seconds"] == 900
    assert first["active_meetings"] == 0 and first["preparing_meetings"] == 1
    count = len(engine.holds)
    for _ in range(20):
        lifecycle.status(state.room.code)
    assert len(engine.holds) == count  # GETs do not reconcile or call engine controls.
    clock[0] += 30
    wall[0] += 30
    repeated = lifecycle.prepare(state.room.code, account_deadline=wall[0] + 2000)
    assert repeated["preparation_expires_at"] == first["preparation_expires_at"]
    assert repeated["preparation_remaining_seconds"] == 870
    clock[0] += 871
    wall[0] += 871
    assert not lifecycle.status(state.room.code)["preparation_active"]
    lifecycle.sync()
    assert not engine.meeting_rooms and not lifecycle.preparations


@pytest.mark.parametrize("bound", ["session", "room", "monotonic", "authorization", "authorization_error"])
def test_prepare_releases_at_earliest_authority_boundary(monkeypatch, bound):
    _, _, engine, lifecycle, state = setup()
    wall, clock, allowed = [time.time()], [1000.0], [True]
    monkeypatch.setattr("charcha.services.meeting_engine.time.time", lambda: wall[0])
    monkeypatch.setattr("charcha.services.meeting_engine.time.monotonic", lambda: clock[0])
    def permitted():
        if allowed[0] == "error":
            raise RuntimeError("not available")
        return allowed[0]
    if bound == "room":
        state.expires_at = wall[0] + 60
    session = wall[0] + (30 if bound == "session" else 2000)
    lifecycle.prepare(state.room.code, account_deadline=session, authorization_check=permitted)
    if bound == "session":
        wall[0] += 31
    elif bound == "room":
        wall[0] += 61
    elif bound == "monotonic":
        clock[0] += 901  # Even if the system wall clock goes backwards.
        wall[0] -= 120
    else:
        allowed[0] = False if bound == "authorization" else "error"
    lifecycle.sync()
    assert not engine.meeting_rooms and not lifecycle.status(state.room.code)["preparation_active"]


def test_cancel_preparation_keeps_other_prejoin_and_occupied_meetings():
    store, transport, engine, lifecycle, a = setup()
    b = store.create_room("Other host preparation", host_funded=True)
    c = store.create_room("Occupied", host_funded=True)
    token = connect(store, transport, c)
    for state in (a, b):
        lifecycle.prepare(state.room.code, account_deadline=time.time()+800)
    lifecycle.cancel_preparation(a.room.code)
    assert engine.meeting_rooms == {b.room.code, c.room.code}
    assert engine.preparing_rooms == {b.room.code}
    store.forget_session(token)
    lifecycle.sync()
    assert engine.meeting_rooms == {b.room.code}


def test_connected_call_consumes_preparation_and_last_departure_releases():
    store, transport, engine, lifecycle, state = setup()
    lifecycle.prepare(state.room.code, account_deadline=time.time()+800)
    token = connect(store, transport, state)
    lifecycle.sync()
    assert not lifecycle.preparations
    assert engine.meeting_rooms == {state.room.code}
    assert lifecycle.status(state.room.code)["active_meetings"] == 1
    lifecycle.cancel_preparation(state.room.code)
    assert engine.meeting_rooms == {state.room.code}
    store.forget_session(token)
    lifecycle.sync()
    assert not engine.meeting_rooms


def test_per_reviewer_engines_do_not_receive_other_room_holds():
    store, transport, shared, lifecycle, a = setup()
    private = RecordingEngine()
    b = store.create_room("Reviewer", host_funded=False)
    lifecycle.resolve_engine = lambda code: private if code == b.room.code else shared
    lifecycle.is_authorized = lambda state: state.host_funded or state is b
    lifecycle.prepare(a.room.code, account_deadline=time.time()+600)
    lifecycle.prepare(b.room.code, account_deadline=time.time()+600)
    assert shared.meeting_rooms == {a.room.code}
    assert private.meeting_rooms == {b.room.code}
    lifecycle.cancel_preparation(b.room.code)
    assert not private.meeting_rooms and shared.meeting_rooms == {a.room.code}
    # Replaced engine is released by the next authoritative reconciliation.
    lifecycle.resolve_engine = lambda code: private
    lifecycle.sync()
    assert not shared.meeting_rooms and private.meeting_rooms == {a.room.code}


@pytest.mark.parametrize("seconds", [-1, 0, 901, float("nan"), float("inf"), True])
def test_invalid_preparation_window_cannot_start_engine(seconds):
    _, _, engine, lifecycle, state = setup()
    with pytest.raises(ProviderError):
        lifecycle.prepare(state.room.code, account_deadline=time.time()+1800, seconds=seconds)
    assert not engine.holds and not lifecycle.preparations


@pytest.mark.parametrize("reason", ["unfunded", "original", "expired", "missing", "external"])
def test_ineligible_room_cannot_prepare(reason):
    _, _, engine, lifecycle, state = setup()
    code = state.room.code
    if reason == "unfunded":
        state.host_funded = False
    elif reason == "original":
        state.room.mode = "transport"
    elif reason == "expired":
        state.expires_at = time.time()-1
    elif reason == "missing":
        code = "not-a-room"
    else:
        engine.settings.evon_serverless = False
    with pytest.raises(ProviderError):
        lifecycle.prepare(code, account_deadline=time.time()+1800)
    assert not engine.holds and not lifecycle.preparations


@pytest.mark.asyncio
async def test_prejoin_can_complete_real_engine_state_machine_with_mocked_health():
    store, transport, _, _, state = setup()
    engine = InterpretationEngine(Settings(_env_file=None, evon_serverless=True,
        evon_base_url="https://reviewer-test.modal.run/v1"), lambda: {})
    calls = []
    async def health(request):
        calls.append(request)
        return httpx.Response(200)
    await engine.client.aclose()
    engine.client = httpx.AsyncClient(transport=httpx.MockTransport(health))
    lifecycle = MeetingEngineLifecycle(store, transport, engine)
    try:
        assert lifecycle.status(state.room.code)["state"] == "idle" and not calls
        lifecycle.prepare(state.room.code, account_deadline=time.time()+600)
        await engine.ensure_ready()
        assert lifecycle.status(state.room.code)["state"] == "ready"
        assert len(calls) == 1 and not state.room.participants
        assert lifecycle.status(state.room.code)["preparing_meetings"] == 1
        task = engine.meeting_task
        lifecycle.cancel_preparation(state.room.code)
        await asyncio.gather(task, return_exceptions=True)
        assert task.cancelled() and not engine.meeting_rooms
    finally:
        await engine.aclose()
