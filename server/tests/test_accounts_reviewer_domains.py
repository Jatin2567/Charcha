"""Verified-domain onboarding uses isolated storage and no speech/GPU services."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from unittest.mock import AsyncMock

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import ValidationError

from charcha.accounts import Account, COOKIE
from charcha.config import Settings
from charcha.reviewer_access import ReviewerAccess, ReviewerDecision, ReviewerInvitation
from test_accounts_reviewers import site, login, invitation


@pytest.mark.parametrize("email", ["judge@gnani.ai", "Judge@GnAnI.AI"])
def test_exact_domain_auto_grants_host_without_admin_or_provider_calls(site, monkeypatch, email):
    app, client = site
    async def no_network(*a, **kw):
        raise AssertionError("Access checks must not contact providers")
    monkeypatch.setattr(httpx.AsyncClient, "send", no_network)
    who, _ = login(site,"reviewer",email=email)
    result = client.get("/api/reviewer/access").json()
    assert result["reviewer"] and result["can_host"] and result["reviewer_shared_allowed"]
    assert result["access_source"] == "domain" and result["auto_domains"] == ["gnani.ai"]
    assert result["request"]["status"] == "approved" and result["request"]["source"] == "domain"
    account=client.get("/api/account").json()
    assert account["can_host"] and not account["admin"]
    assert client.get("/api/admin/reviewer-requests").status_code == 403
    first=result["expires_at"]
    assert client.get("/api/reviewer/access").json()["expires_at"] == first
    assert client.post("/api/reviewer/access/request",json={}).json()["expires_at"] == first
    assert 167*3600 < first-time.time() <=168*3600
    assert app.state.reviewer_resources.profiles == {}


@pytest.mark.parametrize("email", ["judge@evilgnani.ai", "judge@gnani.ai.evil.com", "judge@sub.gnani.ai",
    "judge@gnani.site", "judge@gnanialerts.com", "gnani.ai@gmail.com", "judge@gnаni.ai",
    "judge@gnani.ai.", "judge@gnani.ai ", "judge@@gnani.ai"])
def test_domain_lookalikes_and_other_domains_are_not_automatic(site,email):
    _,client=site
    login(site,"visitor",email=email)
    result=client.get("/api/reviewer/access").json()
    assert not result["reviewer"] and not result["can_host"]
    assert result["request"] is None


def test_other_account_requests_are_idempotent_and_need_admin_decision(site):
    app,client=site
    assert client.post("/api/reviewer/access/request",json={}).status_code==401
    _,cookie=login(site,"visitor",email="visitor@example.test")
    assert client.post("/api/reviewer/access/request",json={"email":"judge@gnani.ai","admin":True}).status_code==422
    result=client.post("/api/reviewer/access/request",json={}).json()
    request=result["request"]
    assert request["status"]=="pending" and not result["can_host"]
    assert client.post("/api/reviewer/access/request").json()["request"]==request
    route="/api/admin/reviewer-requests/"+request["id"]+"/decision"
    assert client.post(route,json={"decision":"approve"}).status_code==403
    assert client.post("/api/rooms",json={"title":"No approval"}).status_code==403
    login(site,"admin",admin=True)
    listed=client.get("/api/admin/reviewer-requests").json()["requests"]
    assert len(listed)==1 and listed[0]["email"]=="visitor@example.test"
    assert not {"principal","subject","email_key","reviewed_by"}.intersection(listed[0])
    approved=client.post(route,json={"decision":"approve","share_resources":False,"expires_in_hours":24})
    assert approved.status_code==200 and approved.json()["status"]=="approved"
    client.cookies.set(COOKIE,cookie)
    access=client.get("/api/reviewer/access").json()
    assert access["can_host"] and access["access_source"]=="approval" and not access["reviewer_shared_allowed"]
    assert not client.get("/api/account").json()["admin"]
    with app.state.accounts.reviewers.connection() as db:
        actions=[r[0] for r in db.execute("SELECT action FROM reviewer_access_audit ORDER BY id")]
    assert actions==["request","approve"]


@pytest.mark.parametrize("decision",["deny","revoke"])
def test_decision_persists_blocks_auto_and_invite_bypass_across_new_subject(site,decision):
    app,client=site
    issued=invitation(site)
    who,_=login(site,"gnani",email="judge@gnani.ai")
    initial=client.get("/api/reviewer/access").json()
    manager=app.state.accounts.reviewers
    login(site,"admin",admin=True)
    route="/api/admin/reviewer-requests/"+initial["request"]["id"]+"/decision"
    assert client.post(route,json={"decision":decision}).is_success
    login(site,"new-oidc-subject",email="JUDGE@GNANI.AI")
    access=client.get("/api/reviewer/access").json()
    assert not access["can_host"] and access["request"]["status"]=="revoked"
    assert client.post("/api/reviewer/access/request",json={}).status_code==403
    assert client.post("/api/reviewer/access/redeem",json={"invitation":issued["invitation"]}).status_code==403
    fresh=ReviewerAccess(manager.path,manager.issuer,auto_domains=["gnani.ai"])
    assert fresh.active(who) is None
    fresh.ensure_domain_access(who,renew=True)
    assert fresh.active(who) is None
    login(site,"admin",admin=True)
    assert client.post(route,json={"decision":"approve"}).is_success
    login(site,"gnani",email="judge@gnani.ai")
    assert client.get("/api/reviewer/access").json()["access_source"]=="approval"


def test_issuer_subject_and_email_bind_approved_grant(site):
    app,client=site
    who,_=login(site,"guest")
    request=client.post("/api/reviewer/access/request").json()["request"]
    login(site,"admin",admin=True)
    client.post(f"/api/admin/reviewer-requests/{request['id']}/decision",json={"decision":"approve"})
    manager=app.state.accounts.reviewers
    assert manager.active(who)
    assert manager.active(replace(who,subject="different")) is None
    assert manager.active(replace(who,email="changed@example.test")) is None
    assert ReviewerAccess(manager.path,"https://another-issuer.test/").active(who) is None


def test_domain_expiry_does_not_renew_by_polling_but_explicit_request_can(site):
    app,client=site
    who,_=login(site,"gnani",email="judge@gnani.ai")
    request=client.get("/api/reviewer/access").json()["request"]
    with app.state.accounts.reviewers.connection() as db:
        db.execute("UPDATE reviewer_requests SET expires_at=? WHERE id=?",(time.time()-1,request["id"]))
    expired=client.get("/api/reviewer/access").json()
    assert not expired["can_host"] and expired["request"]["status"]=="expired"
    renewed=client.post("/api/reviewer/access/request",json={}).json()
    assert renewed["can_host"] and renewed["request"]["id"]==request["id"]
    assert renewed["expires_at"]>request["expires_at"]


def test_non_domain_expiry_requires_a_fresh_admin_decision(site):
    app,client=site
    _,cookie=login(site,"guest")
    req=client.post("/api/reviewer/access/request").json()["request"]
    login(site,"admin",admin=True)
    client.post(f"/api/admin/reviewer-requests/{req['id']}/decision",json={"decision":"approve"})
    with app.state.accounts.reviewers.connection() as db:
        db.execute("UPDATE reviewer_requests SET expires_at=? WHERE id=?",(time.time()-1,req["id"]))
    client.cookies.set(COOKIE,cookie)
    result=client.post("/api/reviewer/access/request").json()
    assert not result["can_host"] and result["request"]["status"]=="pending"


def test_concurrent_auto_checks_create_one_grant(tmp_path):
    manager=ReviewerAccess(tmp_path/'accounts.sqlite3',"https://issuer.test/",auto_domains=["gnani.ai"])
    who=Account("session","person","person@gnani.ai",False,time.time()+60)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:manager.active(who),range(8)))
    assert len({r["id"] for r in results})==1
    assert len({r["expires_at"] for r in results})==1
    with manager.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM reviewer_access_audit").fetchone()[0]==1


def test_revocation_cleanup_is_retryable_after_access_is_withdrawn(site):
    app,client=site
    _,cookie=login(site,"gnani",email="judge@gnani.ai")
    req=client.get("/api/reviewer/access").json()["request"]
    login(site,"admin",admin=True)
    cleanup=AsyncMock(side_effect=[RuntimeError("sensitive detail"),None])
    original=app.state.reviewer_resources
    app.state.reviewer_resources=SimpleNamespace(revoke_subject=cleanup)
    route=f"/api/admin/reviewer-requests/{req['id']}/decision"
    try:
        failed=client.post(route,json={"decision":"revoke"})
        assert failed.status_code==503 and 'sensitive detail' not in failed.text
        client.cookies.set(COOKIE,cookie)
        assert not client.get("/api/reviewer/access").json()["can_host"]
        login(site,"admin",admin=True)
        assert client.post(route,json={"decision":"revoke"}).is_success
    finally:
        app.state.reviewer_resources=original
    assert cleanup.await_count==2


@pytest.mark.parametrize("verified",[False,None,"true",1])
def test_callback_rejects_unverified_domain_even_with_valid_signed_claims(site,monkeypatch,verified):
    app,client=site
    client.follow_redirects=False
    params=parse_qs(urlsplit(client.get('/api/account/login').headers['location']).query)
    now=int(time.time());key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    jwk=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    claims={'iss':app.state.accounts.issuer,'aud':'client','sub':'judge','nonce':params['nonce'][0],
            'iat':now,'exp':now+300,'email':'judge@gnani.ai'}
    if verified is not None:claims['email_verified']=verified
    token=jwt.encode(claims,key,algorithm='RS256',headers={'kid':'fixture'})
    def provider(request):
        return httpx.Response(200,json={'id_token':token} if request.method=='POST' else {'keys':[{**jwk,'kid':'fixture'}]})
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(provider),**kw))
    response=client.get('/api/account/callback',params={'code':'fixture','state':params['state'][0]})
    assert response.status_code==403
    assert not app.state.accounts.sessions
    assert app.state.accounts.reviewers.list_requests()==[]


@pytest.mark.parametrize("domains",["*.gnani.ai","@gnani.ai","gnani.ai/","gnаni.ai","gnani.ai."])
def test_domain_policy_rejects_non_exact_names(domains):
    with pytest.raises(ValidationError):Settings(_env_file=None,reviewer_auto_domains=domains)


def test_domain_policy_can_be_disabled_and_normalizes_case():
    assert Settings(_env_file=None,reviewer_auto_domains="").reviewer_auto_domains==[]
    assert Settings(_env_file=None,reviewer_auto_domains=" GNANI.AI,gnani.ai ").reviewer_auto_domains==['gnani.ai']


def test_legacy_invitation_revoke_cleans_all_subjects_sharing_email(site):
    app,client=site
    issued=invitation(site)
    first,_=login(site,"first",email="reviewer@example.test")
    assert client.post('/api/reviewer/access/redeem',json={'invitation':issued['invitation']}).is_success
    second_invite=invitation(site)
    second,_=login(site,"second",email="reviewer@example.test")
    assert client.post('/api/reviewer/access/redeem',json={'invitation':second_invite['invitation']}).is_success
    original=app.state.reviewer_resources;cleanup=AsyncMock()
    app.state.reviewer_resources=SimpleNamespace(revoke_subject=cleanup)
    login(site,"admin",admin=True)
    try:
        assert client.delete('/api/admin/reviewers/'+issued['id']).is_success
    finally:
        app.state.reviewer_resources=original
    assert {a.args[0] for a in cleanup.await_args_list}=={'first','second'}
    assert app.state.accounts.reviewers.active(first) is None
    assert app.state.accounts.reviewers.active(second) is None


def test_old_email_invitation_stays_revoked_after_explicit_reapproval(tmp_path):
    manager=ReviewerAccess(tmp_path/'accounts.sqlite3','https://issuer.test/',auto_domains=['gnani.ai'])
    admin=Account('admin','admin','admin@example.test',True,time.time()+600)
    old=Account('old','same-subject','old@example.test',False,time.time()+600)
    token=manager.create(admin,ReviewerInvitation())
    manager.redeem(old,token['invitation'])
    current=replace(old,email='new@gnani.ai')
    req=manager.active(current)
    manager.decide(admin,req['id'],ReviewerDecision(decision='revoke'))
    manager.decide(admin,req['id'],ReviewerDecision(decision='approve'))
    assert manager.active(current)
    assert manager.active(old) is None
    assert next(r for r in manager.list() if r['id']==token['id'])['status']=='revoked'


def test_access_mutations_require_same_origin(site):
    _,client=site
    login(site,'visitor')
    assert client.post('/api/reviewer/access/request',headers={'Origin':'https://attacker.test'}).status_code==403
    req=client.post('/api/reviewer/access/request').json()['request']
    login(site,'admin',admin=True)
    assert client.post(f"/api/admin/reviewer-requests/{req['id']}/decision",json={'decision':'approve'},
                       headers={'Origin':'https://attacker.test'}).status_code==403
