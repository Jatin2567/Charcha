"""Budget, room ownership and admin requests, with no network speech clients."""
import secrets
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
import pytest

from charcha.accounts import Account, COOKIE
from charcha.config import Settings
from charcha.errors import ProviderError
from charcha.main import create_app
from charcha.services import host_budget
from charcha.services.usage import UsageGuard, provider_flow, provider_room
from charcha.store import token_digest


def test_standing_host_policy(tmp_path):
    settings = Settings(_env_file=None, mode="live", usage_require_flow_approval=True, usage_require_room_scope=True,
                        usage_stt_seconds_per_day=1, charcha_meeting_host_email="host@example.test",
                        usage_db_path=tmp_path/"ledger.sqlite3")
    app = create_app(settings)
    usage = app.state.usage
    host = "host@example.test"
    old_room = "abcd12344321"
    old = usage.approve_flow(purpose="live_interpretation", room_code=old_room, seconds=30, budgets={"stt_seconds":1})
    with provider_room(old_room):
        usage.reserve({"stt_seconds":1})
    policy = usage._operator_change(host_budget.activate, host_email=host, limit_inr=1, carry_room=old_room)
    assert policy["reserved_inr"] == .0075 and usage.inspect_flow(old["id"])["status"] == "closed"
    assert usage._operator_change(host_budget.activate, host_email=host, limit_inr=500) == policy
    def login(client, email, admin=False):
        cookie = secrets.token_hex(16)
        key = token_digest(cookie)
        app.state.accounts.sessions[key] = Account(key, email, email, admin, time.time()+300)
        client.cookies.set(COOKIE, cookie)

    url = "/api/admin/gnani-budget"
    with TestClient(app, headers={"X-Charcha-Request":"1"}) as client:
        assert client.get(url).status_code == 401
        login(client, "guest@example.test")
        assert client.post("/api/rooms", json={"title":"Guest attempt"}).status_code == 403
        assert client.get(url).status_code == client.post(url, json={"limit_inr":100,"revision":1}).status_code == 403
        login(client, host)
        assert client.post(url, json={"limit_inr":400,"revision":1}).status_code == 403
        codes = [client.post("/api/rooms", json={"title":"Meeting", "audio_mode":"interpreted"}).json()["code"]
                 for _ in range(2)]
        original = client.post("/api/rooms", json={"title":"Original","audio_mode":"original"}).json()["code"]
        assert usage.conference_capacity(2, room_code=original)["status"] == "locked"
        assert usage.conference_capacity(9, room_code=codes[0])["authorization"] == "host_budget"
        with provider_room(codes[0]), provider_flow(usage.queued_turn_flow(codes[1])), pytest.raises(ProviderError):
            usage.reserve({"stt_seconds":1})
        with provider_room(codes[1]), pytest.raises(ProviderError):
            usage.reserve({"voice_enrollments":1})
        def spend(code):
            with provider_room(code):
                try:
                    usage.reserve({"stt_seconds":100})
                    return True
                except ProviderError:
                    return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(spend, codes)) == [False, True]
        assert usage.host_policy()["reserved_inr"] == .7575
        login(client, "admin@example.test", admin=True)
        assert client.post(url, json={"limit_inr":True,"revision":1}).status_code == 422
        assert client.post(url, json={"limit_inr":0,"revision":1},headers={"Origin":"https://other.test"}).status_code == 403
        assert client.post(url, json={"limit_inr":0,"revision":1}).json()["budget"]["remaining_inr"] == 0
        assert client.post(url, json={"limit_inr":500,"revision":1}).status_code == 409
        assert usage.conference_capacity(1, room_code=codes[1])["status"] == "exhausted"
        with provider_room(codes[0]), pytest.raises(ProviderError):
            usage.reserve({"mt_requests":1})
        assert client.post(url, json={"limit_inr":500,"revision":2}).json()["budget"]["remaining_inr"] == 499.2425
        # Changing the designated creator does not transfer this host's allowance.
        assert client.post("/api/admin/host", json={"email":"new@example.test"}).is_success
        login(client, "new@example.test")
        new = client.post("/api/rooms", json={"title":"Other host","audio_mode":"interpreted"}).json()["code"]
        assert usage.conference_capacity(1, room_code=new)["status"] == "locked"
        assert usage.conference_capacity(1, room_code=codes[0])["status"] == "approved"
    guard = UsageGuard(settings)
    assert guard.host_policy()["reserved_inr"] == .7575
    guard.close()
