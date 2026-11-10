"""Session-private reviewer providers; room snapshots never fall back to owner keys.

Only trusted server room context selects an adapter. No supplied secret is written
to SQLite, returned to the browser, or included in a room/event/report payload.
"""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urljoin, urlsplit

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from ..errors import ProviderError
from ..providers.evon import EvonTranslator
from ..providers.gnani import GnaniSpeech
from . import host_budget
from .bounded_http import MODEL_LIST_BYTES, TRANSLATION_BYTES, bounded_model_client
from .engine import InterpretationEngine
from .usage import UsageGuard, current_provider_room


class ResourceSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gnani_source: Literal["shared", "own"] = "shared"
    evon_source: Literal["shared", "own"] = "shared"
    gnani_api_key: SecretStr = SecretStr("")
    evon_base_url: str = Field(default="", max_length=500)
    evon_model: str = Field(default="", max_length=200)
    evon_api_key: SecretStr = SecretStr("")
    evon_modal_key: SecretStr = SecretStr("")
    evon_modal_secret: SecretStr = SecretStr("")
    resource_consent: bool = False


def validate_endpoint(value: str, allowed_origins: list[str]) -> str:
    """Modal public subdomains, or an explicitly operator-reviewed HTTPS origin.

    Reject IPs, userinfo, alternate ports, paths/redirect destinations and encoded
    URLs. Trusted custom origins must have public DNS and protected egress; this
    user-facing form deliberately cannot make arbitrary server-side requests.
    """
    try:
        u = urlsplit(value)
        host = u.hostname or ""
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError()
        labels = host.split(".")
        valid_dns = len(labels) >= 3 and all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", x) for x in labels)
        origin = "https://" + host
        modal = host.endswith(".modal.run") and len(labels) == 3
        if (u.scheme != "https" or u.port not in (None, 443) or not valid_dns
                or u.username or u.password or u.query or u.fragment
                or u.path not in ("", "/", "/v1", "/v1/")
                or re.search(r"[\s%\\]", value) or host.endswith((".local", ".internal", ".localhost", ".test"))
                or not (modal or origin in allowed_origins)):
            raise ValueError()
        return origin + "/v1"
    except ValueError:
        raise HTTPException(422, "Use a public HTTPS Modal endpoint, or ask the administrator to allow your trusted Evon origin. The endpoint must end in /v1.") from None


def checked_secret(secret: SecretStr) -> SecretStr:
    value = secret.get_secret_value()
    if len(value) > 4096 or any(not 33 <= ord(c) <= 126 for c in value):
        raise HTTPException(422, "Provider credentials must contain only printable characters without spaces.")
    return secret


class ReviewerEngine(InterpretationEngine):
    """Verify the requested served model, without generating translation tokens."""
    def __init__(self, settings, headers):
        super().__init__(settings, headers,
                         client=bounded_model_client(MODEL_LIST_BYTES, timeout=165))

    async def _start(self, *, warm_check=False):
        if not warm_check:
            self.state, self.started, self.duration_ms = "starting", time.monotonic(), None
        url = self.settings.evon_base_url.rstrip("/") + "/models"
        origin = urlsplit(url)
        try:
            async with asyncio.timeout(900):
                for _ in range(7):
                    response = await self.client.get(url, headers=self.headers())
                    if response.status_code == 200:
                        data = response.json()
                        if not isinstance(data, dict) or not any(
                            isinstance(row, dict) and row.get("id") == self.settings.evon_model
                            for row in data.get("data", [])
                        ):
                            raise ValueError("Requested model not served")
                        if not warm_check:
                            self.duration_ms = round((time.monotonic() - self.started) * 1000, 2)
                        self.observed_at = datetime.now(UTC).isoformat()
                        self.touch()
                        return
                    if response.status_code != 303 or not origin.hostname.endswith(".modal.run"):
                        raise ValueError("Model unavailable")
                    next_url = urljoin(url, response.headers.get("location", ""))
                    p = urlsplit(next_url)
                    if (p.scheme, p.netloc, p.path) != (origin.scheme, origin.netloc, origin.path):
                        raise ValueError("Invalid continuation")
                    url = next_url
            raise ValueError("Model unavailable")
        except asyncio.CancelledError:
            self.state = "idle"
            raise
        except Exception:
            self.state = "unavailable"
            self.observed_at = datetime.now(UTC).isoformat()
            raise ProviderError("Evon did not confirm the selected model. Check your endpoint, model name and authentication, then prepare again.", False) from None


class ScopedUsage:
    def __init__(self, guard, check):
        self.guard, self.check = guard, check

    def __getattr__(self, name):
        return getattr(self.guard, name)

    def require_live(self):
        self.check()
        self.guard.require_live()

    def reserve(self, units):
        self.check()
        return self.guard.reserve(units)

    @asynccontextmanager
    async def operation(self, *args, **kwargs):
        self.check()
        async with self.guard.operation(*args, **kwargs) as result:
            self.check()  # Authorization can change while waiting for a slot.
            yield result


@dataclass(repr=False)
class RoomResources:
    account: object
    profile: ResourceSelection
    settings: object
    speech: object
    translator: object
    own_usage: UsageGuard | None
    closed: bool = False


class ReviewerResources:
    def __init__(self, settings, store, accounts, usage, speech, translator):
        self.settings, self.store, self.accounts = settings, store, accounts
        self.shared_usage, self.shared_speech, self.shared_translator = usage, speech, translator
        self.profiles: dict[str, ResourceSelection] = {}
        self.rooms: dict[str, RoomResources] = {}
        self.service = self.lifecycle = None

    def account_valid(self, who):
        return bool(who.expires > time.time() and self.accounts.sessions.get(who.key) == who
                    and self.accounts.can_host(who))

    def valid(self, code):
        runtime = self.rooms.get(code)
        state = self.store.rooms.get(code)
        return bool(runtime and not runtime.closed and state and state.expires_at > time.time()
                    and self.account_valid(runtime.account)
                    and (not self.uses_shared(runtime.profile) or self.accounts.shared_resources_allowed(runtime.account)))

    @staticmethod
    def uses_shared(profile):
        return profile.gnani_source == "shared" or profile.evon_source == "shared"

    def check(self, code):
        if not self.valid(code):
            raise ProviderError("The reviewer resource session ended. The host must sign in and create a new meeting.", False)

    def check_provider(self, code):
        self.check(code)
        if current_provider_room() != code:
            raise ProviderError("These provider resources belong to a different meeting.", False)

    def check_room_exists(self, code):
        if code:
            state = self.store.rooms.get(code)
            if state is None or state.expires_at <= time.time():
                raise ProviderError("This meeting has ended.", False)

    def settings_for(self, code):
        runtime = self.rooms.get(code)
        return runtime.settings if runtime else self.store.settings

    def engine_for(self, code):
        self.check_room_exists(code)
        runtime = self.rooms.get(code)
        if runtime:
            self.check(code)
            return runtime.translator.engine
        return getattr(self.shared_translator, "engine", None)

    def selected(self, kind, code=None):
        code = code or current_provider_room()
        if code in self.rooms:
            self.check(code)
            return getattr(self.rooms[code], kind)
        # A removed room cannot regain owner credentials through stale tasks.
        self.check_room_exists(code)
        return self.shared_speech if kind == "speech" else self.shared_translator

    def save(self, who, body):
        if not self.account_valid(who):
            raise HTTPException(403, "An active reviewer invitation or host account is required.")
        if not body.resource_consent:
            raise HTTPException(422, "Confirm that you may use the selected resources and accept their provider charges.")
        if self.uses_shared(body) and not self.accounts.shared_resources_allowed(who):
            raise HTTPException(403, "Your invitation requires your own Gnani key and Evon endpoint.")
        old = self.profiles.get(who.key)
        body = body.model_copy(deep=True)
        for name in ("gnani_api_key", "evon_api_key", "evon_modal_key", "evon_modal_secret"):
            checked_secret(getattr(body, name))
        if body.gnani_source == "own":
            if not body.gnani_api_key.get_secret_value() and old and old.gnani_source == "own":
                body.gnani_api_key = old.gnani_api_key
            if not body.gnani_api_key.get_secret_value():
                raise HTTPException(422, "Enter your Gnani API key.")
        else:
            body.gnani_api_key = SecretStr("")
        if body.evon_source == "own":
            body.evon_base_url = validate_endpoint(body.evon_base_url, self.settings.reviewer_gpu_allowed_origins)
            if not body.evon_model.strip() or re.search(r"[\s\x00-\x1f]", body.evon_model):
                raise HTTPException(422, "Enter the exact served model name without whitespace.")
            if old and old.evon_source == "own" and old.evon_base_url == body.evon_base_url:
                for name in ("evon_api_key", "evon_modal_key", "evon_modal_secret"):
                    if not getattr(body, name).get_secret_value():
                        setattr(body, name, getattr(old, name))
            mk, ms = body.evon_modal_key.get_secret_value(), body.evon_modal_secret.get_secret_value()
            if bool(mk) != bool(ms) or (mk and not urlsplit(body.evon_base_url).hostname.endswith(".modal.run")):
                raise HTTPException(422, "Modal proxy access requires both values and a Modal endpoint.")
        else:
            body.evon_base_url = body.evon_model = ""
            body.evon_api_key = body.evon_modal_key = body.evon_modal_secret = SecretStr("")
        self.profiles[who.key] = body

    def snapshot(self, who):
        p = self.profiles.get(who.key)
        grant = self.accounts.reviewers.active(who)
        access = {"reviewer": bool(grant),
                  "can_host": self.accounts.can_host(who),
                  "reviewer_shared_allowed": self.accounts.shared_resources_allowed(who),
                  "expires_at": grant["expires_at"] if grant else None}
        profile = ({"gnani_source": p.gnani_source, "evon_source": p.evon_source,
                    "evon_base_url": p.evon_base_url, "evon_model": p.evon_model,
                    "gnani_key_set": bool(p.gnani_api_key.get_secret_value()),
                    "evon_key_set": bool(p.evon_api_key.get_secret_value()),
                    "modal_proxy_set": bool(p.evon_modal_key.get_secret_value())} if p else None)
        missing = []
        if not self.account_valid(who):
            missing.append("Your reviewer access or sign-in session has ended. Ask the administrator for access.")
        if not p:
            missing.append("Choose and save your meeting resources.")
        else:
            if self.uses_shared(p) and not access["reviewer_shared_allowed"]:
                missing.append("Shared resources are no longer authorized. Choose your own providers or ask the administrator.")
            if p.gnani_source == "shared" and not self.settings.gnani_api_key.get_secret_value():
                missing.append("Shared Gnani is not configured. Supply your own key.")
            if p.evon_source == "shared" and not (self.settings.evon_base_url and self.settings.evon_model):
                missing.append("Shared Evon is not configured. Supply your own endpoint.")
            if self.settings.mode != "live":
                missing.append("This server is in offline/original-audio mode. An administrator must enable live interpretation.")
        return {"access": access, "profile": profile, "configured": bool(p and not missing), "missing": missing}

    async def bind(self, who, state):
        if state.owner != who.subject:
            raise HTTPException(403, "Only the meeting creator may attach these resources.")
        p = self.profiles.get(who.key)
        if not p or not self.snapshot(who)["configured"] or not self.account_valid(who):
            raise HTTPException(409, "Configure your reviewer resources before creating an interpreted meeting.")
        if self.uses_shared(p) and (not self.accounts.shared_resources_allowed(who) or not self.shared_usage.host_policy()):
            raise HTTPException(409, "Shared resources are unavailable. Use your own Gnani key and Evon endpoint, or contact the administrator.")
        code = state.room.code
        p = p.model_copy(deep=True)
        cfg = self.settings.model_copy(deep=True)
        if p.gnani_source == "own":
            cfg.gnani_api_key = p.gnani_api_key
        if p.evon_source == "own":
            for name in ("evon_base_url", "evon_model", "evon_api_key", "evon_modal_key", "evon_modal_secret"):
                setattr(cfg, name, getattr(p, name))
            cfg.evon_serverless = True
        own = None
        if "own" in (p.gnani_source, p.evon_source):
            digest = hashlib.sha256((self.accounts.issuer + "\0" + who.subject).encode()).hexdigest()
            ledger = cfg.model_copy(update={"usage_db_path": cfg.usage_db_path.parent / "reviewer-usage" / (digest + ".sqlite3"),
                                           "usage_require_flow_approval": True, "usage_require_room_scope": True})
            own = UsageGuard(ledger, host_room_expiry=lambda c: self.store.rooms[c].expires_at
                             if c == code and self.valid(c) else None)
            # No invented price for reviewers' providers. Exact request/audio units
            # persist; their provider account remains the billing authority.
            def initialize(db, now):
                policy = host_budget.activate(db, now, host_email=digest, limit_inr=0)
                if policy["managed"]:
                    host_budget.change(db, now, limit_inr=0, revision=policy["revision"], managed=False)
            own._operator_change(initialize)
        speech_guard = ScopedUsage(own if p.gnani_source == "own" else self.shared_usage, lambda: self.check_provider(code))
        mt_guard = ScopedUsage(own if p.evon_source == "own" else self.shared_usage, lambda: self.check_provider(code))
        # Even shared-source reviewer adapters are scoped to the reviewer's room.
        speech = GnaniSpeech(cfg, speech_guard)
        translator = EvonTranslator(cfg, mt_guard)
        await translator.engine.aclose()
        if p.evon_source == "own":
            translator.engine = ReviewerEngine(cfg, translator._headers)
            await translator.client.aclose()
            translator.client = bounded_model_client(TRANSLATION_BYTES, timeout=cfg.provider_timeout_seconds)
        else:
            translator.engine = self.shared_translator.engine
        self.rooms[code] = RoomResources(who, p, cfg, speech, translator, own)
        state.room.engine_on_demand = cfg.evon_serverless

    async def clear(self, key):
        self.profiles.pop(key, None)
        for code, runtime in list(self.rooms.items()):
            if runtime.account.key == key:
                await self.close_room(code)

    async def revoke_subject(self, subject):
        keys = {r.account.key for r in self.rooms.values() if r.account.subject == subject}
        keys.update(k for k in self.profiles if self.accounts.sessions.get(k) and self.accounts.sessions[k].subject == subject)
        for key in keys:
            await self.clear(key)

    async def close_room(self, code):
        r = self.rooms.get(code)
        if not r or r.closed:
            return
        r.closed = True  # Blocks any new call before cancelling in-flight work.
        state = self.store.rooms.get(code)
        if state:
            state.expires_at = 0
        if self.lifecycle:
            self.lifecycle.cancel_preparation(code)
        if self.service:
            await self.service.prune_expired()
        await r.speech.aclose()
        # Shared engine belongs to the application, never an individual reviewer.
        await r.translator.client.aclose()
        if r.profile.evon_source == "own":
            await r.translator.engine.aclose()
        if r.own_usage:
            r.own_usage.close()
        self.rooms.pop(code, None)

    async def prune(self):
        for key in list(self.profiles):
            who = self.accounts.sessions.get(key)
            if not who or not self.account_valid(who):
                await self.clear(key)
        for code in list(self.rooms):
            if not self.valid(code):
                await self.close_room(code)

    async def aclose(self):
        for code in list(self.rooms):
            await self.close_room(code)
        self.profiles.clear()

    def router(self):
        router = APIRouter()

        @router.get("/api/reviewer/workspace")
        async def get_workspace(request: Request):
            return self.snapshot(self.accounts.require(request))

        @router.post("/api/reviewer/workspace")
        async def save_workspace(body: ResourceSelection, request: Request):
            who = self.accounts.require(request)
            self.store.rate_limit("reviewer-config", who.subject, 20)
            self.save(who, body)
            return self.snapshot(who)

        @router.delete("/api/reviewer/workspace")
        async def delete_workspace(request: Request):
            who = self.accounts.require(request)
            await self.clear(who.key)
            return self.snapshot(who)

        return router


class RoutedUsage:
    def __init__(self, registry):
        self.registry = registry

    def __getattr__(self, name):
        return getattr(self.registry.shared_usage, name)

    def conference_capacity(self, target_count, *, source_active=False, room_code=None):
        if room_code not in self.registry.rooms:
            return self.registry.shared_usage.conference_capacity(target_count, source_active=source_active, room_code=room_code)
        r = self.registry.rooms[room_code]
        if not self.registry.valid(room_code):
            result = self.registry.shared_usage.conference_capacity(0)
            return dict(result, status="expired", required=target_count > 0)
        results = [p.usage.conference_capacity(target_count, source_active=source_active, room_code=room_code)
                   for p in (r.speech, r.translator)]
        return next((r for r in results if r["status"] not in ("approved", "not_required")), results[0])

    def queued_turn_flow(self, room_code):
        provider = self.registry.selected("speech", room_code)
        return provider.usage.queued_turn_flow(room_code)


class RoutedSpeech:
    def __init__(self, registry, usage):
        self.registry, self.usage = registry, usage

    def __getattr__(self, name):
        return getattr(self.registry.shared_speech, name)

    async def transcribe(self, *args, **kwargs):
        async for result in self.registry.selected("speech").transcribe(*args, **kwargs):
            yield result

    async def synthesize(self, *args, **kwargs):
        # Gnani's synthesis API returns an Audio dataclass, not an iterator.
        return await self.registry.selected("speech").synthesize(*args, **kwargs)

    async def enroll(self, *args, **kwargs):
        return await self.registry.selected("speech").enroll(*args, **kwargs)

    async def aclose(self):
        await self.registry.shared_speech.aclose()


class RoutedTranslator:
    def __init__(self, registry):
        self.registry = registry

    def __getattr__(self, name):
        return getattr(self.registry.shared_translator, name)

    @property
    def engine(self):
        code = current_provider_room()
        return self.registry.engine_for(code) if code else getattr(self.registry.shared_translator, "engine", None)

    async def translate(self, *args, **kwargs):
        return await self.registry.selected("translator").translate(*args, **kwargs)

    async def translate_stream(self, *args, **kwargs):
        async for result in self.registry.selected("translator").translate_stream(*args, **kwargs):
            yield result

    async def aclose(self):
        if hasattr(self.registry.shared_translator, "aclose"):
            await self.registry.shared_translator.aclose()
