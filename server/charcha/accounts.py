"""Browser sign-in through a confidential OIDC application. Every grant is single use."""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
import sqlite3
import time
from dataclasses import dataclass
from urllib.parse import urlencode, urlsplit

import httpx
import jwt
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from .store import token_digest
from .services.host_budget import BudgetChange
from .reviewer_access import ReviewerAccess

COOKIE = "charcha_session"
STATE_COOKIE = "charcha_login"
MFA_CLAIM = "https://charcha.app/mfa"
EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
LOGOUT = "/api/account/logout"
BACKCHANNEL = "/api/account/backchannel-logout"
LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout"
PUBLIC = {"/api/health", "/api/account", "/api/account/login", "/api/account/callback", LOGOUT, BACKCHANNEL}


@dataclass(frozen=True)
class Account:
    key: str
    subject: str
    email: str
    admin: bool
    expires: float
    provider_sid: str | None = None


class HostPolicy(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class Accounts:
    def __init__(self, settings, store):
        self.settings, self.store = settings, store
        self.origin = settings.charcha_public_origin.rstrip("/")
        self.domain = settings.charcha_auth_domain
        self.self_hosted = settings.charcha_identity_provider == "keycloak"
        self.issuer = (
            settings.charcha_oidc_issuer.rstrip("/")
            if self.self_hosted
            else "https://" + self.domain + "/"
        )
        self.authorization_url = self.issuer + (
            "/protocol/openid-connect/auth" if self.self_hosted else "authorize"
        )
        self.token_url = self.issuer + (
            "/protocol/openid-connect/token" if self.self_hosted else "oauth/token"
        )
        self.jwks_url = self.issuer + (
            "/protocol/openid-connect/certs" if self.self_hosted else ".well-known/jwks.json"
        )
        self.sessions: dict[str, Account] = {}
        self.flows: dict[str, tuple] = {}
        self.exchanging: set[str] = set()
        self.ended_sessions: dict[str, float] = {}
        self.signing_keys: dict[str, dict] = {}
        self.keys_valid_until = 0.0
        self.db = settings.usage_db_path.with_name("accounts.sqlite3")
        self.reviewers = ReviewerAccess(self.db, self.issuer,
            auto_domains=settings.reviewer_auto_domains,
            auto_hours=settings.reviewer_auto_access_hours,
            auto_shared=settings.reviewer_auto_shared_resources)

    @property
    def configured(self):
        origin = urlsplit(self.origin)
        issuer = urlsplit(self.issuer)
        trusted_issuer = (
            (
                bool(issuer.hostname)
                and not issuer.username
                and not issuer.password
                and not issuer.query
                and not issuer.fragment
                and bool(re.fullmatch(r"(?:/[A-Za-z0-9_-]+)*/realms/[A-Za-z0-9_-]+", issuer.path))
                and (
                    issuer.scheme == "https"
                    or (issuer.scheme == "http" and issuer.hostname in {"localhost", "127.0.0.1"})
                )
            )
            if self.self_hosted
            else bool(re.fullmatch(r"[A-Za-z0-9.-]+", self.domain))
        )
        return bool(
            trusted_issuer
            and self.settings.charcha_auth_client_id
            and self.settings.charcha_auth_client_secret.get_secret_value()
            and not origin.path
            and not origin.query
            and not origin.fragment
            and not origin.username
            and origin.hostname
            and (
                origin.scheme == "https"
                or (origin.scheme == "http" and origin.hostname in ("localhost", "127.0.0.1"))
            )
        )

    def host_email(self):
        if self.db.is_file():
            with sqlite3.connect(self.db) as db:
                present = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='host_policy'").fetchone()
                row = db.execute("SELECT email FROM host_policy WHERE id=1").fetchone() if present else None
                if row:
                    return row[0]
        return self.settings.charcha_meeting_host_email.strip().casefold()

    def can_host(self, who):
        return bool(who and who.expires > time.time() and (
            who.email.casefold() == self.host_email() or self.reviewers.active(who)))

    def shared_resources_allowed(self, who):
        if not who or who.expires <= time.time():
            return False
        if who.email.casefold() == self.host_email():
            return True
        grant = self.reviewers.active(who)
        return bool(grant and grant["share_resources"])

    def set_host(self, who, email):
        email = email.strip().casefold()
        if not EMAIL.fullmatch(email):
            raise HTTPException(422, "Enter a valid host email address")
        self.db.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS host_policy(id INTEGER PRIMARY KEY, email TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS host_changes(stamp REAL, actor TEXT, email TEXT)"
            )
            db.execute("INSERT OR REPLACE INTO host_policy VALUES(1, ?)", (email,))
            db.execute("INSERT INTO host_changes VALUES(?,?,?)", (time.time(), who.subject, email))
            db.execute(
                "DELETE FROM host_changes WHERE rowid NOT IN (SELECT rowid FROM host_changes ORDER BY rowid DESC LIMIT 100)"
            )

    def current(self, request):
        key = token_digest(request.cookies.get(COOKIE, ""))
        account = self.sessions.get(key)
        return account if account and account.expires > time.time() else None

    def prune(self):
        now = time.time()
        for session in self.store.sessions.values():
            account = self.sessions.get(session.account_session or "")
            if account and account.expires <= now:
                session.expires_at = 0
        self.sessions = {k: v for k, v in self.sessions.items() if v.expires > now}
        self.flows = {k: v for k, v in self.flows.items() if v[0] > now}
        self.ended_sessions = {k: v for k, v in self.ended_sessions.items() if v > now}

    def require(self, request, *, admin=False):
        who = self.current(request)
        if not who:
            raise HTTPException(401, "Sign in to continue")
        if admin and not who.admin:
            raise HTTPException(403, "Sign in with your administrator password and second factor")
        return who

    def set_cookie(self, response, name, value, ttl):
        response.set_cookie(
            name,
            value,
            httponly=True,
            secure=self.origin.startswith("https://"),
            samesite="lax",
            max_age=ttl,
            path="/",
        )

    def logout_destination(self):
        if not self.configured:
            return "/"
        params = {"client_id": self.settings.charcha_auth_client_id}
        if self.self_hosted:
            params["post_logout_redirect_uri"] = self.origin + "/"
            return self.issuer + "/protocol/openid-connect/logout?" + urlencode(params)
        params["returnTo"] = self.origin
        return self.issuer + "v2/logout?" + urlencode(params)

    async def signed_claims(self, token, client, required):
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
            raise ValueError("Unexpected signing key")
        if time.monotonic() >= self.keys_valid_until:
            response = await client.get(self.jwks_url)
            response.raise_for_status()
            self.signing_keys = {k["kid"]: k for k in response.json()["keys"] if k.get("kty") == "RSA"}
            self.keys_valid_until = time.monotonic() + 30
        key = self.signing_keys[header["kid"]]
        return jwt.decode(token, jwt.PyJWK.from_dict(key).key, algorithms=["RS256"],
                          issuer=self.issuer, audience=self.settings.charcha_auth_client_id,
                          options={"require": required})

    async def verify_code(self, code, verifier, nonce):
        cfg = self.settings
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.post(
                    self.token_url,
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "code_verifier": verifier,
                        "client_id": cfg.charcha_auth_client_id,
                        "client_secret": cfg.charcha_auth_client_secret.get_secret_value(),
                        "redirect_uri": self.origin + "/api/account/callback",
                    },
                )
                res.raise_for_status()
                token = res.json()["id_token"]
                claims = await self.signed_claims(token, client, ["exp", "iat", "sub", "nonce", "aud", "iss"])
                if (
                    claims["nonce"] != nonce
                    or claims.get("azp", cfg.charcha_auth_client_id) != cfg.charcha_auth_client_id
                ):
                    raise ValueError("Invalid identity")
                if claims.get("email_verified") is not True or not EMAIL.fullmatch(
                    str(claims.get("email", ""))
                ):
                    raise HTTPException(
                        403, "Verify your email with the sign-in provider, then try again"
                    )
                return claims
        except HTTPException:
            raise
        except (httpx.HTTPError, ValueError, KeyError, TypeError, StopIteration, jwt.PyJWTError):
            raise HTTPException(401, "Sign-in could not be verified. Please start again.") from None

    def router(self, service):
        router = APIRouter()

        @router.get("/api/account")
        async def status(request: Request):
            who = self.current(request)
            reviewer = self.reviewers.active(who)
            return {
                "authenticated": bool(who),
                "configured": self.configured,
                "scope": token_digest(who.subject) if who else None,
                "session_scope": token_digest(who.key)[:24] if who else None,
                "email": who.email if who else None,
                "can_host": self.can_host(who),
                "reviewer": bool(reviewer),
                "reviewer_shared_allowed": self.shared_resources_allowed(who),
                "admin": bool(who and who.admin),
                "password_security_available": bool(self.self_hosted and self.configured),
            }

        @router.get("/api/account/security")
        async def account_security(request: Request):
            self.require(request)
            if not self.self_hosted or not self.configured:
                raise HTTPException(503, "Account security is managed by the sign-in provider")
            # Passwords are entered only in Keycloak, never sent to Charcha's API.
            return RedirectResponse(self.issuer + "/account/account-security/signing-in", 303)

        @router.get("/api/account/login")
        async def login(request: Request, destination: str = "/", admin: bool = False, google: bool = False):
            if not self.configured or (admin and not self.settings.charcha_admin_subject):
                raise HTTPException(503, "Sign-in is awaiting workspace configuration")
            self.store.rate_limit("sign-in", request.client.host if request.client else "", 30)
            self.prune()
            if len(self.flows) >= 2048:
                raise HTTPException(503, "Please try again shortly")
            destination = (
                destination
                if re.fullmatch(r"/[a-zA-Z0-9/-]{0,120}", destination)
                and not destination.startswith("//")
                else "/"
            )
            state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
            self.flows[token_digest(state)] = (
                time.time() + 300,
                nonce,
                verifier,
                destination,
                admin,
            )
            params = {
                "client_id": self.settings.charcha_auth_client_id,
                "response_type": "code",
                "redirect_uri": self.origin + "/api/account/callback",
                "scope": "openid email",
                "prompt": "login",
                "state": state,
                "nonce": nonce,
                "code_challenge_method": "S256",
                "code_challenge": base64.urlsafe_b64encode(
                    hashlib.sha256(verifier.encode()).digest()
                )
                .decode()
                .rstrip("="),
            }
            if google and self.self_hosted and not admin:
                params["kc_idp_hint"] = "google"
                params["prompt"] = "select_account"
                params["max_age"] = "0"
            if admin:
                params.update(prompt="login", max_age="0")
                if self.self_hosted:
                    params["kc_idp_hint"] = ""
                else:
                    params["connection"] = self.settings.charcha_admin_connection
            response = RedirectResponse(self.authorization_url + "?" + urlencode(params), 303)
            self.set_cookie(response, STATE_COOKIE, state, 300)
            return response

        @router.get("/api/account/callback")
        async def callback(request: Request, state: str = "", code: str = ""):
            bound = request.cookies.get(STATE_COOKIE, "")
            if not state or not secrets.compare_digest(token_digest(state), token_digest(bound)):
                raise HTTPException(401, "The sign-in request expired. Start sign-in again.")
            flow = self.flows.pop(token_digest(state), None)
            if not flow or flow[0] <= time.time() or not code:
                raise HTTPException(401, "Sign-in expired or was canceled. Start sign-in again.")
            _, nonce, verifier, dest, admin = flow
            exchange = token_digest(state)
            self.exchanging.add(exchange)
            try:
                claims = await self.verify_code(code, verifier, nonce)
                return await finish_login(request, claims, dest, admin, exchange)
            finally:
                self.exchanging.discard(exchange)

        async def finish_login(request, claims, dest, admin, exchange):
            sid = claims.get("sid")
            if self.self_hosted and (not isinstance(sid, str) or not 0 < len(sid) <= 256):
                raise HTTPException(401, "The identity provider did not supply a session. Sign in again.")
            amr = claims.get("amr", [])
            strong_admin = (
                (isinstance(amr, list) and "pwd" in amr and "otp" in amr)
                if self.self_hosted
                else (claims["sub"].startswith("auth0|") and claims.get(MFA_CLAIM) is True)
            )
            if admin and (
                claims["sub"] != self.settings.charcha_admin_subject
                or not strong_admin
                or not isinstance(claims.get("auth_time"), (int, float))
                or abs(time.time() - claims["auth_time"]) > 300
            ):
                raise HTTPException(
                    403, "Administrator identity and fresh multifactor sign-in are required"
                )
            self.prune()
            if len(self.sessions) >= 10000:
                raise HTTPException(503, "Sign-in capacity reached")
            raw = secrets.token_urlsafe(40)
            key = token_digest(raw)
            ttl = min(900 if admin else 14400, int(claims["exp"] - time.time()))
            if ttl < 1:
                raise HTTPException(401, "Sign in again")
            previous = self.current(request)
            if previous:
                await self.revoke(previous, service)
            if exchange not in self.exchanging or (sid and sid in self.ended_sessions):
                raise HTTPException(401, "This sign-in ended. Start sign-in again.")
            self.sessions[key] = Account(
                key, claims["sub"], claims["email"].casefold(), admin, time.time() + ttl, sid
            )
            # Only the signed, verified OIDC identity reaches this point. Login
            # may renew an expired domain lease; ordinary status polling cannot.
            self.reviewers.ensure_domain_access(self.sessions[key], renew=True)
            response = RedirectResponse(self.origin + "/#" + ("/admin" if admin else dest), 303)
            response.delete_cookie(STATE_COOKIE, path="/")
            self.set_cookie(response, COOKIE, raw, ttl)
            return response

        @router.post(LOGOUT)
        async def logout(request: Request):
            state = token_digest(request.cookies.get(STATE_COOKIE, ""))
            self.flows.pop(state, None)
            self.exchanging.discard(state)
            who = self.current(request)
            if who:
                await self.revoke(who, service)
            response = JSONResponse({"ok": True, "continue_url": self.logout_destination()})
            response.delete_cookie(COOKIE, path="/")
            response.delete_cookie(STATE_COOKIE, path="/")
            return response

        @router.post(BACKCHANNEL)
        async def provider_logout(logout_token: str = Form(min_length=1, max_length=16384)):
            if not self.self_hosted or not self.configured:
                raise HTTPException(404)
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    claims = await self.signed_claims(logout_token, client, ["iss", "aud", "iat", "jti", "events", "sid"])
                sid = claims["sid"]
                if ("nonce" in claims or not isinstance(claims["events"], dict)
                        or claims["events"].get(LOGOUT_EVENT) != {} or not isinstance(sid, str) or not 0 < len(sid) <= 256
                        or type(claims["iat"]) not in (int, float) or time.time() - claims["iat"] > 300):
                    raise ValueError("Invalid logout claim")
            except (httpx.HTTPError, ValueError, KeyError, TypeError, jwt.PyJWTError):
                raise HTTPException(400, "Invalid logout notification") from None
            # Only this signed provider session can be ended. Repeat deliveries are idempotent.
            self.prune()
            self.ended_sessions[sid] = time.time() + 300
            for who in list(self.sessions.values()):
                if who.provider_sid == sid and ("sub" not in claims or who.subject == claims["sub"]):
                    await self.revoke(who, service)
            return {}

        @router.get("/api/admin")
        async def overview(request: Request):
            self.require(request, admin=True)
            changes = []
            if self.db.is_file():
                with sqlite3.connect(self.db) as db:
                    present = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='host_changes'").fetchone()
                    if present:
                        changes = [
                            {"at": stamp, "email": email}
                            for stamp, email in db.execute(
                                "SELECT stamp,email FROM host_changes ORDER BY rowid DESC LIMIT 10"
                            )
                        ]
            return {
                "host_email": self.host_email(),
                "changes": changes,
                "rooms": [
                    {
                        "code": s.room.code,
                        "title": s.room.title,
                        "waiting": sum(a["status"] == "pending" for a in s.admissions.values()),
                        "participants": sum(
                            not p.is_agent and not p.is_demo for p in s.room.participants
                        ),
                    }
                    for s in self.store.rooms.values()
                    if s.expires_at > time.time()
                ],
            }

        @router.post("/api/admin/host")
        async def change_host(request: Request, policy: HostPolicy):
            who = self.require(request, admin=True)
            self.store.rate_limit("host-policy", who.subject, 10)
            self.set_host(who, policy.email)
            return {"host_email": self.host_email()}

        @router.get("/api/admin/gnani-budget")
        async def read_budget(request: Request):
            self.require(request, admin=True)
            return {"budget": service.usage.host_policy()}

        @router.post("/api/admin/gnani-budget")
        async def update_budget(request: Request, policy: BudgetChange):
            who = self.require(request, admin=True)
            self.store.rate_limit("gnani-budget", who.subject, 20)
            if not service.usage.host_policy():
                raise HTTPException(409, "A host allowance has not been configured on this server.")
            try:
                return {"budget": service.usage.change_host_budget(policy)}
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from None

        router.include_router(self.reviewers.router(self))
        return router

    async def revoke(self, who, service):
        self.sessions.pop(who.key, None)
        resources = getattr(service, "reviewer_resources", None)
        error = None
        if resources:
            try:
                await resources.clear(who.key)
            except BaseException as caught:
                error = caught
        for session in self.store.sessions.values():
            if session.account_session == who.key:
                session.expires_at = 0
        try:
            await service.prune_expired()
        except BaseException as caught:
            if error is None or (isinstance(error, Exception) and not isinstance(caught, Exception)):
                error = caught
        if error is not None:
            raise error
