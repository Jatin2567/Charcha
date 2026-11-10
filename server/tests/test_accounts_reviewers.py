"""Reviewer invitations use local signed-in fixtures and never contact providers."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import secrets
import sqlite3
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from charcha.accounts import Account, COOKIE
from charcha.config import Settings
from charcha.main import create_app
from charcha.reviewer_access import ReviewerAccess, ReviewerInvitation
from charcha.store import token_digest


@pytest.fixture
def site(tmp_path):
    app = create_app(Settings(_env_file=None, mode="demo",
        usage_db_path=tmp_path / "usage.sqlite3", charcha_public_origin="https://meet.example.test",
        charcha_meeting_host_email="host@example.test", charcha_auth_domain="tenant.example.test",
        charcha_auth_client_id="client", charcha_auth_client_secret="fake"))
    with TestClient(app, base_url="https://meet.example.test", headers={"X-Charcha-Request":"1"}) as client:
        yield app, client


def login(site, subject, *, admin=False, email=None):
    app, client = site
    raw = secrets.token_urlsafe(32)
    key = token_digest(raw)
    who = Account(key, subject, email or subject + "@example.test", admin, time.time()+600)
    app.state.accounts.sessions[key] = who
    client.cookies.set(COOKIE, raw)
    return who, raw


def invitation(site, **options):
    login(site, "operator", admin=True)
    result = site[1].post("/api/admin/reviewer-invitations", json=options)
    assert result.status_code == 201, result.text
    return result.json()


def test_guest_cannot_self_assert_reviewer_or_issue_invitations(site):
    _, client = site
    assert client.post("/api/reviewer/access/redeem", json={"invitation":"x"*43}).status_code == 401
    login(site, "guest")
    assert client.get("/api/reviewer/access").json()["reviewer"] is False
    for path, method in [("/api/admin/reviewer-invitations", "post"),
                         ("/api/admin/reviewers", "get"), ("/api/admin/reviewers/other", "delete")]:
        response = getattr(client, method)(path, **({"json":{}} if method == "post" else {}))
        assert response.status_code == 403
    result = client.post("/api/reviewer/access/redeem", json={"invitation":"x"*43, "reviewer":True})
    assert result.status_code == 403
    assert client.get("/api/account").json()["can_host"] is False


def test_bound_invite_is_one_use_and_never_grants_admin(site):
    app, client = site
    issued = invitation(site, recipient_email=" Judge@Example.Test ", share_resources=True)
    assert issued["recipient_email"] == "judge@example.test"
    _, judge_cookie = login(site, "judge")
    result = client.post("/api/reviewer/access/redeem", json={"invitation":issued["invitation"]})
    assert result.status_code == 200
    assert result.json() == {"reviewer":True,"can_host":True,"reviewer_shared_allowed":True,
                            "expires_at":issued["expires_at"],"grant_id":issued["id"]}
    who = client.get("/api/account").json()
    assert who["reviewer"] and who["can_host"] and not who["admin"]
    assert client.get("/api/admin").status_code == 403
    assert client.post("/api/reviewer/access/redeem", json={"invitation":issued["invitation"]}).status_code == 403
    login(site,"other")
    assert client.post("/api/reviewer/access/redeem", json={"invitation":issued["invitation"]}).status_code == 403
    client.cookies.set(COOKIE,judge_cookie)
    assert client.get("/api/reviewer/access").json()["reviewer"]
    content = app.state.accounts.db.read_bytes()
    assert issued["invitation"].encode() not in content
    assert hashlib.sha256(issued["invitation"].encode()).hexdigest().encode() in content


def test_wrong_recipient_does_not_consume_invitation(site):
    _,client=site
    issued=invitation(site,recipient_email="judge@example.test")
    login(site,"other")
    assert client.post("/api/reviewer/access/redeem",json={"invitation":issued["invitation"]}).status_code==403
    login(site,"judge")
    assert client.post("/api/reviewer/access/redeem",json={"invitation":issued["invitation"]}).status_code==200


def test_unbound_invitation_binds_first_verified_account_with_own_resources_only(site):
    app,client=site
    issued=invitation(site,share_resources=False)
    who,_=login(site,"judge")
    result=client.post("/api/reviewer/access/redeem",json={"invitation":issued["invitation"]})
    assert result.status_code==200
    assert result.json()["can_host"] and not result.json()["reviewer_shared_allowed"]
    assert app.state.accounts.reviewers.active(replace(who,email="changed@example.test")) is None
    assert app.state.accounts.reviewers.active(replace(who,subject="different")) is None


def test_expired_or_revoked_invitation_cannot_be_redeemed(site):
    app,client=site
    issued=invitation(site)
    with sqlite3.connect(app.state.accounts.db) as db:
        db.execute("UPDATE reviewer_invitations SET expires_at=? WHERE id=?",(time.time()-1,issued["id"]))
    login(site,"judge")
    assert client.post("/api/reviewer/access/redeem",json={"invitation":issued["invitation"]}).status_code==403
    issued=invitation(site)
    assert client.delete("/api/admin/reviewers/"+issued["id"]).status_code==200
    login(site,"judge")
    assert client.post("/api/reviewer/access/redeem",json={"invitation":issued["invitation"]}).status_code==403


def test_expiry_removes_host_permission_and_shared_access(site):
    app,client=site
    issued=invitation(site)
    login(site,"judge")
    client.post("/api/reviewer/access/redeem",json={"invitation":issued["invitation"]})
    with sqlite3.connect(app.state.accounts.db) as db:
        db.execute("UPDATE reviewer_invitations SET expires_at=? WHERE id=?",(time.time()-1,issued["id"]))
    response=client.get("/api/account").json()
    assert not response["reviewer"] and not response["can_host"] and not response["reviewer_shared_allowed"]


def test_revocation_updates_existing_sessions_and_closes_subject_resources(site):
    app,client=site
    issued=invitation(site)
    _,cookie=login(site,"judge")
    client.post("/api/reviewer/access/redeem",json={"invitation":issued["invitation"]})
    revoke=AsyncMock()
    original_resources=getattr(app.state,"reviewer_resources",None)
    app.state.reviewer_resources=SimpleNamespace(revoke_subject=revoke)
    login(site,"operator",admin=True)
    try:
        assert client.delete("/api/admin/reviewers/"+issued["id"]).status_code==200
    finally:
        app.state.reviewer_resources=original_resources
    revoke.assert_awaited_once_with("judge")
    client.cookies.set(COOKIE,cookie)
    assert client.get("/api/account").json()["can_host"] is False


def test_admin_list_has_no_invitation_secret_or_principal(site):
    _,client=site
    issued=invitation(site)
    response=client.get("/api/admin/reviewers")
    assert response.status_code==200
    rows=response.json()["reviewers"]
    assert rows[0]["id"]==issued["id"] and rows[0]["status"]=="pending"
    assert all(key not in rows[0] for key in ["invitation","token_hash","principal","subject","issued_by"])
    assert issued["invitation"] not in response.text


@pytest.mark.parametrize("hours",[0,169,-1])
def test_invitation_duration_is_bounded(site,hours):
    _,client=site
    login(site,"operator",admin=True)
    assert client.post("/api/admin/reviewer-invitations",json={"expires_in_hours":hours}).status_code==422


def test_owner_remains_host_when_accounts_db_contains_only_reviewers(site):
    app,client=site
    invitation(site)
    assert client.get("/api/admin").status_code==200
    assert app.state.accounts.host_email()=="host@example.test"
    login(site,"host")
    result=client.get("/api/account").json()
    assert result["can_host"] and result["reviewer_shared_allowed"] and not result["reviewer"]


def test_grant_survives_new_login_but_not_identity_provider_change(site):
    app,client=site
    issued=invitation(site)
    who,_=login(site,"judge")
    client.post("/api/reviewer/access/redeem",json={"invitation":issued["invitation"]})
    login(site,"judge")
    assert client.get("/api/account").json()["reviewer"]
    other=ReviewerAccess(app.state.accounts.db,"https://other.example.test/")
    assert other.active(who) is None


def test_simultaneous_redemption_has_exactly_one_winner(tmp_path):
    manager=ReviewerAccess(tmp_path/"accounts.sqlite3","https://issuer.example.test/")
    admin=Account("a","admin","admin@example.test",True,time.time()+100)
    issued=manager.create(admin,ReviewerInvitation())
    people=[Account(str(i),f"judge{i}",f"judge{i}@example.test",False,time.time()+100) for i in range(2)]
    def redeem(person):
        try:
            manager.redeem(person,issued["invitation"])
            return 200
        except HTTPException as error:
            return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(redeem,people))
    assert sorted(results)==[200,403]
    assert sum(manager.active(person) is not None for person in people)==1
