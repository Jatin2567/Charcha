"""Fail-closed local credit safeguards; this ledger is not a billing statement.

Only UTC date, resource key and reserved integer units enter SQLite. No conversation
text, speaker identity, audio, model name, URL, embedding or credential is stored.
"""
from __future__ import annotations

import asyncio
import sqlite3
import threading
from collections.abc import Callable
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta

from ..config import Settings
from ..errors import ProviderError

RESOURCES = (
    ("stt_seconds", "Speech recognition connection time", "seconds", "usage_stt_seconds_per_day"),
    ("stt_connections", "Speech recognition connection attempts", "connections", "usage_stt_connections_per_day"),
    ("mt_requests", "Translation attempts", "requests", "usage_mt_requests_per_day"),
    ("mt_characters", "Translation source characters", "characters", "usage_mt_characters_per_day"),
    ("tts_requests", "Speech synthesis attempts", "requests", "usage_tts_requests_per_day"),
    ("tts_characters", "Speech synthesis input characters", "characters", "usage_tts_characters_per_day"),
    ("voice_enrollments", "Voice enrollment attempts", "enrollments", "usage_voice_enrollments_per_day"),
)

_eligibility: ContextVar[Callable[[], None] | None] = ContextVar("provider_eligibility", default=None)


@contextmanager
def provider_eligibility(check: Callable[[], None]):
    """Recheck room delivery after admission waits, immediately before paid work.

    Context propagation keeps this independent of provider-specific method signatures
    and never stores room references in the ledger. Standalone adapter callers have
    no room context and still receive the same persistent credit guards.
    """
    token = _eligibility.set(check)
    try:
        yield
    finally:
        _eligibility.reset(token)


class UsageGuard:
    """Atomic daily reservations, shared by every paid adapter in one API process.

    SQLite transactions also protect caps across accidental extra processes sharing
    the same local file. RTC rooms still require the documented single API worker.
    Calls are never automatically retried or refunded by this guard.
    """

    def __init__(self, settings: Settings, *, now: Callable[[], datetime] | None = None):
        self.settings = settings
        self.now = now or (lambda: datetime.now(UTC))
        self.limits = {key: getattr(settings, field) for key, _, _, field in RESOURCES}
        self.path = settings.usage_db_path
        self.failed = False
        self.closed = False
        self.initialized = False
        self.lock = threading.Lock()
        self.stt_slots = asyncio.BoundedSemaphore(settings.usage_max_concurrent_stt)
        self.operation_slots = asyncio.BoundedSemaphore(settings.usage_max_concurrent_operations)
        self.waiters = 0

    def _period(self):
        current = self.now().astimezone(UTC)
        reset = datetime.combine(current.date() + timedelta(days=1), datetime.min.time(), UTC)
        return current.date().isoformat(), reset.isoformat()

    @contextmanager
    def _connection(self):
        if self.closed or self.failed:
            raise sqlite3.OperationalError("Usage ledger unavailable")
        # Reject an ephemeral SQLite database in live mode: restart must not reset caps.
        if str(self.path) == ":memory:":
            raise sqlite3.OperationalError("Persistent usage storage required")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.path), timeout=1, isolation_level=None)
        try:
            if not self.initialized:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS usage ("
                    "period TEXT NOT NULL, resource TEXT NOT NULL, units INTEGER NOT NULL CHECK(units >= 0), "
                    "PRIMARY KEY(period, resource))"
                )
                self.initialized = True
            yield connection
        finally:
            connection.close()

    def require_live(self):
        if self.settings.mode != "live":
            raise ProviderError("Provider calls are disabled in demo mode", False)

    def reserve(self, units: dict[str, int]):
        """Reserve all supplied resources together before the external operation.

        Any attempted upstream operation keeps its reservation even if it fails or
        is cancelled. That conservative accounting avoids unsafe assumptions about
        whether the provider billed a partial/failed request.
        """
        self.require_live()
        if not units or any(key not in self.limits or type(amount) is not int or amount < 0
                            for key, amount in units.items()):
            raise ProviderError("Invalid usage reservation; provider call blocked", False)
        period, _ = self._period()
        try:
            with self.lock, self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    used = dict(connection.execute("SELECT resource, units FROM usage WHERE period=?", (period,)))
                    for key, amount in units.items():
                        if used.get(key, 0) + amount > self.limits[key]:
                            label = next(label for resource, label, _, _ in RESOURCES if resource == key)
                            raise ProviderError(f"Daily credit safeguard reached: {label}. It resets at 00:00 UTC.", False)
                    for key, amount in units.items():
                        connection.execute(
                            "INSERT INTO usage(period, resource, units) VALUES(?, ?, ?) "
                            "ON CONFLICT(period, resource) DO UPDATE SET units=units+excluded.units",
                            (period, key, amount),
                        )
                    connection.commit()
                except BaseException:
                    connection.rollback()
                    raise
        except (OSError, sqlite3.Error):
            self.failed = True
            raise ProviderError("Credit safeguard storage is unavailable; provider calls are blocked. Ask the operator to restore persistent storage.", False) from None

    @asynccontextmanager
    async def operation(self, units: dict[str, int], *, stt: bool = False):
        self.require_live()
        slots = self.stt_slots if stt else self.operation_slots
        if stt:
            if slots.locked():
                raise ProviderError("Provider concurrency safeguard is busy; pause and try again", False)
            await slots.acquire()
        else:
            # A small bounded admission queue lets simultaneous language branches
            # share two vendor slots. Waiting does not reserve or retry any paid call.
            if slots.locked() and self.waiters >= self.settings.usage_max_queued_operations:
                raise ProviderError("Provider concurrency safeguard queue is full; pause and try again", False)
            self.waiters += 1
            try:
                await asyncio.wait_for(slots.acquire(), self.settings.usage_provider_admission_timeout_seconds)
            except TimeoutError:
                raise ProviderError("Provider concurrency safeguard is busy; pause and try again", False) from None
            finally:
                self.waiters -= 1
        try:
            if check := _eligibility.get():
                check()
            self.reserve(units)
            yield
        finally:
            slots.release()

    def snapshot(self) -> dict:
        period, reset = self._period()
        used: dict[str, int] | None = {}
        status = "demo" if self.settings.mode == "demo" else "ready"
        if self.settings.mode == "live":
            try:
                with self.lock, self._connection() as connection:
                    used = dict(connection.execute("SELECT resource, units FROM usage WHERE period=?", (period,)))
            except (OSError, sqlite3.Error):
                self.failed = True
                used, status = None, "unavailable"
        resources = []
        for key, label, unit, _ in RESOURCES:
            limit = self.limits[key]
            amount = used.get(key, 0) if used is not None else None
            remaining = max(0, limit - amount) if amount is not None else None
            utilization = (round(amount / limit * 100, 2) if limit else 100.0) if amount is not None else None
            state = ("unknown" if amount is None else "exhausted" if not remaining
                     else "warning" if utilization >= 80 else "available")
            resources.append({"key": key, "label": label, "unit": unit, "used": amount,
                              "limit": limit, "remaining": remaining,
                              "utilization_percent": utilization, "status": state})
        detail = {
            "ready": "Persistent application reservations are enforced before provider calls. Failed or partial attempts remain counted.",
            "demo": "Demo makes no paid provider calls and writes no usage ledger. These are configured live limits.",
            "unavailable": "Usage storage is unavailable. Live provider calls are blocked until the operator restores storage and restarts the API.",
        }[status]
        return {
            "mode": self.settings.mode,
            "period": {"date": period, "reset_at": reset},
            "enforcement": {"enabled": True, "persistent": status == "ready", "status": status, "detail": detail},
            "resources": resources,
            "billing": {"balance_available": False,
                        "detail": "Local reserved usage is not provider-billed usage or your remaining credit balance. LiveKit participant time/bandwidth and hosted Evon compute need limits in those provider consoles too."},
        }

    def close(self):
        # Connections are scoped to each transaction/read and already closed.
        self.closed = True


def provider_error(message: str, *, status: int | None = None, body: dict | None = None) -> ProviderError:
    """Classify authentication/quota denials without returning any upstream body."""
    denied_statuses = {400, 401, 402, 403, 404, 405, 413, 422, 429}
    forbidden = status in denied_statuses
    if body:
        forbidden |= any(str(body.get(key, "")) in {str(code) for code in denied_statuses}
                         for key in ("status", "status_code", "code", "error_code"))
        classification = " ".join(str(body.get(key, "")) for key in ("code", "error_code", "message", "error", "detail")).lower()
        forbidden |= any(word in classification for word in ("unauthor", "authenticat", "permission", "forbidden", "invalid api", "invalid key", "invalid_token", "api key", "quota", "credit", "billing", "insufficient balance", "insufficient funds", "rate limit", "rate_limit", "payment"))
    return ProviderError(message, not forbidden)
