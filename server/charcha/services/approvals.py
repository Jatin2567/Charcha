"""Local operator grants and manual balance evidence; never a provider client.

Only allowlisted purpose names, UUIDs, timestamps and numeric counters are stored.
Grant checks and reservations run inside the caller's SQLite write transaction.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from ..errors import ProviderError

RESOURCE_KEYS = (
    "stt_seconds", "stt_connections", "mt_requests", "mt_characters",
    "tts_requests", "tts_characters", "voice_enrollments",
)
PURPOSES = ("gnani_speech_check", "voice_clone_check", "live_interpretation")
BALANCE_UNITS = ("INR", "programme_credits")
HISTORY_LIMIT = 50
# Integer millionths of a rupee at the operator-confirmed standard speech rates:
# ₹27/hour for recognition and ₹27/10,000 characters for synthesis.
STT_MICRO_INR = 7500
TTS_MICRO_INR = 2700


def speech_micro_inr(units: dict) -> int:
    return units.get("stt_seconds", 0) * STT_MICRO_INR + units.get("tts_characters", 0) * TTS_MICRO_INR


def create_schema(connection: sqlite3.Connection):
    connection.execute(
        "CREATE TABLE IF NOT EXISTS operator_flows ("
        "id TEXT PRIMARY KEY, purpose TEXT NOT NULL, started_at TEXT NOT NULL, "
        "expires_at TEXT NOT NULL, closed_at TEXT, budgets TEXT NOT NULL, used TEXT NOT NULL, "
        "balance_unit TEXT, before_balance REAL, before_observed_at TEXT, "
        "after_balance REAL, after_observed_at TEXT)"
    )
    columns = {row[1] for row in connection.execute("PRAGMA table_info(operator_flows)")}
    if "metrics" not in columns:
        connection.execute("ALTER TABLE operator_flows ADD COLUMN metrics TEXT NOT NULL DEFAULT '{}'")
    if "room_digest" not in columns:
        connection.execute("ALTER TABLE operator_flows ADD COLUMN room_digest TEXT")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS programme_balance ("
        "id INTEGER PRIMARY KEY CHECK(id=1), balance REAL NOT NULL, unit TEXT NOT NULL, "
        "observed_at TEXT NOT NULL, source TEXT NOT NULL)"
    )


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("A timezone-aware timestamp is required")
    return value.astimezone(UTC)


def timestamp(value: str | datetime, now: datetime) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
        result = utc(parsed)
    except (TypeError, ValueError, AttributeError):
        raise ValueError("A valid timezone-aware observation timestamp is required") from None
    if result > utc(now):
        raise ValueError("Observation timestamps cannot be in the future")
    return result.isoformat()


def balance_value(value: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("Balance must be a finite nonnegative number")
    return float(value)


def validate_budgets(budgets: dict[str, int]) -> dict[str, int]:
    if not isinstance(budgets, dict) or any(key not in RESOURCE_KEYS or type(value) is not int or value < 0
                                           for key, value in budgets.items()):
        raise ValueError("Flow budgets must be nonnegative integers using the seven resource names")
    result = {key: budgets.get(key, 0) for key in RESOURCE_KEYS}
    if not any(result.values()):
        raise ValueError("A flow requires at least one positive resource budget")
    return result


def room_digest(code: str) -> str:
    if not isinstance(code, str) or not re.fullmatch(r"[0-9a-fA-F]{12}", code):
        raise ValueError("Use the 12 hexadecimal characters from the meeting invitation.")
    return hashlib.sha256(code.lower().encode("ascii")).hexdigest()


def matches_room(flow: dict, code: str | None, require_scope: bool) -> bool:
    digest = flow.get("room_digest")
    if code is None:
        return digest is None
    if flow["purpose"] != "live_interpretation":
        return False
    return digest == room_digest(code) if digest else not require_scope


def _row(connection: sqlite3.Connection, flow_id: str) -> dict:
    try:
        if str(UUID(flow_id)) != flow_id:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ValueError("A valid flow UUID is required") from None
    cursor = connection.execute("SELECT * FROM operator_flows WHERE id=?", (flow_id,))
    found = cursor.fetchone()
    if not found:
        raise ValueError("Flow not found in the local ledger")
    return dict(zip((column[0] for column in cursor.description), found, strict=True))


def _state(row: dict, now: datetime) -> str:
    if row["closed_at"]:
        return "closed"
    if row["expires_at"] <= utc(now).isoformat():
        return "expired"
    budgets, used = json.loads(row["budgets"]), json.loads(row["used"])
    if not any(used[key] < budget for key, budget in budgets.items()):
        return "exhausted"
    return "approved"


def _public(row: dict, now: datetime) -> dict:
    delta = None
    if row["before_balance"] is not None and row["after_balance"] is not None:
        # Decimal programme prices are displayed without binary floating point noise.
        delta = round(row["before_balance"] - row["after_balance"], 8)
    return {
        "id": row["id"], "purpose": row["purpose"], "status": _state(row, now),
        "room_digest": row["room_digest"],
        "started_at": row["started_at"], "expires_at": row["expires_at"], "closed_at": row["closed_at"],
        "budgets": json.loads(row["budgets"]), "used": json.loads(row["used"]),
        "balance_unit": row["balance_unit"], "balance_delta": delta,
        "credits_used": delta if row["balance_unit"] == "programme_credits" else None,
        "credits_source": "manual_dashboard_delta" if delta is not None else "unknown",
        "before_balance": row["before_balance"], "before_observed_at": row["before_observed_at"],
        "after_balance": row["after_balance"], "after_observed_at": row["after_observed_at"],
        "metrics": json.loads(row["metrics"]),
    }


def record_balance(connection: sqlite3.Connection, now: datetime, *, balance: float, unit: str,
                   observed_at: str | datetime, source: str = "manual_dashboard"):
    amount, observed = balance_value(balance), timestamp(observed_at, now)
    if unit not in BALANCE_UNITS or source not in ("manual_dashboard", "user_reported"):
        raise ValueError("Balance unit or evidence source is unsupported")
    existing = connection.execute("SELECT observed_at FROM programme_balance WHERE id=1").fetchone()
    if existing and observed < existing[0]:
        raise ValueError("A balance observation cannot replace a newer local observation")
    connection.execute(
        "INSERT INTO programme_balance(id,balance,unit,observed_at,source) VALUES(1,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET balance=excluded.balance,unit=excluded.unit,"
        "observed_at=excluded.observed_at,source=excluded.source", (amount, unit, observed, source),
    )


def approve(connection: sqlite3.Connection, now: datetime, *, purpose: str, seconds: int,
            budgets: dict[str, int], before_balance: float | None = None,
            balance_unit: str | None = None, before_observed_at: str | datetime | None = None,
            max_seconds: int = 300, room_code: str | None = None) -> dict:
    now = utc(now)
    normalized = validate_budgets(budgets)
    digest = room_digest(room_code) if room_code is not None else None
    if digest and purpose != "live_interpretation":
        raise ValueError("Meeting codes apply only to live interpretation.")
    if purpose not in PURPOSES or type(seconds) is not int or not 1 <= seconds <= max_seconds:
        raise ValueError(f"Use an allowlisted purpose and an expiry from 1 to {max_seconds} seconds")
    if connection.execute("SELECT 1 FROM operator_flows WHERE closed_at IS NULL AND expires_at>? LIMIT 1",
                          (now.isoformat(),)).fetchone():
        raise ValueError("Close the existing flow before approving another flow")
    before = observed = None
    if any(value is not None for value in (before_balance, balance_unit, before_observed_at)):
        if any(value is None for value in (before_balance, balance_unit, before_observed_at)):
            raise ValueError("Before balance, unit and observation timestamp must be supplied together")
        before = balance_value(before_balance)
        observed = timestamp(before_observed_at, now)
        if balance_unit not in BALANCE_UNITS:
            raise ValueError("A supported balance unit is required")
        record_balance(connection, now, balance=before, unit=balance_unit, observed_at=observed)
    flow_id = str(uuid4())
    connection.execute(
        "INSERT INTO operator_flows(id,purpose,started_at,expires_at,budgets,used,balance_unit,"
        "before_balance,before_observed_at,room_digest) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (flow_id, purpose, now.isoformat(), (now + timedelta(seconds=seconds)).isoformat(),
         json.dumps(normalized), json.dumps({key: 0 for key in RESOURCE_KEYS}), balance_unit, before, observed,
         digest),
    )
    # Expired/closed history is metadata only and bounded, including across restarts.
    connection.execute("DELETE FROM operator_flows WHERE id NOT IN "
                       "(SELECT id FROM operator_flows ORDER BY started_at DESC, rowid DESC LIMIT ?)",
                       (HISTORY_LIMIT,))
    return _public(_row(connection, flow_id), now)


def reserve(connection: sqlite3.Connection, now: datetime, units: dict[str, int],
            *, expected_flow_id: str | None = None, room_code: str | None = None,
            require_room_scope: bool = False) -> str:
    current = utc(now).isoformat()
    row_id = connection.execute(
        "SELECT id FROM operator_flows WHERE closed_at IS NULL AND expires_at>? "
        "ORDER BY started_at DESC LIMIT 1", (current,),
    ).fetchone()
    if not row_id or (expected_flow_id is not None and row_id[0] != expected_flow_id):
        raise ProviderError("Operator approval is required for this provider flow; no API request was sent", False)
    row = _row(connection, row_id[0])
    if not matches_room(row, room_code, require_room_scope):
        raise ProviderError("Operator approval for this meeting is required; no API request was sent", False)
    budgets, used = json.loads(row["budgets"]), json.loads(row["used"])
    if any(used[key] + amount > budgets[key] for key, amount in units.items()):
        raise ProviderError("Approved flow resource budget reached; request fresh operator permission before another flow", False)
    for key, amount in units.items():
        used[key] += amount
    connection.execute("UPDATE operator_flows SET used=? WHERE id=?", (json.dumps(used), row_id[0]))
    return row_id[0]


def close(connection: sqlite3.Connection, now: datetime, *, flow_id: str) -> dict:
    row = _row(connection, flow_id)
    if row["closed_at"] is None:
        connection.execute("UPDATE operator_flows SET closed_at=? WHERE id=?", (utc(now).isoformat(), flow_id))
    return _public(_row(connection, flow_id), now)


def inspect(connection: sqlite3.Connection, now: datetime, *, flow_id: str) -> dict:
    return _public(_row(connection, flow_id), now)


def record_metrics(connection: sqlite3.Connection, now: datetime, *, flow_id: str, metrics: dict) -> dict:
    numeric = {"tts_first_pcm_ms", "tts_total_ms", "stt_final_ms", "tts_audio_seconds", "reference_seconds"}
    stages = {"none", "tts", "stt", "enrollment", "configuration", "approval", "cancelled"}
    if not isinstance(metrics, dict) or any(key not in numeric | {"error_stage"} for key in metrics):
        raise ValueError("Flow metrics contain an unsupported field")
    for key, value in metrics.items():
        if key == "error_stage":
            if value not in stages:
                raise ValueError("Flow error stage is unsupported")
        elif type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1e9:
            raise ValueError("Flow metrics must be finite nonnegative numbers")
    row = _row(connection, flow_id)
    previous = json.loads(row["metrics"])
    previous.update(metrics)
    connection.execute("UPDATE operator_flows SET metrics=? WHERE id=?", (json.dumps(previous), flow_id))
    return _public(_row(connection, flow_id), now)


def reconcile(connection: sqlite3.Connection, now: datetime, *, flow_id: str, after_balance: float,
              balance_unit: str, after_observed_at: str | datetime) -> dict:
    row = _row(connection, flow_id)
    if row["before_balance"] is None or row["balance_unit"] != balance_unit:
        raise ValueError("Flow needs a before-dashboard balance in the same unit")
    if _state(row, now) not in ("closed", "expired"):
        raise ValueError("Close the flow before recording its after-dashboard balance")
    after, observed = balance_value(after_balance), timestamp(after_observed_at, now)
    completed = row["closed_at"] or row["expires_at"]
    if observed < completed or observed < row["before_observed_at"]:
        raise ValueError("After observation must follow flow completion and the before observation")
    if after > row["before_balance"]:
        raise ValueError("Balance increased; top-ups prevent attribution of a flow consumption delta")
    if row["after_balance"] is not None:
        raise ValueError("This flow already has an after-dashboard observation")
    record_balance(connection, now, balance=after, unit=balance_unit, observed_at=observed)
    connection.execute("UPDATE operator_flows SET after_balance=?,after_observed_at=? WHERE id=?",
                       (after, observed, flow_id))
    return _public(_row(connection, flow_id), now)


def snapshot(connection: sqlite3.Connection, now: datetime, *, required: bool, rate: float | None = None,
             stt_rate: float | None = None, tts_rate: float | None = None) -> tuple[dict, dict]:
    rows = connection.execute("SELECT id FROM operator_flows ORDER BY started_at DESC,rowid DESC LIMIT ?",
                              (HISTORY_LIMIT,)).fetchall()
    flows = [_public(_row(connection, row[0]), now) for row in rows]
    active = next((flow for flow in flows if flow["status"] == "approved"), None)
    approval = {
        "required": required, "status": "approved" if active else "locked",
        "active_flow_id": active["id"] if active else None,
        "expires_at": active["expires_at"] if active else None,
        "detail": ("One locally approved flow is active within its explicit time and resource budgets."
                   if active else "Provider calls require a fresh explicit operator grant for one bounded flow."),
    }
    observed = connection.execute("SELECT balance,unit,observed_at,source FROM programme_balance WHERE id=1").fetchone()
    programme = empty_programme(rate, stt_rate=stt_rate, tts_rate=tts_rate)
    programme["flows"] = flows
    if observed:
        programme.update(balance=observed[0], unit=observed[1], observed_at=observed[2], source=observed[3])
    return approval, programme


def empty_programme(rate: float | None = None, *, stt_rate: float | None = None,
                    tts_rate: float | None = None) -> dict:
    return {
        "source": "not_connected", "unit": None, "balance": None, "observed_at": None,
        "automatic_sync": False, "flows": [],
        "quoted_rate": ({"amount": rate, "currency": "INR", "unit": "request",
                         "source": "user_reported", "scope": "unconfirmed"} if rate is not None else None),
        "pricing": {"currency": "INR", "source": "user_provided_pricing_table",
                    "reference_url": "https://app.gnani.ai/voice/pricing",
                    "stt_per_hour": stt_rate, "tts_per_10000_characters": tts_rate,
                    "voice_enrollment": None, "rounding": "unconfirmed"},
        "detail": "Balances and flow deltas are manually supplied evidence, never provider-verified billing. "
                  "Other account activity or delayed charges can affect dashboard deltas. Local reservations are separate units; quoted rates are reference only.",
    }
