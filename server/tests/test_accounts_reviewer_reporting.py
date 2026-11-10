"""Account/meeting reports use selected resources without starting providers."""
import hashlib
from types import SimpleNamespace

import pytest

from test_accounts_reviewer_meetings import site, reviewer, own_resources, make_room, sign_in
from charcha.services.usage import provider_room


def test_personal_engine_status_ignores_shared_engine(site, monkeypatch):
    app, client = site
    reviewer(site)
    registry = app.state.reviewer_resources
    own_resources(client)
    before = client.get("/api/account/interpretation-engine").json()
    assert before["scope"] == "reviewer" and before["state"] == "idle"
    assert before["startup_ms"] is None and before["observed_at"] is None
    code = make_room(client)
    engine = registry.engine_for(code)
    engine.touch()
    engine.duration_ms = 1234
    monkeypatch.setattr(registry.shared_translator.engine, "status",
                        lambda: (_ for _ in ()).throw(AssertionError("Wrong engine")))
    current = client.get("/api/account/interpretation-engine").json()
    assert current["scope"] == "reviewer" and current["state"] == "ready"
    assert current["startup_ms"] == 1234
    assert engine.task is None and engine.meeting_task is None


def test_multiple_personal_rooms_do_not_invent_aggregate_readiness(site):
    app, client = site
    reviewer(site)
    own_resources(client)
    first, second = make_room(client), make_room(client)
    app.state.reviewer_resources.engine_for(first).touch()
    report = client.get("/api/account/interpretation-engine").json()
    assert report["scope"] == "multiple"
    assert "startup_ms" not in report and "active_meetings" not in report
    assert app.state.reviewer_resources.engine_for(second).task is None


def test_unconfigured_guest_has_no_measured_engine(site):
    _, client = site
    sign_in(site, "guest")
    report = client.get("/api/account/interpretation-engine").json()
    assert report["scope"] == "none" and "startup_ms" not in report


def test_personal_usage_is_persistent_isolated_and_never_owner_fallback(site, monkeypatch):
    app, client = site
    reviewer(site)
    own_resources(client)
    code = make_room(client)
    registry = app.state.reviewer_resources
    with provider_room(code):
        registry.selected("speech").usage.reserve({"stt_seconds": 7})
        registry.selected("translator").usage.reserve({"mt_requests": 2})
    monkeypatch.setattr(registry.shared_usage, "public_snapshot",
                        lambda: (_ for _ in ()).throw(AssertionError("Wrong ledger")))
    for _ in range(2):
        report = client.get("/api/usage").json()
        assert report["resource_scope"]["kind"] == "reviewer"
        values = {r["key"]: r["used"] for r in report["resources"]}
        assert values["stt_seconds"] == 7 and values["mt_requests"] == 2
        assert not report["enforcement"]["enabled"]
        assert all(r["limit"] is None and r["remaining"] is None for r in report["resources"])
        assert report["programme"]["balance"] is None and report["programme"]["pricing"] is None
        assert "private-key" not in str(report) and "model-key" not in str(report)
    assert client.delete("/api/reviewer/workspace").is_success
    assert client.get("/api/usage").json()["resource_scope"]["kind"] == "reviewer"
    assert all(r["used"] is not None for r in client.get("/api/usage").json()["resources"])


def test_usage_scopes_do_not_leak_another_reviewers_units(site):
    app, client = site
    reviewer(site)
    own_resources(client)
    code = make_room(client)
    with provider_room(code):
        app.state.reviewer_resources.selected("speech").usage.reserve({"stt_seconds": 9})
    shared = client.get("/api/usage?scope=shared").json()
    assert shared["resource_scope"]["kind"] == "shared"
    assert next(r["used"] for r in shared["resources"] if r["key"] == "stt_seconds") == 0
    sign_in(site, "other-guest")
    assert client.get("/api/usage?scope=reviewer").status_code == 403
    assert client.get("/api/usage?scope=someone-else").status_code == 422
    assert client.get("/api/usage").json()["resource_scope"]["kind"] == "shared"


def test_unused_personal_usage_is_read_only_and_corruption_is_unknown(site):
    app, client = site
    who, _, _ = reviewer(site)
    own_resources(client)
    registry = app.state.reviewer_resources
    root = registry.settings.usage_db_path.parent / "reviewer-usage"
    report = client.get("/api/usage").json()
    assert not root.exists()
    assert all(r["used"] == 0 for r in report["resources"])
    digest = hashlib.sha256((registry.accounts.issuer + "\0" + who.subject).encode()).hexdigest()
    root.mkdir()
    (root / (digest + ".sqlite3")).write_bytes(b"invalid database")
    report = client.get("/api/usage").json()
    assert report["enforcement"]["status"] == "unavailable"
    assert all(r["used"] is None for r in report["resources"])


def test_anonymous_cannot_read_resource_reports(site):
    _, client = site
    assert client.get("/api/usage?scope=reviewer").status_code == 401
    assert client.get("/api/account/interpretation-engine").status_code == 401


def test_engine_routes_normalize_codes_before_membership_and_lookup(site, monkeypatch):
    app, client = site
    reviewer(site)
    own_resources(client)
    code = make_room(client)
    authenticated = []
    def authenticate(token, given):
        authenticated.append(given)
        return SimpleNamespace(participant_id="fixture-member")
    monkeypatch.setattr(app.state.store, "authenticate", authenticate)
    headers = {"Authorization": "Bearer fixture-member-token"}
    result = client.get(f"/api/rooms/{code.upper()}/engine", headers=headers)
    assert result.status_code == 200 and result.json()["scope"] == "reviewer"
    # No connected media: recovery must refuse startup, not fail the lookup.
    result = client.post(f"/api/rooms/{code.upper()}/engine", headers=headers)
    assert result.status_code == 409
    assert "Connect your meeting audio" in result.json()["detail"]
    assert authenticated == [code, code]
    assert app.state.reviewer_resources.engine_for(code).task is None
