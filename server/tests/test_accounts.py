"""Identity callbacks and meeting admission with local identities and no cloud calls."""

import json
import secrets
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient

from charcha.accounts import BACKCHANNEL, COOKIE, LOGOUT_EVENT, MFA_CLAIM, Account
from charcha.config import Settings
from charcha.main import create_app
from charcha.providers.demo import SAMPLES
from charcha.store import token_digest


@pytest.fixture
def site(request):
    app = create_app(
        Settings(
            _env_file=None,
            **getattr(request, "param", {}),
            mode="demo",
            charcha_meeting_host_email="host@example.test",
            charcha_public_origin="https://meet.example.test",
            charcha_auth_domain="tenant.example.test",
            charcha_auth_client_id="client",
            charcha_auth_client_secret="fake",
            charcha_admin_subject="auth0|operator",
        )
    )
    with TestClient(
        app,
        base_url="https://meet.example.test",
        follow_redirects=False,
        headers={"X-Charcha-Request": "1"},
    ) as client:
        yield app, client


def identity(site, subject, *, admin=False):
    app, client = site
    token = secrets.token_urlsafe(32)
    key = token_digest(token)
    app.state.accounts.sessions[key] = Account(
        key, subject, subject + "@example.test", admin, time.time() + 600
    )
    client.cookies.set(COOKIE, token)
    return token


JOIN = {"name": "Guest", "language": "hi", "voice_mode": "standard", "consent": True}


def test_admission_cannot_be_bypassed(site):
    _, client = site
    assert client.post("/api/rooms", json={"title": "Family plans"}).status_code == 401
    host = identity(site, "host")
    code = client.post("/api/rooms", json={"title": "Family plans"}).json()["code"]
    url = "/api/rooms/" + code
    host_member = client.post(url + "/join", json=JOIN).json()
    assert host_member["is_host"]
    report = client.get("/api/account/call-performance").json()
    assert report["room_code"] == code and report["participant_id"] == host_member["participant"]["id"]
    assert "session_token" not in report
    guest = identity(site, "guest")
    assert client.get("/api/account/call-performance").json() is None
    assert client.post("/api/rooms", json={"title": "No"}).status_code == 403
    assert client.get(url).json()["participants"] == []
    assert (
        client.get(
            url + "/transcript", headers={"Authorization": "Bearer " + host_member["session_token"]}
        ).status_code
        == 403
    )
    assert client.post(url + "/join", json=JOIN).status_code == 403
    assert client.post(url + "/admission").json()["status"] == "pending"
    assert client.get(url + "/admission/requests").status_code == 403
    client.cookies.set(COOKIE, host)
    [entry] = client.get(url + "/admission/requests").json()["requests"]
    assert entry["email"] == "guest@example.test"
    action = url + "/admission/requests/" + entry["id"]
    assert client.post(action, json={"decision": "approve"}).status_code == 200
    client.cookies.set(COOKIE, guest)
    member = client.post(url + "/join", json=JOIN).json()
    assert not member["is_host"]
    assert client.post(url + "/join", json=JOIN).status_code == 403
    assert (
        client.post("/api/account/logout", headers={"Origin": "https://other.example"}).status_code
        == 403
    )
    assert client.post("/api/account/logout").status_code == 200
    client.cookies.set(COOKIE, guest)
    assert (
        client.get(
            url + "/transcript", headers={"Authorization": "Bearer " + member["session_token"]}
        ).status_code
        == 401
    )
    identity(site, "other")
    client.post(url + "/admission")
    client.cookies.set(COOKIE, host)
    [entry] = client.get(url + "/admission/requests").json()["requests"]
    client.post(url + "/admission/requests/" + entry["id"], json={"decision": "deny"})
    identity(site, "other")
    assert client.post(url + "/admission").json()["status"] == "denied"
    assert client.post(url + "/join", json=JOIN).status_code == 403


def test_device_transfer_returns_to_waiting_room(site):
    app, client = site
    host = identity(site, "host")
    code = client.post("/api/rooms", json={"title": "Device switch"}).json()["code"]
    base = "/api/rooms/" + code
    guest = identity(site, "guest")
    client.post(base + "/admission")
    client.cookies.set(COOKIE, host)
    [entry] = client.get(base + "/admission/requests").json()["requests"]
    client.post(base + "/admission/requests/" + entry["id"], json={"decision": "approve"})
    client.cookies.set(COOKIE, guest)
    member = client.post(base + "/join", json=JOIN).json()
    identity(site, "unrelated")
    assert client.post(base + "/admission/rejoin").status_code == 409
    identity(site, "guest")
    assert client.post(base + "/admission/rejoin").json()["status"] == "pending"
    assert client.post(base + "/join", json=JOIN).status_code == 403
    assert token_digest(member["session_token"]) not in app.state.store.sessions


def test_host_policy_and_admin_separation(site):
    app, client = site
    identity(site, "host")
    assert client.get("/api/admin").status_code == 403
    assert client.post("/api/admin/host", json={"email": "other@example.test"}).status_code == 403
    identity(site, "admin", admin=True)
    assert client.post("/api/admin/host", json={"email": "bad"}).status_code == 422
    assert (
        client.post("/api/admin/host", json={"email": "Other@example.test"}).json()["host_email"]
        == "other@example.test"
    )
    assert app.state.accounts.host_email() == "other@example.test"
    identity(site, "other")
    assert client.post("/api/rooms", json={"title": "New host"}).status_code == 201


@pytest.mark.parametrize(
    "admin,with_mfa,success", [(False, False, True), (True, False, False), (True, True, True)]
)
def test_callback_replay_session_rotation_and_mfa(site, monkeypatch, admin, with_mfa, success):
    app, client = site
    location = client.get(
        "/api/account/login", params={"admin": admin, "destination": "/join/abcd"}
    ).headers["location"]
    params = parse_qs(urlsplit(location).query)
    assert params["code_challenge_method"] == ["S256"]
    if admin:
        assert params["connection"] == ["Username-Password-Authentication"]

    async def verified(code, verifier, nonce):
        assert code == "local" and params["nonce"] == [nonce] and verifier
        return {
            "sub": "auth0|operator",
            "email": "user@example.test",
            "auth_time": time.time(),
            "exp": time.time() + 3600,
            MFA_CLAIM: with_mfa,
        }

    monkeypatch.setattr(app.state.accounts, "verify_code", verified)
    callback = "/api/account/callback?code=local&state=" + params["state"][0]
    assert client.get("/api/account/callback?code=local&state=foreign").status_code == 401
    result = client.get(callback)
    assert result.status_code == (303 if success else 403)
    assert client.get(callback).status_code == 401
    assert client.get("/api/account").json()["admin"] == (admin and success)
    if success:
        assert (
            "HttpOnly" in result.headers["set-cookie"] and "Secure" in result.headers["set-cookie"]
        )
        assert result.headers["location"].endswith("/#/admin" if admin else "/#/join/abcd")


@pytest.mark.parametrize(
    "mutation", ["valid", "issuer", "audience", "nonce", "unverified", "expired", "tampered"]
)
async def test_validates_signed_identity_tokens(site, monkeypatch, mutation):
    app, _ = site
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    now = int(time.time())
    issuer = "https://tenant.example.test/"
    claims = {
        "iss": issuer,
        "aud": "client",
        "sub": "google-oauth2|test",
        "nonce": "challenge",
        "exp": now + 60,
        "iat": now,
        "email": "test@example.test",
        "email_verified": True,
    }
    if mutation == "issuer":
        claims["iss"] = "https://elsewhere.test/"
    if mutation == "audience":
        claims["aud"] = "other"
    if mutation == "nonce":
        claims["nonce"] = "other"
    if mutation == "unverified":
        claims["email_verified"] = False
    if mutation == "expired":
        claims["exp"] = now - 1
    signing_key = (
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
        if mutation == "tampered"
        else key
    )
    signed = jwt.encode(claims, signing_key, algorithm="RS256", headers={"kid": "test"})

    def provider(req):
        assert req.url.host == "tenant.example.test"
        return httpx.Response(
            200,
            json={"id_token": signed}
            if req.method == "POST"
            else {"keys": [{**jwk, "kid": "test"}]},
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(provider), **kw)
    )
    if mutation == "valid":
        assert (await app.state.accounts.verify_code("code", "verifier", "challenge"))[
            "sub"
        ] == claims["sub"]
    else:
        with pytest.raises(HTTPException):
            await app.state.accounts.verify_code("code", "verifier", "challenge")


def test_correction_is_shared_versioned_and_needs_fresh_listener_ack(site):
    _, client = site
    host = identity(site, "host")
    code = client.post("/api/rooms", json={"title": "Meeting time"}).json()["code"]
    base = "/api/rooms/" + code
    hm = client.post(base + "/join", json=JOIN).json()
    guest = identity(site, "guest")
    client.post(base + "/admission")
    client.cookies.set(COOKIE, host)
    req = client.get(base + "/admission/requests").json()["requests"][0]
    client.post(base + "/admission/requests/" + req["id"], json={"decision": "approve"})
    client.cookies.set(COOKIE, guest)
    gm = client.post(base + "/join", json={**JOIN, "language": "ta"}).json()
    h = {"Authorization": "Bearer " + hm["session_token"]}
    g = {"Authorization": "Bearer " + gm["session_token"]}
    client.cookies.set(COOKIE, host)

    def completed(message_id):
        for _ in range(50):
            turns = client.get(base + "/transcript", headers=h).json()["turns"]
            turn = next(t for t in turns if t["id"] == message_id)
            if turn["status"] != "processing":
                return turn
            time.sleep(0.02)
        pytest.fail("Translation did not finish")

    orig = client.post(base + "/text", json={"text": SAMPLES[0]["hi"]}, headers=h).json()[
        "utterance_id"
    ]
    assert completed(orig)["status"] == "complete"
    edit = base + "/turns/" + orig + "/correct"
    client.cookies.set(COOKIE, guest)
    assert (
        client.post(base + "/confirmations", json={"utterance_id": orig}, headers=g).status_code
        == 200
    )
    assert client.post(edit, json={"text": SAMPLES[1]["hi"]}, headers=g).status_code == 403
    client.cookies.set(COOKIE, host)
    update = client.post(edit, json={"text": SAMPLES[1]["hi"]}, headers=h).json()["utterance_id"]
    assert client.post(edit, json={"text": SAMPLES[1]["hi"]}, headers=h).status_code == 409
    corrected = completed(update)
    assert corrected["translations"]["ta"] == SAMPLES[1]["ta"] and corrected["confirmed_by"] == []
    assert corrected["listeners"] == {gm["participant"]["id"]: "Guest"}
    assert corrected["replaces_id"] == orig and completed(orig)["superseded_by"] == update
    assert completed(orig)["confirmed_by"] == [gm["participant"]["id"]]
    assert (
        client.post(base + "/confirmations", json={"utterance_id": update}, headers=h).status_code
        == 403
    )
    client.cookies.set(COOKIE, guest)
    assert (
        client.post(base + "/confirmations", json={"utterance_id": orig}, headers=g).status_code
        == 409
    )
    assert (
        client.post(base + "/confirmations", json={"utterance_id": update}, headers=g).status_code
        == 200
    )


KEYCLOAK = {
    "charcha_identity_provider": "keycloak",
    "charcha_oidc_issuer": "https://identity.example.test/identity/realms/charcha",
}


@pytest.mark.parametrize("site", [KEYCLOAK], indirect=True)
def test_signout_cancels_login_and_can_recover_an_orphaned_provider_session(site):
    _, client = site
    login = client.get("/api/account/login")
    state = parse_qs(urlsplit(login.headers["location"]).query)["state"][0]
    blocked = client.post("/api/account/logout", headers={"origin": "https://untrusted.example"})
    assert blocked.status_code == 403
    for _ in range(2):
        response = client.post("/api/account/logout")
        assert response.status_code == 200
        url = urlsplit(response.json()["continue_url"])
        assert url.path.endswith("/protocol/openid-connect/logout")
        assert parse_qs(url.query) == {"client_id": ["client"], "post_logout_redirect_uri": ["https://meet.example.test/"]}
        assert any("charcha_login=" in cookie and "Max-Age=0" in cookie for cookie in response.headers.get_list("set-cookie"))
    client.cookies.set("charcha_login", state)
    assert client.get("/api/account/callback", params={"state": state, "code": "stale"}).status_code == 401


@pytest.mark.parametrize("site", [KEYCLOAK], indirect=True)
def test_signed_provider_logout_invalidates_matching_admin_sessions_only(site):
    app, client = site
    accounts = app.state.accounts
    current = time.time()
    for sid, token in (("one", "session-a"), ("one", "session-b"), ("two", "other-device")):
        key = token_digest(token)
        accounts.sessions[key] = Account(key, "operator", "admin@example.test", True, current + 400, sid)
    client.cookies.set(COOKIE, "session-a")
    assert client.get("/api/admin").status_code == 200
    signing = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    accounts.signing_keys = {"key": json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing.public_key()))}
    accounts.keys_valid_until = time.monotonic() + 90
    claims = {"iss": accounts.issuer, "aud": "client", "sub": "operator", "sid": "one",
              "iat": int(current), "jti": "notice", "events": {LOGOUT_EVENT: {}}}
    def notify(values, signer=signing):
        token = jwt.encode(values, signer, algorithm="RS256", headers={"kid": "key"})
        return client.post(BACKCHANNEL, data={"logout_token": token}).status_code
    for change in ({"nonce": "cross-token"}, {"events": {}}, {"iat": current - 600}, {"aud": "other"}, {"sid": ""}):
        assert notify({**claims, **change}) == 400
    assert notify(claims, rsa.generate_private_key(public_exponent=65537, key_size=2048)) == 400
    assert client.get("/api/admin").status_code == 200
    assert notify(claims) == notify(claims) == 200
    assert client.get("/api/admin").status_code == 401
    assert list(accounts.sessions) == [token_digest("other-device")]


@pytest.mark.parametrize("site", [KEYCLOAK], indirect=True)
def test_password_security_requires_account_and_google_hint_cannot_bypass_admin(site):
    app, client = site
    assert client.get("/api/account/security").status_code == 401
    assert client.get("/api/account").json()["password_security_available"]
    identity(site, "guest")
    response = client.get("/api/account/security")
    assert response.status_code == 303
    assert response.headers["location"] == KEYCLOAK["charcha_oidc_issuer"] + "/account/account-security/signing-in"
    response = client.get("/api/account/login", params={"google": True})
    params = parse_qs(urlsplit(response.headers["location"]).query, keep_blank_values=True)
    assert params["kc_idp_hint"] == ["google"]
    assert params["prompt"] == ["select_account"] and params["max_age"] == ["0"]
    app.state.settings.charcha_admin_subject = "operator-uuid"
    response = client.get("/api/account/login", params={"google": True, "admin": True})
    params = parse_qs(urlsplit(response.headers["location"]).query, keep_blank_values=True)
    assert params["kc_idp_hint"] == [""]
    assert params["max_age"] == ["0"]


@pytest.mark.parametrize("site", [KEYCLOAK], indirect=True)
@pytest.mark.parametrize(
    "methods,expected",
    [(["pwd", "otp"], 303), (["pwd"], 403), (["otp"], 403), (["google"], 403), ("pwd otp", 403)],
)
def test_keycloak_admin_requires_password_and_otp(site, monkeypatch, methods, expected):
    app, client = site
    app.state.settings.charcha_admin_subject = "operator-uuid"
    response = client.get("/api/account/login", params={"admin": True})
    location = response.headers["location"]
    assert location.startswith(KEYCLOAK["charcha_oidc_issuer"] + "/protocol/openid-connect/auth?")
    params = parse_qs(urlsplit(location).query, keep_blank_values=True)
    assert params["max_age"] == ["0"] and params["kc_idp_hint"] == [""]
    assert "connection" not in params

    async def verified(*args):
        return {
            "sub": "operator-uuid",
            "sid": "provider-login-session",
            "email": "operator@example.test",
            "amr": methods,
            "auth_time": time.time(),
            "exp": time.time() + 600,
        }

    monkeypatch.setattr(app.state.accounts, "verify_code", verified)
    result = client.get(
        "/api/account/callback", params={"code": "test", "state": params["state"][0]}
    )
    assert result.status_code == expected


@pytest.mark.parametrize("site", [KEYCLOAK], indirect=True)
async def test_keycloak_verifies_realm_issuer_and_uses_local_realm_endpoints(site, monkeypatch):
    app, _ = site
    issuer = KEYCLOAK["charcha_oidc_issuer"]
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    claims = {
        "iss": issuer,
        "aud": "client",
        "sub": "local-user",
        "nonce": "test",
        "exp": int(time.time()) + 600,
        "iat": int(time.time()),
        "email_verified": True,
        "email": "host@example.test",
    }
    token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test"})
    urls = []

    def provider(request):
        urls.append(str(request.url))
        assert request.url.host == "identity.example.test"
        return httpx.Response(
            200,
            json={"id_token": token}
            if request.method == "POST"
            else {"keys": [{**jwk, "kid": "test"}]},
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(provider), **kw)
    )
    assert (await app.state.accounts.verify_code("code", "verifier", "test"))["sub"] == "local-user"
    assert urls == [
        issuer + "/protocol/openid-connect/token",
        issuer + "/protocol/openid-connect/certs",
    ]


@pytest.mark.parametrize(
    "issuer",
    [
        "",
        "http://identity.example.test/realms/charcha",
        "https://user:secret@identity.example.test/realms/charcha",
        "https://identity.example.test/not-a-realm",
        "https://identity.example.test/realms/charcha?secret=x",
    ],
)
def test_keycloak_issuer_fails_closed(issuer):
    from charcha.accounts import Accounts

    config = Settings(
        _env_file=None,
        charcha_identity_provider="keycloak",
        charcha_oidc_issuer=issuer,
        charcha_auth_client_id="client",
        charcha_auth_client_secret="test",
    )
    assert not Accounts(config, None).configured
