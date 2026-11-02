import argparse
import importlib.util
from pathlib import Path

import httpx
import pytest

MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_browser_audio.py"
spec = importlib.util.spec_from_file_location("browser_audio_check", MODULE_PATH)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def arguments(**values):
    return argparse.Namespace(**{"api_url": "http://127.0.0.1:5180/api", "room": "test-room", "seconds": 1, "hold": 0, **values})


@pytest.mark.parametrize("value", ["https://provider.example/api", "http://127.0.0.1.evil.test/api", "http://user:secret@127.0.0.1/api", "http://127.0.0.1/api?key=hidden", "http://127.0.0.1:bad/api"])
def test_rejects_nonloopback_or_credential_urls(value):
    with pytest.raises(check.CheckRejected):
        check.loopback_url(value, ("http", "https"))


@pytest.mark.parametrize("value", ["http://127.0.0.1:5180/api", "http://localhost:5180/api", "http://[::1]:5180/api"])
def test_accepts_loopback(value):
    assert check.loopback_url(value, ("http", "https")) == value


async def test_refuses_live_mode_before_join_or_rtc():
    requests = []

    def handler(request):
        requests.append((request.method, request.url.path))
        return httpx.Response(200, json={"mode": "live"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(check.CheckRejected, match="transport mode"):
            await check.perform_check(arguments(), client)
    assert requests == [("GET", "/api/health")]


@pytest.mark.parametrize("fail_at", ["remote_rtc", "patch"])
async def test_leaves_fixture_membership_after_failed_setup(fail_at, capsys):
    requests = []

    def handler(request):
        requests.append((request.method, request.url.path))
        if request.url.path.endswith("/health"):
            return httpx.Response(200, json={"mode": "transport"})
        if request.url.path.endswith("/join"):
            return httpx.Response(200, json={
                "session_token": "private-test-membership", "participant": {"id": "fixture-id"},
                "room": {"mode": "transport"},
                "livekit": {"url": "wss://remote.test" if fail_at == "remote_rtc" else "ws://127.0.0.1:7880",
                            "token": "private-media-token", "agent_identity": "trusted-agent"},
            })
        if request.method == "PATCH":
            return httpx.Response(503, json={"detail": "private upstream detail"})
        if request.url.path.endswith("/leave"):
            assert request.headers["Authorization"] == "Bearer private-test-membership"
            return httpx.Response(200, json={"ok": True})
        raise AssertionError("Unexpected route")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(check.CheckRejected):
            await check.perform_check(arguments(), client)
    assert requests[-1] == ("POST", "/api/rooms/test-room/leave")
    output = capsys.readouterr()
    assert "private" not in output.out + output.err
