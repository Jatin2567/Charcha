"""Persistent shared allowance. All writes use the usage ledger's reservation transaction."""
import json

from pydantic import BaseModel, Field

from ..errors import ProviderError
from .approvals import room_digest, speech_micro_inr

MICRO_INR = 1_000_000


class BudgetChange(BaseModel):
    limit_inr: int = Field(strict=True, ge=0, le=1_000_000)
    revision: int = Field(strict=True, ge=1)
    managed: bool = Field(default=True, strict=True)


def create_schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS host_speech_budget (
        id INTEGER PRIMARY KEY CHECK(id=1), host TEXT NOT NULL,
        ceiling INTEGER NOT NULL CHECK(ceiling>=0), used INTEGER NOT NULL CHECK(used>=0),
        revision INTEGER NOT NULL DEFAULT 1, modified_at TEXT NOT NULL)""")
    columns = {row[1] for row in db.execute("PRAGMA table_info(host_speech_budget)")}
    if "managed" not in columns:
        db.execute("ALTER TABLE host_speech_budget ADD COLUMN managed INTEGER NOT NULL DEFAULT 1")


def read(db):
    row = db.execute("SELECT host,ceiling,used,revision,modified_at,managed FROM host_speech_budget WHERE id=1").fetchone()
    if row is None:
        return None
    host, ceiling, used, revision, modified, managed = row
    return {"host_email": host, "limit_inr": ceiling // MICRO_INR, "reserved_inr": used / MICRO_INR,
            "remaining_inr": max(0, ceiling-used) / MICRO_INR, "revision": revision, "updated_at": modified,
            "managed": bool(managed)}


def activate(db, now, *, host_email, limit_inr, carry_room=None):
    """One-time operator cutover. Retries never replenish or reopen the allowance."""
    existing = read(db)
    if existing:
        if existing["host_email"] != host_email:
            raise ValueError("A different host already owns the shared allowance.")
        return existing
    if type(limit_inr) is not int or not 0 <= limit_inr <= 1_000_000:
        raise ValueError("Enter a whole-rupee limit from 0 to 1,000,000.")
    carried = 0
    if carry_room:
        digest = room_digest(carry_room)
        rows = db.execute("SELECT used FROM operator_flows WHERE room_digest=? AND purpose='live_interpretation'",
                          (digest,)).fetchall()
        if not rows:
            raise ValueError("No recorded flows found for the carry-forward meeting.")
        carried = sum(speech_micro_inr(json.loads(row[0])) for row in rows)
        db.execute("UPDATE operator_flows SET closed_at=? WHERE room_digest=? AND closed_at IS NULL",
                   (now.isoformat(), digest))
    db.execute("INSERT INTO host_speech_budget(id,host,ceiling,used,modified_at) VALUES(1,?,?,?,?)",
               (host_email, limit_inr * MICRO_INR, carried, now.isoformat()))
    return read(db)


def change(db, now, *, limit_inr, revision, managed=True):
    updated = db.execute("UPDATE host_speech_budget SET ceiling=?, managed=?, revision=revision+1, modified_at=? "
                         "WHERE id=1 AND revision=?", (limit_inr * MICRO_INR, int(managed), now.isoformat(), revision))
    if not updated.rowcount:
        raise ValueError("The spending limit changed. Reload the current limit before saving.")
    return read(db)


def reserve(db, units):
    policy = read(db)
    if policy and not policy["managed"]:
        return
    if units.get("voice_enrollments"):
        raise ProviderError("Voice enrollment requires separate permission.", False)
    cost = speech_micro_inr(units)
    # Zero-priced Evon work also stops while paused or exhausted. Concurrent room
    # requests and administrator edits serialize on this same persistent row.
    updated = db.execute("UPDATE host_speech_budget SET used=used+? "
                         "WHERE id=1 AND ceiling>used AND used+?<=ceiling", (cost, cost))
    if not updated.rowcount:
        raise ProviderError("The shared Gnani limit has been reached. Contact your workspace administrator.", False)
