"""Readiness continuations use MockTransport only; no GPU, secrets or providers."""
import asyncio
import importlib.util
import json
from pathlib import Path
import socket

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("modal_readiness_test_runner", ROOT / "scripts/check_modal_readiness.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)
BASE = "https://owned-stage.modal.run"
PRIVATE = {"api_key": "private-bearer-test-value", "modal_key": "private-modal-key-test-value",
           "modal_secret": "private-modal-secret-test-value"}


def assert_redacted(report, *extra):
    encoded = json.dumps(report)
    for value in (*PRIVATE.values(), *extra):
        assert value not in encoded


def test_default_plan_does_not_read_credentials_environment_or_network(monkeypatch, capsys):
    def forbidden(*_a, **_k):
        pytest.fail("Planning must not load secrets or construct a network client")
    monkeypatch.setattr(check, "load_credentials", forbidden)
    monkeypatch.setattr(check, "check_readiness", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    assert check.main([]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["plan_only"] and report["network_requests_made"] == 0
    assert report["limits"] == {"wall_seconds": 960, "same_request_303_continuations": 6,
                                "maximum_http_requests": 7, "automatic_failure_retries": 0}


@pytest.mark.parametrize("endpoint", ["http://owned-stage.modal.run", "https://modal.run",
    BASE + "/", BASE + "/v1", BASE + "?private", BASE + "?", BASE + "#",
    "https://user:private@owned-stage.modal.run", BASE + ":8443", BASE + ":bad",
    "https://evil.modal.run.attacker.invalid", BASE + "\n", "https://-bad.modal.run"])
def test_base_is_exact_https_modal_origin_without_path_or_query(endpoint):
    with pytest.raises(check.Rejected):
        check.build_plan(endpoint)


@pytest.mark.parametrize("wall,redirects", [(961, 6), (0, 6), (float("nan"), 6), (960, 7), (960, -1)])
def test_limits_reject_unbounded_work(wall, redirects):
    with pytest.raises(check.Rejected):
        check.build_plan(BASE, wall_seconds=wall, max_redirects=redirects)


@pytest.mark.parametrize("ack", [[], ["--acknowledge-gpu-cost"]])
def test_run_requires_both_explicit_flags_and_real_host_before_secret_read(monkeypatch, capsys, ack):
    monkeypatch.setattr(check, "load_credentials", lambda *_a: pytest.fail("Credentials read"))
    args = ["--run", *ack]
    if not ack:
        args += ["--base-url", BASE]
    assert check.main(args) == 2
    output = capsys.readouterr().out
    assert all(value not in output for value in PRIVATE.values())


async def test_one_health_request_uses_both_auth_layers_and_redacts_response_body():
    seen = []
    def handler(request):
        seen.append(request)
        assert str(request.url) == BASE + "/health"
        assert request.headers["Authorization"] == "Bearer " + PRIVATE["api_key"]
        assert request.headers["Modal-Key"] == PRIVATE["modal_key"]
        assert request.headers["Modal-Secret"] == PRIVATE["modal_secret"]
        return httpx.Response(200, text=PRIVATE["api_key"])
    result = await check.check_readiness(BASE, PRIVATE, transport=httpx.MockTransport(handler))
    assert result["ready"] and result["failure_class"] is None
    assert result["http_requests"] == 1 and result["followed_303_continuations"] == 0
    assert len(seen) == 1
    assert_redacted(result)


@pytest.mark.parametrize("location", ["/health?__modal_result=private-result-token",
    BASE + "/health?__modal_result=private-result-token", "?__modal_result=private-result-token",
    "https://owned-stage.modal.run:443/health?__modal_result=private-result-token"])
async def test_303_continues_only_the_original_health_request_and_never_exports_query(location):
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(303, headers={"Location": location}) if len(seen) == 1 else httpx.Response(200)
    result = await check.check_readiness(BASE, PRIVATE, transport=httpx.MockTransport(handler))
    assert result["ready"] and result["http_requests"] == 2
    assert result["followed_303_continuations"] == 1
    assert [row["status_code"] for row in result["status_history"]] == [303, 200]
    assert str(seen[1].url).endswith("/health?__modal_result=private-result-token")
    assert seen[1].headers["Modal-Secret"] == PRIVATE["modal_secret"]
    assert_redacted(result, "private-result-token", "__modal_result", location)


@pytest.mark.parametrize("location", ["https://attacker.invalid/health?secret=private",
    "https://other.modal.run/health", "/v1/chat/completions?private", "/health/", "/%68ealth",
    "http://owned-stage.modal.run/health", "https://owned-stage.modal.run:8443/health",
    "https://user:private@owned-stage.modal.run/health", "/health#private", "//evil.invalid/health",
    "/health\\private", "", None])
async def test_unapproved_303_destination_stops_without_forwarding_any_credentials(location):
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(303, headers={} if location is None else {"Location": location})
    result = await check.check_readiness(BASE, PRIVATE, transport=httpx.MockTransport(handler))
    assert len(seen) == 1 and not result["ready"]
    assert result["failure_class"] == "continuation_destination"
    assert_redacted(result, "private")


def test_control_character_continuation_is_rejected_before_url_resolution():
    with pytest.raises(check.Rejected):
        check.continuation_url(BASE, BASE + "/health", "/health\nprivate")


@pytest.mark.parametrize("status", [301, 302, 307, 308, 401, 403, 429, 500, 503])
async def test_other_statuses_are_not_followed_or_retried(status):
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(status, headers={"Location": BASE + "/health?private"}, text=PRIVATE["modal_secret"])
    result = await check.check_readiness(BASE, PRIVATE, transport=httpx.MockTransport(handler))
    assert len(seen) == result["http_requests"] == 1
    assert not result["ready"] and result["failure_class"] == "http_status"
    assert_redacted(result)


async def test_seventh_303_exhausts_six_continuations_without_new_request_retry():
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(303, headers={"Location": "/health?private=" + str(len(seen))})
    result = await check.check_readiness(BASE, PRIVATE, transport=httpx.MockTransport(handler))
    assert len(seen) == result["http_requests"] == 7
    assert result["followed_303_continuations"] == 6
    assert not result["ready"] and result["failure_class"] == "continuation_limit"
    assert_redacted(result, "?private")


@pytest.mark.parametrize("failure,expected", [(httpx.ReadTimeout, "timeout"), (httpx.ConnectError, "request_failed")])
async def test_failed_request_is_redacted_and_never_retried(failure, expected):
    seen = []
    def handler(request):
        seen.append(request)
        raise failure(PRIVATE["api_key"] + str(request.url), request=request)
    result = await check.check_readiness(BASE, PRIVATE, transport=httpx.MockTransport(handler))
    assert len(seen) == 1 and result["failure_class"] == expected
    assert_redacted(result)


async def test_total_wall_deadline_cancels_hanging_request_without_retry():
    seen = []
    async def handler(request):
        seen.append(request)
        await asyncio.Event().wait()
    result = await check.check_readiness(BASE, PRIVATE, wall_seconds=.01,
                                         transport=httpx.MockTransport(handler))
    assert len(seen) == 1 and result["failure_class"] == "timeout"
    assert result["wall_seconds"] < 1


async def test_elapsed_deadline_prevents_another_303_continuation_request():
    seen = []
    times = iter([0, 0, 960, 960, 960])
    def handler(request):
        seen.append(request)
        return httpx.Response(303, headers={"Location": "/health?private"})
    result = await check.check_readiness(BASE, PRIVATE, clock=lambda: next(times),
                                         transport=httpx.MockTransport(handler))
    assert len(seen) == 1 and result["failure_class"] == "timeout"


def test_private_json_must_be_under_ignored_work_and_read_only_when_explicit(tmp_path):
    (tmp_path / "work").mkdir()
    file = tmp_path / "work/client.json"
    file.write_text(json.dumps(PRIVATE))
    assert check.load_credentials(file, root=tmp_path) == PRIVATE
    assert json.loads(file.read_text()) == PRIVATE
    for path in (tmp_path / "client.json", tmp_path / "work/../client.json", tmp_path / "work/client.env"):
        with pytest.raises(check.Rejected):
            check.load_credentials(path, root=tmp_path)


@pytest.mark.parametrize("value", [{}, {**PRIVATE, "extra": "value"}, {**PRIVATE, "modal_secret": ""},
    {**PRIVATE, "api_key": "header\ninjection"}, {**PRIVATE, "api_key": 123}])
def test_incomplete_or_unsafe_authentication_is_rejected_without_exposing_values(value):
    with pytest.raises(check.Rejected) as issue:
        check.authentication(value)
    assert PRIVATE["modal_secret"] not in str(issue.value)
