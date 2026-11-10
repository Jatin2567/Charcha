"""Fault-injected reviewer cleanup uses only inert clients and local fixtures."""
import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from fastapi.testclient import TestClient
import pytest

from charcha.config import Settings
from charcha.accounts import Accounts
from charcha.errors import ProviderError
from charcha.main import create_app
from charcha.services.meeting_engine import MeetingEngineLifecycle
from charcha.services.reviewer_resources import ReviewerResources, RoomResources


def fixture(*, source="own", count=1):
    store = SimpleNamespace(rooms={})
    accounts = SimpleNamespace(sessions={})
    registry = ReviewerResources(None, store, accounts, None, None, None)
    registry.lifecycle = SimpleNamespace(cancel_preparation=Mock())
    registry.service = SimpleNamespace(prune_expired=AsyncMock(),
        pipeline=SimpleNamespace(close_room=AsyncMock()),
        transport=SimpleNamespace(remove=AsyncMock(), close_room=AsyncMock()))
    runtimes = []
    for i in range(count):
        code = f"room-{i}"
        account = SimpleNamespace(key="session", subject="reviewer", expires=time.time()+600)
        speech = SimpleNamespace(aclose=AsyncMock())
        translator = SimpleNamespace(client=SimpleNamespace(aclose=AsyncMock()),
                                     engine=SimpleNamespace(aclose=AsyncMock()))
        own_usage = SimpleNamespace(close=Mock()) if source == "own" else None
        runtime = RoomResources(account, SimpleNamespace(evon_source=source), None, speech, translator, own_usage)
        registry.rooms[code] = runtime
        registry.profiles[account.key] = object()  # Contains no actual credential.
        store.rooms[code] = SimpleNamespace(expires_at=time.time()+600,
            room=SimpleNamespace(participants=[SimpleNamespace(id="member", is_agent=False, is_demo=False)]))
        runtimes.append(runtime)
    return registry, runtimes


def assert_private_closed(runtime):
    runtime.speech.aclose.assert_awaited_once()
    runtime.translator.client.aclose.assert_awaited_once()
    runtime.translator.engine.aclose.assert_awaited_once()
    runtime.own_usage.close.assert_called_once()


@pytest.mark.asyncio
async def test_media_failure_detaches_credentials_and_retry_revisits_removed_media():
    registry, (runtime,) = fixture()
    registry.service.prune_expired.side_effect = RuntimeError("simulated media teardown failure")
    with pytest.raises(RuntimeError):
        await registry.clear("session")
    assert not registry.profiles and not registry.rooms
    assert registry.pending_teardown == {"room-0":("member",)}
    assert registry.store.rooms["room-0"].expires_at == 0
    assert_private_closed(runtime)
    registry.lifecycle.cancel_preparation.assert_called_once_with("room-0")
    with pytest.raises(ProviderError):
        registry.selected("speech", "room-0")
    # The ordinary service may already have removed Store state before failing.
    registry.store.rooms.clear()
    registry.service.prune_expired.side_effect = None
    await registry.prune()
    assert not registry.pending_teardown
    registry.service.pipeline.close_room.assert_awaited_once_with("room-0")
    registry.service.transport.remove.assert_awaited_once_with("room-0", "member")
    registry.service.transport.close_room.assert_awaited_once_with("room-0")
    assert_private_closed(runtime)  # Client close is not retried after successful detach.


@pytest.mark.asyncio
async def test_client_close_failure_cannot_skip_other_clients_or_ledger():
    registry, (runtime,) = fixture()
    runtime.speech.aclose.side_effect = RuntimeError("simulated client close failure")
    with pytest.raises(RuntimeError):
        await registry.clear("session")
    assert not registry.rooms and not registry.profiles
    assert_private_closed(runtime)


@pytest.mark.asyncio
async def test_cancellation_propagates_after_independent_resource_cleanup():
    registry, (runtime,) = fixture()
    registry.service.prune_expired.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await registry.clear("session")
    assert not registry.rooms and not registry.profiles
    assert registry.pending_teardown
    assert_private_closed(runtime)


@pytest.mark.asyncio
async def test_shared_engine_is_never_closed_by_reviewer_cleanup():
    registry, (runtime,) = fixture(source="shared")
    registry.service.prune_expired.side_effect = RuntimeError("simulated media failure")
    with pytest.raises(RuntimeError):
        await registry.clear("session")
    runtime.speech.aclose.assert_awaited_once()
    runtime.translator.client.aclose.assert_awaited_once()
    runtime.translator.engine.aclose.assert_not_awaited()
    assert not registry.rooms and not registry.profiles


@pytest.mark.asyncio
async def test_cleanup_releases_failed_rooms_hold_but_keeps_other_meeting_warm():
    registry, (runtime,) = fixture(source="shared")
    engine = runtime.translator.engine
    engine.settings = SimpleNamespace(evon_serverless=True)
    engine.meeting_rooms = {"room-0", "other"}
    engine.status = lambda: {"state":"ready"}
    engine.hold_meetings = lambda codes: setattr(engine, "meeting_rooms", set(codes))
    registry.store.settings = engine.settings
    registry.store.is_active = lambda code, pid: True
    original = registry.store.rooms["room-0"]
    original.host_funded = True
    original.room.code, original.room.mode, original.room.engine_on_demand = "room-0", "live", True
    registry.store.rooms["other"] = SimpleNamespace(expires_at=time.time()+600, host_funded=True,
        room=SimpleNamespace(code="other", mode="live", engine_on_demand=True,
            participants=[SimpleNamespace(id="other-member", is_agent=False, is_demo=False)]))
    transport = SimpleNamespace(rooms={"other":SimpleNamespace(closed=False, disconnected=False,
        room=SimpleNamespace(remote_participants={"other-member":object()}))})
    registry.lifecycle = MeetingEngineLifecycle(registry.store, transport, engine)
    registry.service.prune_expired.side_effect = RuntimeError("teardown failed")
    with pytest.raises(RuntimeError):
        await registry.clear("session")
    assert engine.meeting_rooms == {"other"}
    engine.aclose.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["clear", "prune", "aclose"])
async def test_one_room_failure_does_not_skip_other_room_cleanup(operation):
    registry, runtimes = fixture(count=2)
    registry.service.prune_expired.side_effect = [RuntimeError("simulated first failure"), None]
    with pytest.raises(RuntimeError):
        if operation == "clear":
            await registry.clear("session")
        else:
            await getattr(registry, operation)()
    assert not registry.rooms and not registry.profiles
    for runtime in runtimes:
        assert_private_closed(runtime)
    assert registry.lifecycle.cancel_preparation.call_count == 2


@pytest.mark.asyncio
async def test_retry_failure_remains_pending_without_retaining_runtime():
    registry, (runtime,) = fixture()
    registry.service.prune_expired.side_effect = RuntimeError("first failure")
    with pytest.raises(RuntimeError):
        await registry.close_room("room-0")
    registry.service.prune_expired.side_effect = None
    registry.service.transport.remove.side_effect = RuntimeError("retry failure")
    with pytest.raises(RuntimeError):
        await registry.prune()
    assert registry.pending_teardown == {"room-0":("member",)} and not registry.rooms
    registry.service.transport.close_room.assert_not_awaited()
    registry.service.transport.remove.side_effect = None
    await registry.prune()
    assert not registry.pending_teardown
    assert_private_closed(runtime)


@pytest.mark.asyncio
async def test_overlapping_cleanup_serializes_and_retries_after_first_failure():
    registry, (runtime,) = fixture()
    entered, release = asyncio.Event(), asyncio.Event()
    attempts = 0
    async def teardown():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            entered.set()
            await release.wait()
            raise RuntimeError("first teardown failed")
    registry.service.prune_expired.side_effect = teardown
    first = asyncio.create_task(registry.close_room("room-0"))
    await entered.wait()
    second = asyncio.create_task(registry.close_room("room-0"))
    await asyncio.sleep(0)
    assert attempts == 1
    release.set()
    results = await asyncio.gather(first, second, return_exceptions=True)
    assert isinstance(results[0], RuntimeError) and results[1] is None
    assert attempts == 2 and not registry.pending_teardown and not registry.teardown_locks
    assert_private_closed(runtime)


def test_background_cleanup_recovers_and_does_not_log_exception_secrets(tmp_path, monkeypatch, caplog):
    original_sleep = asyncio.sleep
    async def quick_cleanup(seconds, *args, **kwargs):
        return await original_sleep(.005 if seconds == 30 else seconds, *args, **kwargs)
    monkeypatch.setattr(asyncio, "sleep", quick_cleanup)
    app = create_app(Settings(_env_file=None, mode="demo", usage_db_path=tmp_path / "usage.sqlite3"))
    app.state.accounts.prune = Mock(side_effect=RuntimeError("secret-account-detail"))
    app.state.reviewer_resources.prune = AsyncMock(side_effect=[RuntimeError("secret-provider-detail"), None, None])
    app.state.service.prune_expired = AsyncMock()
    with TestClient(app):
        deadline = time.monotonic() + 2
        while app.state.service.prune_expired.await_count < 2 and time.monotonic() < deadline:
            time.sleep(.01)
        assert app.state.service.prune_expired.await_count >= 2
        assert app.state.accounts.prune.call_count >= 2
    assert "cleanup deferred" in caplog.text
    assert "secret-account-detail" not in caplog.text and "secret-provider-detail" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [RuntimeError("cleanup failed"), asyncio.CancelledError()])
async def test_logout_invalidates_all_memberships_even_if_reviewer_cleanup_fails(failure):
    who = SimpleNamespace(key="logging-out")
    own_member = SimpleNamespace(account_session=who.key, expires_at=time.time()+600)
    other_member = SimpleNamespace(account_session="other", expires_at=time.time()+600)
    accounts = SimpleNamespace(sessions={who.key:who}, store=SimpleNamespace(sessions={"own":own_member,"other":other_member}))
    service = SimpleNamespace(reviewer_resources=SimpleNamespace(clear=AsyncMock(side_effect=failure)),
                              prune_expired=AsyncMock())
    with pytest.raises(type(failure)):
        await Accounts.revoke(accounts, who, service)
    assert who.key not in accounts.sessions and own_member.expires_at == 0
    assert other_member.expires_at > time.time()
    service.prune_expired.assert_awaited_once()


@pytest.mark.asyncio
async def test_logout_preserves_cancellation_when_later_teardown_also_fails():
    who = SimpleNamespace(key="logging-out")
    member = SimpleNamespace(account_session=who.key, expires_at=time.time()+600)
    accounts = SimpleNamespace(sessions={who.key:who}, store=SimpleNamespace(sessions={"own":member}))
    service = SimpleNamespace(reviewer_resources=SimpleNamespace(clear=AsyncMock(side_effect=asyncio.CancelledError())),
                              prune_expired=AsyncMock(side_effect=RuntimeError("later failure")))
    with pytest.raises(asyncio.CancelledError):
        await Accounts.revoke(accounts, who, service)
    assert member.expires_at == 0
