"""Expiring reviewer grants, bound to verified accounts through one-use invitations.

An invitation is not an identity claim. Normal OIDC sign-in happens first; an
administrator separately decides whether that identity may host review rooms
and use the workspace's providers. Invitation plaintext is never persisted.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
from pathlib import Path
import re
import secrets
import sqlite3
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, SecretStr, field_validator

EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
MAX_ACTIVE_INVITATIONS = 1000


class ReviewerInvitation(BaseModel):
    recipient_email: str | None = Field(default=None, max_length=254)
    expires_in_hours: int = Field(default=72, ge=1, le=168)
    share_resources: bool = True

    @field_validator("recipient_email")
    @classmethod
    def recipient(cls, value):
        if value is None or not value.strip():
            return None
        value = value.strip().casefold()
        if not EMAIL.fullmatch(value):
            raise ValueError("Enter a valid recipient email")
        return value


class RedeemReviewerInvitation(BaseModel):
    invitation: SecretStr = Field(min_length=32, max_length=256)


class ReviewerAccess:
    def __init__(self, path: Path, issuer: str):
        self.path, self.issuer = path, issuer

    def principal(self, who):
        return hashlib.sha256((self.issuer + "\0" + who.subject).encode()).hexdigest()

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute("""CREATE TABLE IF NOT EXISTS reviewer_invitations(
                id TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE,
                recipient_email TEXT, issued_by TEXT NOT NULL,
                created_at REAL NOT NULL, expires_at REAL NOT NULL,
                share_resources INTEGER NOT NULL,
                redeemed_at REAL, principal TEXT, subject TEXT, email TEXT,
                revoked_at REAL, revoked_by TEXT
            )""")
            columns = {row[1] for row in db.execute("PRAGMA table_info(reviewer_invitations)")}
            if "subject" not in columns:
                db.execute("ALTER TABLE reviewer_invitations ADD COLUMN subject TEXT")
            db.execute("CREATE INDEX IF NOT EXISTS reviewer_principal ON reviewer_invitations(principal)")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def public(row, now):
        status = ("revoked" if row["revoked_at"] is not None else
                  "expired" if row["expires_at"] <= now else
                  "active" if row["redeemed_at"] is not None else "pending")
        return {"id": row["id"], "recipient_email": row["recipient_email"],
                "email": row["email"], "created_at": row["created_at"],
                "expires_at": row["expires_at"], "share_resources": bool(row["share_resources"]),
                "redeemed_at": row["redeemed_at"], "status": status}

    def active(self, who):
        if not who or who.expires <= time.time() or not self.path.is_file():
            return None
        now = time.time()
        with self.connection() as db:
            # A changed email or identity-provider subject does not inherit the grant.
            row = db.execute("""SELECT * FROM reviewer_invitations
                WHERE principal=? AND email=? AND redeemed_at IS NOT NULL
                  AND revoked_at IS NULL AND expires_at>?
                ORDER BY share_resources DESC, expires_at DESC LIMIT 1""",
                (self.principal(who), who.email.casefold(), now)).fetchone()
            return self.public(row, now) if row else None

    def create(self, who, body: ReviewerInvitation):
        now = time.time()
        raw = secrets.token_urlsafe(32)
        identifier = secrets.token_urlsafe(16)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute("""SELECT COUNT(*) FROM reviewer_invitations
                WHERE revoked_at IS NULL AND expires_at>?""", (now,)).fetchone()[0]
            if count >= MAX_ACTIVE_INVITATIONS:
                raise HTTPException(409, "Revoke unused reviewer invitations before creating another")
            # Retain recent audit metadata without retaining indefinite invitation history.
            db.execute("""DELETE FROM reviewer_invitations WHERE expires_at<?
                AND id NOT IN (SELECT id FROM reviewer_invitations ORDER BY created_at DESC LIMIT 1000)""",
                (now - 90 * 86400,))
            db.execute("""INSERT INTO reviewer_invitations
                (id,token_hash,recipient_email,issued_by,created_at,expires_at,share_resources)
                VALUES(?,?,?,?,?,?,?)""",
                (identifier, hashlib.sha256(raw.encode()).hexdigest(), body.recipient_email,
                 self.principal(who), now, now + body.expires_in_hours * 3600, int(body.share_resources)))
            row = db.execute("SELECT * FROM reviewer_invitations WHERE id=?", (identifier,)).fetchone()
            public = self.public(row, now)
        # Returned once to the administrator, never in status/list endpoints or logs.
        return {**public, "invitation": raw}

    def redeem(self, who, raw):
        now = time.time()
        digest = hashlib.sha256(raw.strip().encode()).hexdigest()
        with self.connection() as db:
            # Serialization makes one-use redemption hold across browser requests/processes.
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM reviewer_invitations WHERE token_hash=?", (digest,)).fetchone()
            if (not row or row["revoked_at"] is not None or row["expires_at"] <= now
                    or row["redeemed_at"] is not None):
                raise HTTPException(403, "This reviewer invitation is invalid, expired or already used")
            if row["recipient_email"] and row["recipient_email"] != who.email.casefold():
                raise HTTPException(403, "Sign in with the email address invited by the administrator")
            if who.expires <= now:
                raise HTTPException(401, "Sign in again to use this invitation")
            db.execute("""UPDATE reviewer_invitations SET redeemed_at=?,principal=?,subject=?,email=?
                WHERE id=? AND redeemed_at IS NULL""",
                (now, self.principal(who), who.subject, who.email.casefold(), row["id"]))
            updated = db.execute("SELECT * FROM reviewer_invitations WHERE id=?", (row["id"],)).fetchone()
            return self.public(updated, now)

    def list(self):
        if not self.path.is_file():
            return []
        now = time.time()
        with self.connection() as db:
            return [self.public(row, now) for row in db.execute(
                "SELECT * FROM reviewer_invitations ORDER BY created_at DESC LIMIT 1000")]

    def revoke(self, who, identifier):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT id,subject FROM reviewer_invitations WHERE id=?", (identifier,)).fetchone()
            if not row:
                raise HTTPException(404, "Reviewer invitation not found")
            db.execute("""UPDATE reviewer_invitations SET revoked_at=COALESCE(revoked_at,?),
                revoked_by=COALESCE(revoked_by,?) WHERE id=?""",
                (time.time(), self.principal(who), identifier))
            return row["subject"]

    def router(self, accounts):
        router = APIRouter()

        def status(who):
            grant = self.active(who)
            return {"reviewer": bool(grant), "can_host": accounts.can_host(who),
                    "reviewer_shared_allowed": accounts.shared_resources_allowed(who),
                    "expires_at": grant["expires_at"] if grant else None,
                    "grant_id": grant["id"] if grant else None}

        @router.get("/api/reviewer/access")
        async def access(request: Request):
            return status(accounts.require(request))

        @router.post("/api/reviewer/access/redeem")
        async def redeem(request: Request, body: RedeemReviewerInvitation):
            who = accounts.require(request)
            accounts.store.rate_limit("reviewer-redeem", who.subject, 10)
            self.redeem(who, body.invitation.get_secret_value())
            return status(who)

        @router.post("/api/admin/reviewer-invitations", status_code=201)
        async def invite(request: Request, body: ReviewerInvitation):
            who = accounts.require(request, admin=True)
            accounts.store.rate_limit("reviewer-invite", who.subject, 20)
            return self.create(who, body)

        @router.get("/api/admin/reviewers")
        async def reviewers(request: Request):
            accounts.require(request, admin=True)
            return {"reviewers": self.list()}

        @router.delete("/api/admin/reviewers/{identifier}")
        async def revoke(request: Request, identifier: str):
            who = accounts.require(request, admin=True)
            accounts.store.rate_limit("reviewer-revoke", who.subject, 20)
            subject = self.revoke(who, identifier)
            resources = getattr(request.app.state, "reviewer_resources", None)
            if subject and resources:
                await resources.revoke_subject(subject)
            return {"revoked": True}

        return router
