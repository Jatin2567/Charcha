"""Read-only reporting for the resources selected by the signed-in account.

These reads never start/probe an engine or fall back from a personal ledger to
the workspace ledger. Private usage is attempted application units, not billing.
"""
from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException

from .usage import RESOURCES


def room_engine_status(registry, code):
    engine = registry.engine_for(code)
    runtime = registry.rooms.get(code)
    own = bool(runtime and runtime.profile.evon_source == "own")
    return {**(engine.status() if engine else {"state": "external"}),
            "scope": "reviewer" if own else "shared",
            "detail": ("Readiness of the personal Evon endpoint selected for this meeting."
                       if own else "Readiness of the shared workspace endpoint. Its meeting counts may include other workspace meetings.")}


def account_engine_status(registry, who):
    engines = {}
    for code, runtime in registry.rooms.items():
        if runtime.account.subject == who.subject and registry.valid(code):
            engine = runtime.translator.engine
            engines[id(engine)] = code
    if len(engines) == 1:
        return room_engine_status(registry, next(iter(engines.values())))
    if engines:
        return {"state": "external", "scope": "multiple",
                "detail": "Your meetings use multiple interpretation engines. Open a current meeting to see its own readiness and startup measurement."}
    profile = registry.profiles.get(who.key) if registry.account_valid(who) else None
    if profile and profile.evon_source == "own":
        return {"state": "idle", "scope": "reviewer", "startup_ms": None,
                "observed_at": None, "active_meetings": 0,
                "detail": "Your personal endpoint has not been prepared in an active meeting."}
    if registry.accounts.shared_resources_allowed(who):
        engine = getattr(registry.shared_translator, "engine", None)
        return {**(engine.status() if engine else {"state": "external"}),
                "scope": "shared",
                "detail": "Shared workspace endpoint status; meeting counts include all meetings using that endpoint."}
    return {"state": "external", "scope": "none",
            "detail": "No active interpretation engine is selected for this account. Select your resources and create a meeting to prepare them."}


def usage_summary(registry, who, scope="auto"):
    digest = hashlib.sha256((registry.accounts.issuer + "\0" + who.subject).encode()).hexdigest()
    path = registry.settings.usage_db_path.parent / "reviewer-usage" / (digest + ".sqlite3")
    profile = registry.profiles.get(who.key) if registry.account_valid(who) else None
    active = [r.profile for code, r in registry.rooms.items()
              if r.account.subject == who.subject and registry.valid(code)]
    selections = ([profile] if profile else []) + active
    has_own = any(p.gnani_source == "own" or p.evon_source == "own" for p in selections)
    has_history = path.exists()
    available = ["shared"]
    if registry.accounts.can_host(who) or has_history:
        available.append("reviewer")
    if scope == "auto":
        scope = "reviewer" if has_own or has_history else "shared"
    if scope not in available:
        raise HTTPException(403, "Personal usage is available only for your own reviewer resources.")
    if scope == "shared":
        return {**registry.shared_usage.public_snapshot(), "resource_scope": {
            "kind": "shared", "label": "Shared workspace resources", "available": available,
            "detail": "Workspace-wide attempted usage for shared providers, across all meetings. Personal reviewer-provider usage is excluded."}}

    now = datetime.now(UTC)
    date = now.date().isoformat()
    reset = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), UTC).isoformat()
    used, ready = {}, True
    # mode=ro cannot create a database, change policy, or initialize allowances.
    if has_history:
        try:
            with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
                used = dict(db.execute("SELECT resource, units FROM usage WHERE period=?", (date,)))
        except (OSError, sqlite3.Error):
            used, ready = {}, False
    detail = ("Your own-provider attempts recorded by Charcha today, across your reviewer meetings. "
              "Only personal-provider units appear here; any shared-provider portion appears in the shared workspace ledger. "
              "Zero means no Charcha-recorded attempts today, not zero usage in your provider account.")
    if not ready:
        detail = "Your personal usage ledger could not be read. Usage is unknown; shared workspace values are not substituted."
    resource_scope = {"kind": "reviewer", "label": "Your personal reviewer resources",
                      "detail": detail, "available": available}
    if profile:
        resource_scope.update(gnani_source=profile.gnani_source, evon_source=profile.evon_source)
    mode = registry.settings.mode
    status = "ready" if ready else "unavailable"
    return {
        "resource_scope": resource_scope, "mode": mode,
        "period": {"date": date, "reset_at": reset},
        "enforcement": {"enabled": False, "persistent": has_history and ready,
                        "status": status, "detail": "Personal-provider units only. This report does not impose a credit limit or connect to provider billing."},
        "resources": [{"key": key, "label": label, "unit": unit,
                       "used": used.get(key, 0) if ready else None,
                       "limit": None, "remaining": None, "utilization_percent": None,
                       "status": "unknown"} for key, label, unit, _ in RESOURCES],
        "approval": {"required": False, "status": "unavailable" if not ready else "locked",
                     "active_flow_id": None, "expires_at": None, "owner_tracks_billing": True,
                     "detail": "Reporting only. Meeting resource access is controlled by your current reviewer invitation and resource selection."},
        "programme": {"source": "not_connected", "unit": None, "balance": None,
                      "observed_at": None, "automatic_sync": False,
                      "detail": "Check your selected providers for billing and remaining credits. No prices or account balance are inferred.",
                      "quoted_rate": None, "pricing": None, "flows": []},
        "billing": {"balance_available": False,
                    "detail": "Attempted units include failed or partial attempts. They are not provider-billed charges or remaining credits."},
    }
