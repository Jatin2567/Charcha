import importlib.util
import json
from pathlib import Path
import ssl

import httpx
import pytest

MODULE = Path(__file__).resolve().parents[2] / "scripts" / "verify_lan_stack.py"
spec = importlib.util.spec_from_file_location("lan_stack_probe", MODULE)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def health():
    return {"mode": "transport", "providers": [
        {"name": "LiveKit", "status": "configured"},
        *({"name": name, "status": "disabled"} for name in ("Prisma STT", "Evon MT", "Timbre TTS")),
    ]}


@pytest.mark.parametrize("url", ["http://192.168.1.7:8443", "https://8.8.8.8:8443", "https://127.0.0.1:8443", "https://192.168.1.7:443", "https://user:secret@192.168.1.7:8443", "https://192.168.1.7:8443?token=x", "https://host:8443", "https://192.168.1.7:8443/"])
def test_url_gate_rejects_unsafe_or_unexpected_targets(url):
    with pytest.raises(probe.ProbeRejected, match="invalid_private_test_url"):
        probe.private_url(url, "https", 8443, "")


def test_manifest_binds_media_to_exact_frontend_host(tmp_path):
    path = tmp_path / "manifest.json"
    manifest = {"mode": "transport", "screening": "off", "frontend": "https://192.168.1.7:8443/#/tests", "livekit": "wss://192.168.1.7:8444"}
    path.write_text(json.dumps(manifest))
    assert probe.load_manifest(path) == {"base": "https://192.168.1.7:8443", "media": "wss://192.168.1.7:8444"}
    manifest["livekit"] = "wss://192.168.1.8:8444"
    path.write_text(json.dumps(manifest))
    with pytest.raises(probe.ProbeRejected, match="media_host_mismatch"):
        probe.load_manifest(path)


@pytest.mark.parametrize("kind", ["live", "unknown", "stt_enabled"])
async def test_refuses_provider_modes_before_creating_room(kind):
    requests = []
    payload = health()
    if kind == "stt_enabled":
        payload["providers"][1]["status"] = "configured"
    else:
        payload["mode"] = kind

    def handler(request):
        requests.append((request.method, request.url.path))
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(probe.ProbeRejected):
            await probe.perform({"base": "https://192.168.1.7:8443", "media": "wss://192.168.1.7:8444"}, client, {"checks": []})
    assert requests == [("GET", "/api/health")]


async def test_redirected_media_rejected_and_fixture_removed_without_rtc(capsys):
    requests = []

    def handler(request):
        requests.append((request.method, request.url.path))
        if request.url.path.endswith("/health"):
            return httpx.Response(200, json=health())
        if request.url.path == "/api/rooms":
            return httpx.Response(201, json={"code": "local-room", "mode": "transport"})
        if request.url.path.endswith("/join"):
            return httpx.Response(200, json={"participant": {"id": "fixture", "voice_mode": "standard"}, "room": {"mode": "transport"}, "session_token": "private-session", "livekit": {"url": "wss://other.example", "token": "private-media", "agent_identity": "fixture-agent"}})
        if request.url.path.endswith("/leave"):
            assert request.headers["Authorization"] == "Bearer private-session"
            return httpx.Response(200, json={"ok": True})
        raise AssertionError("unexpected request")

    report = {"checks": []}
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(probe.ProbeRejected, match="invalid_media_membership"):
            await probe.perform({"base": "https://192.168.1.7:8443", "media": "wss://192.168.1.7:8444"}, client, report)
    assert requests[-1] == ("POST", "/api/rooms/local-room/leave")
    assert report["fixture_cleanup_confirmed"]
    assert "private" not in capsys.readouterr().out


def test_report_sanitizes_upstream_errors_and_never_overwrites(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(probe, "ROOT", tmp_path)
    monkeypatch.setattr(probe, "load_manifest", lambda path: {})

    async def fail(*args):
        raise RuntimeError("Authorization: secret-private-media-token")

    monkeypatch.setattr(probe, "run", fail)
    output = tmp_path / "work" / "evidence.json"
    args = ["--manifest", "fake.json", "--ca", "public-ca.pem", "--output", str(output)]
    assert probe.main(args) == 1
    result = json.loads(output.read_text())
    assert result["failure_code"] == "local_tls_media_or_application_failure"
    assert result["provider_requests"] == 0
    assert "secret" not in output.read_text() + capsys.readouterr().out
    original = output.read_bytes()
    with pytest.raises(SystemExit):
        probe.main(args)
    assert output.read_bytes() == original


async def test_https_only_checks_page_and_signaling_then_leaves_both_members(monkeypatch):
    requests, signals = [], []
    context = ssl.create_default_context()
    count = 0

    async def signal(url, token, identity, code, supplied_context):
        signals.append(identity)
        assert url == "wss://192.168.1.7:8444"
        assert token == "private-media"
        assert code == "local-room"
        assert supplied_context is context

    monkeypatch.setattr(probe, "signaling_join", signal)

    def handler(request):
        nonlocal count
        requests.append((request.method, request.url.path))
        if request.url.path.endswith("/health"):
            return httpx.Response(200, json=health())
        if request.url.path == "/":
            return httpx.Response(200, text='<html><div id="root"></div></html>', headers={"content-type": "text/html"})
        if request.url.path == "/api/rooms":
            return httpx.Response(201, json={"code": "local-room", "mode": "transport"})
        if request.url.path.endswith("/join"):
            count += 1
            return httpx.Response(200, json={"participant": {"id": f"fixture{count}", "voice_mode": "standard"}, "room": {"mode": "transport"}, "session_token": "private-session", "livekit": {"url": "wss://192.168.1.7:8444", "token": "private-media"}})
        if request.url.path.endswith("/transcript"):
            return httpx.Response(200, json={"turns": []})
        if request.url.path.endswith("/leave"):
            return httpx.Response(200, json={"ok": True})
        raise AssertionError("unexpected request")

    report = {"checks": []}
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await probe.perform_https({"base": "https://192.168.1.7:8443", "media": "wss://192.168.1.7:8444"}, client, context, report)
    assert signals == ["fixture1", "fixture2"]
    assert requests[-2:] == [("POST", "/api/rooms/local-room/leave")] * 2
    assert not any(method == "PATCH" for method, _ in requests)
    assert report["fixture_cleanup_confirmed"]
    assert "directions" not in report


async def test_wss_signaling_uses_verified_tls_auth_header_and_rejects_redirects(monkeypatch):
    import websockets.asyncio.client
    from livekit.protocol.rtc import SignalResponse

    context = ssl.create_default_context()
    observed = {}

    class FakeConnect:
        def __init__(self, url, **kwargs):
            observed.update(url=url, **kwargs)
            marker = RuntimeError("redirect")
            assert self.process_redirect(marker) is marker

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def recv(self):
            response = SignalResponse()
            response.join.participant.identity = "fixture"
            response.join.room.name = "local-room"
            return response.SerializeToString()

    monkeypatch.setattr(websockets.asyncio.client, "connect", FakeConnect)
    await probe.signaling_join("wss://192.168.1.7:8444", "private-token", "fixture", "local-room", context)
    assert "private-token" not in observed["url"]
    assert observed["additional_headers"] == {"Authorization": "Bearer private-token"}
    assert observed["ssl"] is context
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    assert observed["proxy"] is None


def test_https_only_report_never_claims_audio_acceptance(monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "ROOT", tmp_path)
    monkeypatch.setattr(probe, "load_manifest", lambda path: {})

    async def done(config, ca, report, https_only=False):
        assert https_only
        report["fixture_cleanup_confirmed"] = True

    monkeypatch.setattr(probe, "run", done)
    output = tmp_path / "work" / "signaling.json"
    assert probe.main(["--manifest", "fake", "--ca", "public", "--output", str(output), "--https-only"]) == 0
    report = json.loads(output.read_text())
    assert report["scope"] == "https_and_wss_signaling_only"
    assert report["audio_attempted"] is False
    assert report["os_trust_changed"] is False
    assert "directions" not in report
