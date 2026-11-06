"""Account-scoped timing history. Never stores transcripts, audio or voice profiles."""
from __future__ import annotations

import hashlib
import asyncio
import copy
import json
import logging
import sqlite3
import time
from collections import OrderedDict
from contextlib import contextmanager
from datetime import UTC, datetime

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .performance import performance_snapshot

logger = logging.getLogger(__name__)


def principal_key(issuer: str, subject: str) -> str:
    # Stable across sign-ins; email addresses and session cookies are not archive keys.
    return hashlib.sha256((issuer + "\0" + subject).encode()).hexdigest()


class ConnectionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    measured_at: datetime
    receiving_tracks: int = Field(ge=0, le=10000)
    network_rtt_ms: float | None = Field(default=None, ge=0, le=600000)
    jitter_ms: float | None = Field(default=None, ge=0, le=600000)
    jitter_buffer_ms: float | None = Field(default=None, ge=0, le=600000)
    packet_loss_percent: float | None = Field(default=None, ge=0, le=100)
    packets_received: int | None = Field(default=None, ge=0, le=2**53)
    packets_lost: int | None = Field(default=None, ge=0, le=2**53)


class PerformanceHistory:
    retention_days = 90
    max_reports = 500

    def __init__(self, settings, listener_metrics):
        self.path = settings.usage_db_path.with_name("performance.sqlite3")
        self.listener_metrics = listener_metrics
        self._pending = OrderedDict()
        self._writer = None
        self._wake = asyncio.Event()
        self._initialized = False
        self._closing = False
        self._last_saved = {}
        self._ended_at = {}
        self._warnings = {}
        self._read_failed = set()
        self._sequence = 0
        self._commit_generation = 0
        self.max_pending = 128
        self.retry_base_seconds = .5
        self.retry_max_seconds = 30

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # A busy database must not stall shutdown or hold a worker indefinitely.
        db = sqlite3.connect(self.path, timeout=.25)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.executescript("""
            CREATE TABLE IF NOT EXISTS reports(
                id TEXT PRIMARY KEY, code TEXT NOT NULL, title TEXT NOT NULL,
                started_at TEXT NOT NULL, saved_at TEXT NOT NULL, ended_at TEXT,
                status TEXT NOT NULL, updated REAL NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS readers(
                report_id TEXT REFERENCES reports(id) ON DELETE CASCADE,
                participant_id TEXT, principal TEXT NOT NULL,
                PRIMARY KEY(report_id, participant_id));
            CREATE INDEX IF NOT EXISTS readers_principal ON readers(principal, report_id);
            CREATE TABLE IF NOT EXISTS connections(
                report_id TEXT REFERENCES reports(id) ON DELETE CASCADE,
                principal TEXT, body TEXT NOT NULL, PRIMARY KEY(report_id, principal));
            """)
            with db:
                yield db
        finally:
            db.close()

    def initialize(self):
        # Previous process cannot still own a live room (the API has one worker).
        with self.connect() as db:
            db.execute("UPDATE reports SET status='interrupted' WHERE status='active'")
            self.prune(db)

    def prune(self, db):
        db.execute("DELETE FROM reports WHERE updated < ?", (time.time()-self.retention_days*86400,))
        db.execute("""DELETE FROM reports WHERE status != 'active' AND id NOT IN
                   (SELECT id FROM reports ORDER BY updated DESC LIMIT ?)""", (self.max_reports,))

    def save(self, state, status="active"):
        """Synchronous storage helper for offline fixtures. Runtime uses enqueue()."""
        snapshot = self.capture(state, status)
        if snapshot:
            self._write(snapshot)

    def capture(self, state, status="active"):
        """Copy on the event loop; the disk worker never touches mutable room state."""
        if not state.performance_owners:
            return
        stamp = datetime.now(UTC).isoformat()
        if status == "completed":
            ended_at = self._ended_at.setdefault(state.room.id, stamp)
            while len(self._ended_at) > self.max_reports:
                self._ended_at.pop(next(iter(self._ended_at)))
        else:
            self._ended_at.pop(state.room.id, None)
            ended_at = None
        body = performance_snapshot(state)
        body["receiver_audio"] = self.listener_metrics.report(state.room.code)
        turn_latency = getattr(self.listener_metrics.store, "turn_latency", None)
        if turn_latency:
            if status in ("completed", "interrupted"):
                turn_latency.finalize_room(state.room.code)
            body["turn_latency"] = turn_latency.report(state.room.code)
        return {"id":state.room.id, "code":state.room.code, "title":state.room.title,
                "started_at":state.room.created_at.isoformat(), "saved_at":stamp,
                "ended_at":ended_at, "status":status,
                "updated":time.time(), "body":json.dumps(body, allow_nan=False),
                "readers":dict(state.performance_owners), "connections":{}}

    def _write(self, snapshot):
        with self.connect() as db:
            db.execute("""INSERT INTO reports VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET saved_at=excluded.saved_at, ended_at=excluded.ended_at,
                status=excluded.status, updated=excluded.updated, body=excluded.body""",
                tuple(snapshot[key] for key in ("id", "code", "title", "started_at", "saved_at", "ended_at", "status", "updated", "body")))
            db.executemany("INSERT OR IGNORE INTO readers VALUES(?,?,?)",
                [(snapshot["id"], pid, principal) for pid, principal in snapshot["readers"].items()])
            for principal, body in snapshot["connections"].items():
                db.execute("INSERT OR REPLACE INTO connections VALUES(?,?,?)",
                           (snapshot["id"], principal, json.dumps(body, allow_nan=False)))
            self.prune(db)

    def enqueue(self, state, status="active"):
        try:
            snapshot = self.capture(state, status)
        except Exception:
            # Optional reporting must never prevent joining, leaving or cleanup.
            self._warn(state.performance_owners.values(), "Report preparation failed. The meeting can continue; saving will retry.")
            logger.warning("Performance snapshot preparation failed")
            return False
        if not snapshot:
            return True
        previous = self._pending.get(snapshot["id"])
        if previous is None and len(self._pending) >= self.max_pending:
            self._warn(snapshot["readers"].values(), "Report saving is busy. This report is not saved yet.")
            logger.warning("Performance snapshot queue is full")
            return False
        self._sequence += 1
        snapshot.update(version=self._sequence, attempts=previous["attempts"] if previous else 0,
                        retry_at=previous["retry_at"] if previous else 0)
        if previous:
            snapshot["connections"] = previous["connections"].copy()
        self._pending[snapshot["id"]] = snapshot
        self._wake.set()
        return True

    def _warn(self, principals, message):
        for principal in principals:
            self._warnings[principal] = message
        # Bound failure metadata as well as the snapshot queue.
        while len(self._warnings) > 1024:
            self._warnings.pop(next(iter(self._warnings)))

    def status(self, principal, report_id=None):
        pending = [row for row in self._pending.values() if principal in row["readers"].values()
                   and (report_id is None or row["id"] == report_id)]
        saved = [stamp for key, stamp in self._last_saved.items()
                 if key[1] == principal and (report_id is None or key[0] == report_id)]
        message = self._warnings.get(principal)
        if principal in self._read_failed:
            message = "Saved reports could not be read. Live measurements remain available; try again shortly."
        retrying = any(row["attempts"] for row in pending)
        return {"state": "retrying" if retrying else "unavailable" if message else "pending" if pending else "saved",
                "last_saved_at": max(saved) if saved else None, "pending":len(pending),
                "error":message or ("Report saving is retrying. Keep the app server running until it is saved." if retrying else None)}

    async def start(self):
        if self._writer is None or self._writer.done():
            self._closing = False
            try:
                await asyncio.to_thread(self.initialize)
                self._initialized = True
            except (sqlite3.Error, OSError):
                logger.warning("Performance history initialization failed; writes will retry")
            self._writer = asyncio.create_task(self._run(), name="performance-history-writer")

    async def _run(self):
        while not self._closing:
            self._wake.clear()
            ready = next((row for row in self._pending.values() if row["retry_at"] <= time.monotonic()), None)
            if ready is None:
                delay = min((max(.01, row["retry_at"]-time.monotonic()) for row in self._pending.values()), default=30)
                try:
                    await asyncio.wait_for(self._wake.wait(), delay)
                except TimeoutError:
                    pass
                continue
            # Freeze the work item; a newer checkpoint may arrive during this write.
            snapshot = copy.deepcopy(ready)
            try:
                if not self._initialized:
                    await asyncio.to_thread(self.initialize)
                    self._initialized = True
                operation = asyncio.create_task(asyncio.to_thread(self._write, snapshot))
                try:
                    await asyncio.shield(operation)
                except asyncio.CancelledError:
                    # Never start another write while an abandoned thread still owns one.
                    await operation
                    raise
            except asyncio.CancelledError:
                raise
            except Exception:
                current = self._pending.get(snapshot["id"])
                if current:
                    current["attempts"] += 1
                    current["retry_at"] = time.monotonic()+min(self.retry_max_seconds,
                        self.retry_base_seconds*2**min(current["attempts"]-1, 10))
                self._warn(snapshot["readers"].values(), "Report saving failed and is retrying. The meeting can continue.")
                logger.warning("Performance report write failed; retry scheduled")
            else:
                # Readers can finish a transaction begun before this commit.
                # Advance before removing pending data so they can detect that race.
                self._commit_generation += 1
                for principal in snapshot["readers"].values():
                    self._last_saved[(snapshot["id"], principal)] = snapshot["saved_at"]
                    self._warnings.pop(principal, None)
                while len(self._last_saved) > 2048:
                    self._last_saved.pop(next(iter(self._last_saved)))
                current = self._pending.get(snapshot["id"])
                if current and current["version"] == snapshot["version"]:
                    self._pending.pop(snapshot["id"])
                elif current:
                    current["attempts"], current["retry_at"] = 0, 0

    async def flush(self, timeout=3):
        self._wake.set()
        deadline = time.monotonic()+timeout
        while self._pending and time.monotonic() < deadline:
            await asyncio.sleep(.01)
        return not self._pending

    async def close(self, timeout=3):
        saved = await self.flush(timeout)
        self._closing = True
        if self._writer:
            self._writer.cancel()
            await asyncio.gather(self._writer, return_exceptions=True)
            self._writer = None
        if not saved:
            logger.warning("Unsaved performance reports remain at shutdown")
        return saved

    @staticmethod
    def metadata(row):
        return {"report_id": row["id"], "room_code": row["code"], "title": row["title"],
                "started_at": row["started_at"], "saved_at": row["saved_at"],
                "ended_at": row["ended_at"], "status": row["status"]}

    def list(self, principal):
        with self.connect() as db:
            self.prune(db)
            rows = db.execute("""SELECT * FROM reports r WHERE EXISTS
                (SELECT 1 FROM readers a WHERE a.report_id=r.id AND a.principal=?)
                ORDER BY r.updated DESC LIMIT 100""", (principal,)).fetchall()
            return [self.metadata(row) for row in rows]

    def get(self, report_id, principal):
        with self.connect() as db:
            row = db.execute("""SELECT * FROM reports r WHERE id=? AND updated>=? AND EXISTS
                (SELECT 1 FROM readers a WHERE a.report_id=r.id AND a.principal=?)""",
                (report_id, time.time()-self.retention_days*86400, principal)).fetchone()
            if not row:
                raise HTTPException(404, "This meeting report is unavailable for your account")
            ids = [r[0] for r in db.execute("SELECT participant_id FROM readers WHERE report_id=? AND principal=?",
                                           (report_id, principal))]
            connection = db.execute("SELECT body FROM connections WHERE report_id=? AND principal=?",
                                    (report_id, principal)).fetchone()
        body = json.loads(row["body"])
        self._filter_listeners(body, ids)
        return {**body, **self.metadata(row), "view": "saved", "participant_ids": ids,
                "connection": json.loads(connection[0]) if connection else None}

    @staticmethod
    def _filter_listeners(body, ids):
        # Both deliberate probes and conversation measurements belong to the listener.
        for field in ("receiver_audio", "turn_latency"):
            receiver = body.get(field)
            if receiver:
                receiver["samples"] = [s for s in receiver["samples"] if s["listener_id"] in ids]
                receiver.pop("summary", None)

    def _pending_report(self, report_id, principal):
        row = self._pending.get(report_id)
        if not row or principal not in row["readers"].values():
            return None
        ids = [pid for pid, owner in row["readers"].items() if owner == principal]
        body = json.loads(row["body"])
        self._filter_listeners(body, ids)
        metadata = self.metadata(row)
        # The capture time is not a successful database commit.
        metadata["saved_at"] = self._last_saved.get((report_id, principal))
        return {**body, **metadata, "view":"saved", "participant_ids":ids,
                "connection":copy.deepcopy(row["connections"].get(principal)),
                "persistence":self.status(principal, report_id)}

    async def _consistent_read(self, operation, *args):
        # The only runtime writer is this instance. If it commits while a threaded
        # read is in flight, repeat rather than return the older transaction after
        # the pending snapshot has already been removed. Bound retries so continuous
        # writes cannot hold an HTTP request forever; an explicit retry is truthful.
        for _ in range(3):
            generation = self._commit_generation
            try:
                value = await asyncio.to_thread(operation, *args)
            except HTTPException:
                if generation != self._commit_generation:
                    continue
                raise
            if generation == self._commit_generation:
                return value
        raise sqlite3.OperationalError("Performance history changed during repeated reads")

    def _remember_saved(self, report_id, principal, stamp):
        key = (report_id, principal)
        previous = self._last_saved.get(key)
        if previous is None or stamp > previous:
            self._last_saved[key] = stamp

    async def read_list(self, principal):
        try:
            rows = await self._consistent_read(self.list, principal)
            self._read_failed.discard(principal)
        except (sqlite3.Error, OSError):
            rows = []
            self._read_failed.add(principal)
        by_id = {row["report_id"]:row for row in rows}
        for row in rows:
            self._remember_saved(row["report_id"], principal, row["saved_at"])
        for row in list(self._pending.values()):
            if principal in row["readers"].values():
                meta = self.metadata(row)
                meta["saved_at"] = self._last_saved.get((row["id"],principal))
                by_id[row["id"]] = meta
        rows = sorted(by_id.values(), key=lambda row:row["started_at"], reverse=True)[:100]
        return [{**row,"persistence":self.status(principal,row["report_id"])} for row in rows]

    async def read_get(self, report_id, principal):
        try:
            report = await self._consistent_read(self.get, report_id, principal)
            self._read_failed.discard(principal)
        except HTTPException as exc:
            pending = self._pending_report(report_id, principal)
            if exc.status_code == 404 and pending:
                return pending
            raise
        except (sqlite3.Error, OSError):
            self._read_failed.add(principal)
            # May have been queued while the read was waiting for the disk.
            pending = self._pending_report(report_id, principal)
            if pending:
                return pending
            raise HTTPException(503, "Saved reports are temporarily unavailable. Try again shortly.") from None
        self._remember_saved(report_id, principal, report["saved_at"])
        pending = self._pending_report(report_id, principal)
        if pending:
            pending["connection"] = pending["connection"] or report.get("connection")
            return pending
        return {**report,"persistence":self.status(principal,report_id)}

    async def read_latest(self, principal):
        rows = await self.read_list(principal)
        if rows:
            return await self.read_get(rows[0]["report_id"], principal)
        if principal in self._read_failed:
            raise HTTPException(503, "Saved reports are temporarily unavailable. Try again shortly.")
        return None

    def enqueue_connection(self, state, participant_id, principal, body):
        if not principal or state.performance_owners.get(participant_id) != principal:
            raise HTTPException(403, "Connection metrics belong to your own meeting membership")
        # Capture the current report too, so a connection cannot outlive its reader grant.
        if not self.enqueue(state):
            return False
        row = self._pending[state.room.id]
        row["connections"][principal] = {**body.model_dump(mode="json"),
            "received_at":datetime.now(UTC).isoformat(), "client_reported":True}
        return True

    def latest(self, principal):
        rows = self.list(principal)
        return self.get(rows[0]["report_id"], principal) if rows else None

    def save_connection(self, state, participant_id, principal, body):
        if not principal or state.performance_owners.get(participant_id) != principal:
            raise HTTPException(403, "Connection metrics belong to your own meeting membership")
        with self.connect() as db:
            if not db.execute("SELECT 1 FROM readers WHERE report_id=? AND principal=?",
                              (state.room.id, principal)).fetchone():
                raise HTTPException(409, "Meeting history is not available yet")
            db.execute("INSERT OR REPLACE INTO connections VALUES(?,?,?)",
                (state.room.id, principal, json.dumps({**body.model_dump(mode="json"),
                    "received_at": datetime.now(UTC).isoformat(), "client_reported": True}, allow_nan=False)))
