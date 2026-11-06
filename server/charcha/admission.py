"""Room codes identify a meeting. Only the room's host can admit another account."""

from __future__ import annotations

import secrets
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel


class Decision(BaseModel):
    decision: Literal["approve", "deny"]


def admission_status(state, who):
    if who.subject == state.owner:
        return "host"
    entry = state.admissions.get(who.subject)
    return entry["status"] if entry else "none"


def admission_router(store, accounts, service):
    router = APIRouter(prefix="/api/rooms/{code}/admission")

    def require_owner(state, who):
        if state.owner != who.subject:
            raise HTTPException(403, "Only the meeting host can manage requests")

    @router.get("")
    async def status(code: str, request: Request):
        return {"status": admission_status(store.room(code), accounts.require(request))}

    @router.post("")
    async def knock(code: str, request: Request):
        who, state = accounts.require(request), store.room(code)
        store.rate_limit("ask-to-join", who.subject, 20)
        status = admission_status(state, who)
        if status == "none":
            if len(state.admissions) >= 256:
                raise HTTPException(429, "The meeting waiting room is full")
            state.admissions[who.subject] = {
                "id": secrets.token_urlsafe(14),
                "email": who.email,
                "status": "pending",
            }
            status = "pending"
        return {"status": status}

    @router.post("/rejoin")
    async def rejoin(code: str, request: Request):
        who, state = accounts.require(request), store.room(code)
        store.rate_limit("replace-device", who.subject, 5)
        entry = state.admissions.get(who.subject)
        if not entry or entry["status"] != "joined":
            raise HTTPException(409, "Only an admitted guest can replace their own device")
        entry["status"] = "releasing"
        digest = store.memberships.get((state.room.code, entry["participant_id"]))
        old = store.sessions.get(digest or "")
        if old:
            old.expires_at = 0
        try:
            await service.prune_expired()
        finally:
            # Re-entry requires a new decision even when the old device disappeared.
            state.admissions[who.subject] = {
                "id": secrets.token_urlsafe(14),
                "email": who.email,
                "status": "pending",
            }
        return {"status": "pending"}

    @router.get("/requests")
    async def requests(code: str, request: Request):
        state = store.room(code)
        require_owner(state, accounts.require(request))
        return {"requests": [a for a in state.admissions.values() if a["status"] == "pending"]}

    @router.post("/requests/{entry_id}")
    async def decide(code: str, entry_id: str, body: Decision, request: Request):
        state = store.room(code)
        require_owner(state, accounts.require(request))
        entry = next((a for a in state.admissions.values() if a["id"] == entry_id), None)
        if not entry:
            raise HTTPException(404, "Request not found")
        result = "approved" if body.decision == "approve" else "denied"
        if entry["status"] not in ("pending", result):
            raise HTTPException(409, "This request has already been decided")
        entry["status"] = result
        return {"status": result}

    return router
