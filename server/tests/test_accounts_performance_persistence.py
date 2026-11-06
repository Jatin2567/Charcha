"""Fault-injected report persistence; no speech, model, or external services."""
import asyncio
import sqlite3
import threading
import time

import pytest

from charcha.config import Settings
from charcha.models import PerformanceSample
from charcha.services.listener_metrics import ListenerMetrics
from charcha.services.performance_history import PerformanceHistory
from charcha.store import Store
from test_accounts import site, identity
from test_accounts_performance_history import joined, leave


def setup(tmp_path):
    settings = Settings(_env_file=None, mode="demo", usage_db_path=tmp_path/"usage.sqlite3")
    store = Store(settings)
    state = store.create_room("Private meeting")
    state.performance_owners["listener"] = "owner"
    history = PerformanceHistory(settings, ListenerMetrics(store))
    history.retry_base_seconds = .02
    history.retry_max_seconds = .04
    return store, state, history


def sample(state, value=100):
    state.performance_samples.append(PerformanceSample(utterance_id="turn", source_language="hi",
        target_language="ta", input_kind="audio", measurement="server_first_pcm", total_ms=value))


def test_write_failure_retries_and_snapshot_is_immutable(tmp_path, monkeypatch):
    async def run():
        store, state, history = setup(tmp_path)
        sample(state)
        write = history._write
        failed = threading.Event()
        attempts = []
        def unreliable(snapshot):
            attempts.append(snapshot["status"])
            if len(attempts) <= 2:
                failed.set()
                raise OSError("test disk unavailable")
            write(snapshot)
        monkeypatch.setattr(history, "_write", unreliable)
        await history.start()
        history.enqueue(state, "completed")
        state.performance_samples.clear()  # Already-captured data must be independent.
        while not failed.is_set():
            await asyncio.sleep(.001)
        await asyncio.sleep(.005)
        status = history.status("owner")
        assert status["state"] == "retrying" and status["pending"] == 1
        pending = await history.read_get(state.room.id, "owner")
        assert pending["summary"]["p50_ms"] == 100
        assert pending["saved_at"] is None
        assert await history.flush(2)
        report = await history.read_get(state.room.id, "owner")
        assert report["persistence"]["state"] == "saved"
        assert report["summary"]["p50_ms"] == 100 and len(attempts) == 3
        assert await history.close()
    asyncio.run(run())


def test_locked_database_does_not_block_event_loop_and_recovers(tmp_path):
    async def run():
        _, state, history = setup(tmp_path)
        await history.start()
        blocker = sqlite3.connect(history.path)
        blocker.execute("BEGIN EXCLUSIVE")
        history.enqueue(state, "completed")
        ticks = 0
        until = time.monotonic()+2
        while time.monotonic() < until and history.status("owner")["state"] != "retrying":
            await asyncio.sleep(.005)
            ticks += 1
        assert ticks > 10  # SQLite busy wait ran in a thread, not this audio/event loop.
        assert history.status("owner")["state"] == "retrying"
        blocker.rollback()
        blocker.close()
        assert await history.flush(2)
        assert (await history.read_get(state.room.id, "owner"))["status"] == "completed"
        await history.close()
    asyncio.run(run())


def test_final_snapshot_supersedes_in_flight_checkpoint(tmp_path, monkeypatch):
    async def run():
        _, state, history = setup(tmp_path)
        started, release = threading.Event(), threading.Event()
        original = history._write
        def slow(snapshot):
            if not started.is_set():
                started.set()
                assert release.wait(3)
            original(snapshot)
        monkeypatch.setattr(history, "_write", slow)
        await history.start()
        sample(state, 100)
        history.enqueue(state)
        while not started.is_set():
            await asyncio.sleep(.001)
        sample(state, 300)
        history.enqueue(state, "completed")
        release.set()
        assert await history.flush(2)
        saved = await history.read_get(state.room.id, "owner")
        assert saved["status"] == "completed" and saved["summary"]["sample_count"] == 2
        assert history.status("owner")["pending"] == 0
        await history.close()
    asyncio.run(run())


def test_queue_is_bounded_and_failure_status_is_account_private(tmp_path):
    async def run():
        store, state, history = setup(tmp_path)
        history.max_pending = 1
        other = store.create_room("Another account")
        other.performance_owners["other-listener"] = "other-owner"
        assert history.enqueue(state, "completed")
        assert history.enqueue(state, "completed")  # Coalesce, not a second queue item.
        assert not history.enqueue(other, "completed")
        assert history.status("other-owner")["state"] == "unavailable"
        assert history.status("stranger")["error"] is None
        assert history.status("stranger")["pending"] == 0
        await history.start()
        assert await history.flush(2)
        assert history.enqueue(other, "completed")
        assert await history.flush(2)
        assert history.status("other-owner")["state"] == "saved"
        await history.close()
    asyncio.run(run())


def test_shutdown_is_bounded_when_storage_stays_unavailable(tmp_path, monkeypatch):
    async def run():
        _, state, history = setup(tmp_path)
        await history.start()
        def fail(snapshot):
            raise OSError("test disk full")
        monkeypatch.setattr(history, "_write", fail)
        history.enqueue(state, "completed")
        start = time.monotonic()
        assert not await history.close(timeout=.1)
        assert time.monotonic()-start < 1
        assert history.status("owner")["pending"] == 1
    asyncio.run(run())


def test_storage_failure_does_not_break_join_leave_or_leak_report(site, monkeypatch):
    app, client = site
    history = app.state.performance_history
    original = history._write
    def fail(snapshot):
        raise sqlite3.OperationalError("test lock")
    monkeypatch.setattr(history, "_write", fail)
    code, member, _ = joined(site)
    report_id = app.state.store.room(code).room.id
    report = client.get('/api/account/call-performance')
    assert report.status_code == 200 and report.json()['view'] == 'live'
    assert leave(client, code, member).status_code == 200
    saved = client.get('/api/account/call-performance').json()
    assert saved['status'] == 'completed'
    assert saved['persistence']['state'] in ('pending', 'retrying')
    identity(site, 'stranger')
    assert client.get('/api/account/performance-history').json()['reports'] == []
    assert client.get('/api/account/performance-history/'+report_id).status_code == 404
    monkeypatch.setattr(history, '_write', original)
    assert client.portal.call(history.flush)


def test_reader_failure_is_reported_instead_of_empty_history(site, monkeypatch):
    app, client = site
    code, member, _ = joined(site)
    leave(client, code, member)
    history = app.state.performance_history
    assert client.portal.call(history.flush)
    def fail(principal):
        raise sqlite3.OperationalError("test read error")
    monkeypatch.setattr(history, 'list', fail)
    listed = client.get('/api/account/performance-history').json()
    assert listed['persistence']['state'] == 'unavailable'
    assert client.get('/api/account/call-performance').status_code == 503


@pytest.mark.parametrize('operation', ['get', 'list'])
def test_read_overlapping_completed_commit_never_returns_old_active_report(tmp_path, monkeypatch, operation):
    async def run():
        _, state, history = setup(tmp_path)
        await history.start()
        sample(state)
        history.enqueue(state, 'active')
        assert await history.flush(2)
        old_stamp = history.status('owner')['last_saved_at']
        entered, release = threading.Event(), threading.Event()
        original = getattr(history, operation)
        reads = 0
        def delayed(*args):
            nonlocal reads
            value = original(*args)
            reads += 1
            if reads == 1:
                # This completed DB read has the OLD active snapshot. Hold it
                # until the writer commits final data and removes pending state.
                entered.set()
                assert release.wait(3)
            return value
        monkeypatch.setattr(history, operation, delayed)
        reading = asyncio.create_task(history.read_get(state.room.id, 'owner') if operation == 'get'
                                      else history.read_list('owner'))
        while not entered.is_set():
            await asyncio.sleep(.001)
        sample(state, 300)
        history.enqueue(state, 'completed')
        assert await history.flush(2)
        final_stamp = history.status('owner')['last_saved_at']
        assert final_stamp >= old_stamp and not history._pending
        release.set()
        result = await reading
        row = result if operation == 'get' else result[0]
        assert row['status'] == 'completed'
        assert row['saved_at'] == final_stamp
        assert history.status('owner')['last_saved_at'] == final_stamp
        assert reads == 2
        if operation == 'get':
            assert row['summary']['sample_count'] == 2
        await history.close()
    asyncio.run(run())
