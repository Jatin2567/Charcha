"""Reviewer grants for trusted, verified OIDC accounts.

Exact email domains can receive expiring grants; other accounts request an
administrator decision. Neither path verifies competition-judge status.
One-use invitations remain supported, and durable denial/revocation wins over
both paths. No provider or GPU request is made by this module.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
from pathlib import Path
import re
import secrets
import sqlite3
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

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


class RequestReviewerAccess(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewerDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "deny", "revoke"]
    expires_in_hours: int = Field(default=72, ge=1, le=168)
    share_resources: bool = True


class ReviewerAccess:
    def __init__(self, path: Path, issuer: str, *, auto_domains=(), auto_hours=168, auto_shared=True):
        self.path, self.issuer = path, issuer
        self.auto_domains = tuple(auto_domains)
        self.auto_hours, self.auto_shared = auto_hours, auto_shared

    def principal(self, who):
        return hashlib.sha256((self.issuer + "\0" + who.subject).encode()).hexdigest()

    def email_key(self, email):
        return hashlib.sha256((self.issuer + "\0email\0" + email.casefold()).encode()).hexdigest()

    def eligible_domain(self, who):
        email = who.email if who else ""
        return bool(who and who.expires > time.time() and email.isascii()
                    and EMAIL.fullmatch(email) and email.rsplit("@", 1)[1].casefold() in self.auto_domains)

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
            db.execute("""CREATE TABLE IF NOT EXISTS reviewer_requests(
                id TEXT PRIMARY KEY, principal TEXT NOT NULL, subject TEXT NOT NULL,
                email TEXT NOT NULL, email_key TEXT NOT NULL, source TEXT NOT NULL,
                status TEXT NOT NULL, created_at REAL NOT NULL, reviewed_at REAL,
                expires_at REAL, share_resources INTEGER NOT NULL DEFAULT 0,
                reviewed_by TEXT, UNIQUE(principal,email))""")
            db.execute("CREATE INDEX IF NOT EXISTS reviewer_request_email ON reviewer_requests(email_key)")
            db.execute("""CREATE TABLE IF NOT EXISTS reviewer_blocks(
                principal TEXT NOT NULL, email_key TEXT NOT NULL, created_at REAL NOT NULL,
                actor TEXT NOT NULL, PRIMARY KEY(principal,email_key))""")
            db.execute("""CREATE TABLE IF NOT EXISTS reviewer_access_audit(
                id INTEGER PRIMARY KEY, request_id TEXT NOT NULL, stamp REAL NOT NULL,
                actor TEXT NOT NULL, action TEXT NOT NULL, previous_status TEXT)""")
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

    @staticmethod
    def public_request(row, now):
        state = row["status"]
        if state == "approved" and row["expires_at"] is not None and row["expires_at"] <= now:
            state = "expired"
        return {"id": row["id"], "email": row["email"], "source": row["source"],
                "status": state, "created_at": row["created_at"], "reviewed_at": row["reviewed_at"],
                "expires_at": row["expires_at"], "share_resources": bool(row["share_resources"])}

    def blocked(self, db, who):
        return db.execute("SELECT 1 FROM reviewer_blocks WHERE principal=? OR email_key=? LIMIT 1",
                          (self.principal(who), self.email_key(who.email))).fetchone() is not None

    def request_row(self, db, who):
        return db.execute("SELECT * FROM reviewer_requests WHERE principal=? AND email=?",
                          (self.principal(who), who.email.casefold())).fetchone()

    @staticmethod
    def audit(db, identifier, actor, action, previous=None):
        db.execute("INSERT INTO reviewer_access_audit(request_id,stamp,actor,action,previous_status) VALUES(?,?,?,?,?)",
                   (identifier, time.time(), actor, action, previous))

    def ensure_domain_access(self, who, *, renew=False):
        if not self.eligible_domain(who):
            return
        now = time.time()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if self.blocked(db, who):
                return
            row = self.request_row(db, who)
            if row is None:
                identifier = secrets.token_urlsafe(16)
                db.execute("""INSERT INTO reviewer_requests
                    (id,principal,subject,email,email_key,source,status,created_at,reviewed_at,expires_at,share_resources,reviewed_by)
                    VALUES(?,?,?,?,?,'domain','approved',?,?,?,?,?)""",
                    (identifier, self.principal(who), who.subject, who.email.casefold(), self.email_key(who.email),
                     now, now, now + self.auto_hours * 3600, int(self.auto_shared), "domain-policy"))
                self.audit(db, identifier, "domain-policy", "automatic-approval")
            elif (renew and row["source"] == "domain" and row["status"] == "approved"
                  and row["reviewed_by"] == "domain-policy" and row["expires_at"] <= now):
                db.execute("UPDATE reviewer_requests SET reviewed_at=?,expires_at=?,share_resources=? WHERE id=?",
                           (now, now + self.auto_hours * 3600, int(self.auto_shared), row["id"]))
                self.audit(db, row["id"], "domain-policy", "explicit-domain-renewal", "expired")

    def request_status(self, who):
        if not self.path.is_file():
            return None
        with self.connection() as db:
            row = self.request_row(db, who)
            if row:
                result = self.public_request(row, time.time())
                if self.blocked(db, who) and result["status"] not in {"denied", "revoked"}:
                    result["status"] = "revoked"
                return result
            if self.blocked(db, who):
                # Never disclose another principal's identifier, even when its
                # email block applies to this newly created OIDC identity.
                return {"id": None, "email": who.email.casefold(), "source": "request",
                        "status": "revoked", "created_at": None, "reviewed_at": None,
                        "expires_at": None, "share_resources": False}
            return None

    def request_access(self, who):
        if not who or who.expires <= time.time():
            raise HTTPException(401, "Sign in again to request reviewer access")
        self.ensure_domain_access(who, renew=True)
        now = time.time()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self.request_row(db, who)
            if self.blocked(db, who):
                raise HTTPException(403, "Reviewer access was denied or revoked. Contact the administrator.")
            if row:
                if row["status"] == "approved" and row["expires_at"] <= now:
                    db.execute("UPDATE reviewer_requests SET status='pending',reviewed_at=NULL,expires_at=NULL,share_resources=0 WHERE id=?",
                               (row["id"],))
                    self.audit(db, row["id"], self.principal(who), "request-renewal", "expired")
                return
            count = db.execute("SELECT COUNT(*) FROM reviewer_requests WHERE status='pending'").fetchone()[0]
            if count >= MAX_ACTIVE_INVITATIONS:
                raise HTTPException(409, "Reviewer request capacity reached. Contact the administrator.")
            identifier = secrets.token_urlsafe(16)
            db.execute("""INSERT INTO reviewer_requests
                (id,principal,subject,email,email_key,source,status,created_at)
                VALUES(?,?,?,?,?,'request','pending',?)""",
                (identifier,self.principal(who),who.subject,who.email.casefold(),self.email_key(who.email),now))
            self.audit(db, identifier, self.principal(who), "request")

    def active(self, who):
        if not who or who.expires <= time.time():
            return None
        self.ensure_domain_access(who)
        if not self.path.is_file():
            return None
        now = time.time()
        with self.connection() as db:
            if self.blocked(db, who):
                return None
            application = self.request_row(db, who)
            if application and application["status"] == "approved" and application["expires_at"] > now:
                if application["source"] != "domain" or application["reviewed_by"] != "domain-policy" or self.eligible_domain(who):
                    result = self.public_request(application, now)
                    result["access_source"] = "domain" if application["reviewed_by"] == "domain-policy" else "approval"
                    return result
            # A changed email or identity-provider subject does not inherit the grant.
            row = db.execute("""SELECT * FROM reviewer_invitations
                WHERE principal=? AND email=? AND redeemed_at IS NOT NULL
                  AND revoked_at IS NULL AND expires_at>?
                ORDER BY share_resources DESC, expires_at DESC LIMIT 1""",
                (self.principal(who), who.email.casefold(), now)).fetchone()
            return {**self.public(row, now), "access_source": "invitation"} if row else None

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
            if self.blocked(db, who):
                raise HTTPException(403, "Reviewer access was denied or revoked. Contact the administrator.")
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

    def list_requests(self):
        if not self.path.is_file():
            return []
        with self.connection() as db:
            return [self.public_request(row, time.time()) for row in db.execute(
                "SELECT * FROM reviewer_requests ORDER BY (status='pending') DESC,created_at DESC LIMIT 1000")]

    def block_identity(self, db, principal, email, subject, actor):
        """A durable email+subject block survives logout and OIDC re-registration."""
        now = time.time()
        email_key = self.email_key(email)
        db.execute("INSERT OR REPLACE INTO reviewer_blocks VALUES(?,?,?,?)", (principal,email_key,now,actor))
        subjects = {subject}
        for row in db.execute("SELECT id,subject,status FROM reviewer_requests WHERE principal=? OR email_key=?",
                              (principal,email_key)).fetchall():
            subjects.add(row["subject"])
            db.execute("UPDATE reviewer_requests SET status='revoked',reviewed_at=?,reviewed_by=? WHERE id=?",
                       (now,actor,row["id"]))
            self.audit(db,row["id"],actor,"revoke",row["status"])
        # Revoke redeemed invitations of this issuer/identity as well. An old
        # invitation must not resurrect access when a block is later cleared.
        for row in db.execute("SELECT * FROM reviewer_invitations WHERE (principal=? OR email=?) AND subject IS NOT NULL",
                              (principal,email.casefold())).fetchall():
            expected = hashlib.sha256((self.issuer + "\0" + row["subject"]).encode()).hexdigest()
            if row["principal"] != expected:
                continue
            subjects.add(row["subject"])
            db.execute("UPDATE reviewer_invitations SET revoked_at=COALESCE(revoked_at,?),revoked_by=COALESCE(revoked_by,?) WHERE id=?",
                       (now,actor,row["id"]))
        return subjects

    def decide(self, who, identifier, body: ReviewerDecision):
        now = time.time()
        actor = self.principal(who)
        subjects = set()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM reviewer_requests WHERE id=?", (identifier,)).fetchone()
            if not row:
                raise HTTPException(404, "Reviewer access request not found")
            if body.decision == "approve":
                db.execute("DELETE FROM reviewer_blocks WHERE principal=? OR email_key=?", (row["principal"],row["email_key"]))
                db.execute("UPDATE reviewer_requests SET status='approved',reviewed_at=?,reviewed_by=?,expires_at=?,share_resources=? WHERE id=?",
                           (now,actor,now+body.expires_in_hours*3600,int(body.share_resources),identifier))
            else:
                subjects = self.block_identity(db,row["principal"],row["email"],row["subject"],actor)
                db.execute("UPDATE reviewer_requests SET status=?,reviewed_at=?,reviewed_by=?,share_resources=0 WHERE id=?",
                           ("denied" if body.decision == "deny" else "revoked",now,actor,identifier))
            self.audit(db,identifier,actor,body.decision,row["status"])
            updated = db.execute("SELECT * FROM reviewer_requests WHERE id=?", (identifier,)).fetchone()
            return self.public_request(updated,now), subjects

    def revoke(self, who, identifier):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM reviewer_invitations WHERE id=?", (identifier,)).fetchone()
            if not row:
                raise HTTPException(404, "Reviewer invitation not found")
            db.execute("""UPDATE reviewer_invitations SET revoked_at=COALESCE(revoked_at,?),
                revoked_by=COALESCE(revoked_by,?) WHERE id=?""",
                (time.time(), self.principal(who), identifier))
            if row["subject"]:
                return self.block_identity(db,row["principal"],row["email"],row["subject"],self.principal(who))
            return set()

    def router(self, accounts):
        router = APIRouter()

        def status(who):
            grant = self.active(who)
            return {"reviewer": bool(grant), "can_host": accounts.can_host(who),
                    "reviewer_shared_allowed": accounts.shared_resources_allowed(who),
                    "expires_at": grant["expires_at"] if grant else None,
                    "grant_id": grant["id"] if grant else None,
                    "auto_domains": list(self.auto_domains),
                    "access_source": grant.get("access_source") if grant else None,
                    "request": self.request_status(who)}

        @router.get("/api/reviewer/access")
        async def access(request: Request):
            return status(accounts.require(request))

        @router.post("/api/reviewer/access/request")
        async def request_access(request: Request, body: RequestReviewerAccess | None = None):
            who = accounts.require(request)
            accounts.store.rate_limit("reviewer-request", who.subject, 10)
            self.request_access(who)
            return status(who)

        @router.get("/api/admin/reviewer-requests")
        async def requests(request: Request):
            accounts.require(request, admin=True)
            return {"requests": self.list_requests()}

        @router.post("/api/admin/reviewer-requests/{identifier}/decision")
        async def decision(request: Request, identifier: str, body: ReviewerDecision):
            who = accounts.require(request, admin=True)
            accounts.store.rate_limit("reviewer-decision", who.subject, 30)
            result, subjects = self.decide(who, identifier, body)
            resources = getattr(request.app.state, "reviewer_resources", None)
            if resources:
                # Access is already withdrawn before any asynchronous teardown.
                # Retry on this same decision remains safe after cleanup failure.
                failed = False
                for subject in subjects:
                    try:
                        await resources.revoke_subject(subject)
                    except Exception:
                        failed = True
                if failed:
                    raise HTTPException(503, "Access was withdrawn; retry the decision to finish meeting cleanup")
            return result

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
            subjects = self.revoke(who, identifier)
            resources = getattr(request.app.state, "reviewer_resources", None)
            if resources:
                failed = False
                for subject in subjects:
                    try:
                        await resources.revoke_subject(subject)
                    except Exception:
                        failed = True
                if failed:
                    raise HTTPException(503, "Access was withdrawn; retry revocation to finish meeting cleanup")
            return {"revoked": True}

        return router
