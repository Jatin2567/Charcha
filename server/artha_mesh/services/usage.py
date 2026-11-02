"""Fail-closed local credit safeguards; this ledger is not a billing statement.

UTC resource totals, bounded approval metadata/metrics and optional manual balances
enter SQLite. No conversation text, speaker identity, audio, model name, URL,
embedding or credential is stored.
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
from . import approvals

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
_approved_flow: ContextVar[str | None] = ContextVar("approved_provider_flow", default=None)


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
                approvals.create_schema(connection)
                self.initialized = True
            yield connection
        finally:
            connection.close()

    def require_live(self):
        if self.settings.mode != "live":
            raise ProviderError(f"Provider calls are disabled in {self.settings.mode} mode", False)

    def reserve(self, units: dict[str, int]) -> str | None:
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
                    flow_id = None
                    if self.settings.usage_require_flow_approval:
                        flow_id = approvals.reserve(connection, self.now(), units, expected_flow_id=_approved_flow.get())
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
                    return flow_id
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
            flow_id = self.reserve(units)
            # Stream ticker tasks inherit this binding. Expiring flow A cannot
            # silently start consuming a later flow B approved by the operator.
            flow_token = _approved_flow.set(flow_id)
            try:
                yield
            finally:
                _approved_flow.reset(flow_token)
        finally:
            slots.release()

    def snapshot(self) -> dict:
        period, reset = self._period()
        used: dict[str, int] | None = {}
        status = "demo" if self.settings.mode == "demo" else "disabled" if self.settings.mode == "transport" else "ready"
        approval = {"required": self.settings.usage_require_flow_approval,
                    "status": status if status in {"demo", "disabled"} else "unavailable",
                    "active_flow_id": None, "expires_at": None,
                    "detail": ("Transport mode relays original audio only; all speech-provider calls are disabled."
                               if self.settings.mode == "transport" else
                               "Demo makes no provider calls; live calls require explicit operator approval.")}
        programme = approvals.empty_programme(
            self.settings.usage_reported_request_rate_inr,
            stt_rate=self.settings.usage_stt_inr_per_hour,
            tts_rate=self.settings.usage_tts_inr_per_10000_characters,
        )
        if self.settings.mode == "live":
            try:
                with self.lock, self._connection() as connection:
                    used = dict(connection.execute("SELECT resource, units FROM usage WHERE period=?", (period,)))
                    approval, programme = approvals.snapshot(
                        connection, self.now(), required=self.settings.usage_require_flow_approval,
                        rate=self.settings.usage_reported_request_rate_inr,
                        stt_rate=self.settings.usage_stt_inr_per_hour,
                        tts_rate=self.settings.usage_tts_inr_per_10000_characters,
                    )
            except (OSError, sqlite3.Error):
                self.failed = True
                used, status = None, "unavailable"
                approval["status"] = "unavailable"
                approval["detail"] = "Approval storage is unavailable; provider calls are blocked."
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
            "disabled": "Transport mode makes no speech-provider calls and writes no usage ledger. These are configured live limits, not historical usage.",
            "unavailable": "Usage storage is unavailable. Live provider calls are blocked until the operator restores storage and restarts the API.",
        }[status]
        return {
            "mode": self.settings.mode,
            "period": {"date": period, "reset_at": reset},
            "enforcement": {"enabled": True, "persistent": status == "ready", "status": status, "detail": detail},
            "resources": resources,
            "approval": approval,
            "programme": programme,
            "billing": {"balance_available": False,
                        "detail": "Local reserved usage is not provider-billed usage or your remaining credit balance. LiveKit participant time/bandwidth and hosted Evon compute need limits in those provider consoles too."},
        }

    def _operator_change(self, operation: Callable, **values) -> dict | None:
        """Local CLI only; no HTTP writer exposes these operator capabilities."""
        self.require_live()
        try:
            with self.lock, self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    result = operation(connection, self.now(), **values)
                    connection.commit()
                    return result
                except BaseException:
                    connection.rollback()
                    raise
        except (OSError, sqlite3.Error):
            self.failed = True
            raise ProviderError("Operator approval storage is unavailable; no grant or balance change was saved", False) from None

    def public_snapshot(self) -> dict:
        """Expose aggregate controls while keeping financial evidence operator-local.

        The explicit opt-in is useful for a loopback development API. Production
        configuration checks reject it because this endpoint has no operator auth.
        Local CLI commands continue to use the full snapshot directly.
        """
        result = self.snapshot()
        if not self.settings.usage_show_private_balance:
            programme = result["programme"]
            programme.update(source="not_connected", unit=None, balance=None, observed_at=None)
            programme["detail"] = (
                "Private financial evidence is hidden from this usage endpoint. "
                "Use the operator CLI or explicitly configured local-only view for manual balances and dashboard deltas. "
                "Resource reservations and reference prices are not provider-billed charges."
            )
            for flow in programme["flows"]:
                for key in ("before_balance", "before_observed_at", "after_balance", "after_observed_at",
                            "balance_unit", "balance_delta", "credits_used"):
                    flow[key] = None
                flow["credits_source"] = "unknown"
        return result

    def conference_capacity(self, target_count: int, *, source_active: bool = False) -> dict:
        """Read-only admission hint; atomic reserve remains the final authority.

        Distinct output languages, rather than audience size, consume MT/TTS
        requests. No IDs, financial snapshots, credentials or provider calls.
        """
        keys = tuple(key for key, *_ in RESOURCES if key != "voice_enrollments")
        result = {"required": target_count > 0, "status": "not_required", "expires_at": None,
                  "remaining": {key: None for key in keys}}
        if target_count <= 0:
            return result
        if not self.settings.usage_require_flow_approval:
            result["status"] = "unavailable"
            return result
        snapshot = self.snapshot()
        if snapshot["enforcement"]["status"] != "ready":
            result["status"] = "unavailable"
            return result
        flows = snapshot["programme"]["flows"]
        active = next((flow for flow in flows if flow["id"] == snapshot["approval"]["active_flow_id"]), None)
        if active is None:
            latest = flows[0]["status"] if flows else None
            result["status"] = latest if latest in {"expired", "exhausted"} else "locked"
            if result["status"] in {"expired", "exhausted"}:
                result["expires_at"] = flows[0]["expires_at"]
            return result
        if active["purpose"] != "live_interpretation":
            result["status"] = "locked"
            return result
        daily = {row["key"]: row["remaining"] for row in snapshot["resources"]}
        remaining = {key: min(max(0, active["budgets"][key] - active["used"][key]), daily[key])
                     if type(daily.get(key)) is int else None for key in keys}
        result.update(expires_at=active["expires_at"], remaining=remaining)
        if any(value is None for value in remaining.values()):
            result["status"] = "unavailable"
            return result
        minimum = {"stt_seconds": 1, "stt_connections": 0 if source_active else 1,
                   "mt_requests": target_count, "mt_characters": 1,
                   "tts_requests": target_count, "tts_characters": 1}
        result["status"] = "approved" if all(remaining[key] >= amount for key, amount in minimum.items()) else "exhausted"
        return result

    def approve_flow(self, **values) -> dict:
        values.setdefault("max_seconds", self.settings.usage_approval_max_seconds)
        return self._operator_change(approvals.approve, **values)

    def inspect_flow(self, flow_id: str) -> dict:
        return self._operator_change(approvals.inspect, flow_id=flow_id)

    @contextmanager
    def bind_flow(self, flow_id: str):
        flow = self.inspect_flow(flow_id)
        if flow["status"] != "approved":
            raise ProviderError("The specified operator flow is not active; no API request was sent", False)
        token = _approved_flow.set(flow_id)
        try:
            yield
        finally:
            _approved_flow.reset(token)

    def close_flow(self, flow_id: str) -> dict:
        return self._operator_change(approvals.close, flow_id=flow_id)

    def reconcile_flow(self, **values) -> dict:
        return self._operator_change(approvals.reconcile, **values)

    def record_programme_balance(self, **values):
        self._operator_change(approvals.record_balance, **values)

    def record_flow_metrics(self, flow_id: str, metrics: dict) -> dict:
        return self._operator_change(approvals.record_metrics, flow_id=flow_id, metrics=metrics)

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
