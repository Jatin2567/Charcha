import copy
import importlib.util
import json
import os
from pathlib import Path
import socket

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


benchmark = load("evon_benchmark")
prepare = load("evon_prepare")
KEY = "private-test-key-not-a-real-key-123456"


def plan(**kwargs):
    return benchmark.build_plan(benchmark.load_cases(benchmark.DEFAULT_CORPUS, None), **kwargs)


def test_offline_default_reads_no_provider_environment_or_network(monkeypatch, capsys):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("offline plan accessed network/environment")

    class NoEnvironment(dict):
        def get(self, key, default=None):
            # argparse/gettext may inspect locale for its built-in help strings.
            if key in {"LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"}:
                return default
            return forbidden()

        __getitem__ = forbidden

    with monkeypatch.context() as context:
        context.setattr(os, "environ", NoEnvironment())
        context.setattr(socket, "socket", forbidden)
        context.setattr(httpx, "AsyncClient", forbidden)
        assert benchmark.main([]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["provider_calls_made"] == 0
    assert result["limits"]["requests"] == 2
    assert result["limits"]["automatic_retries"] == 0
    assert result["speech"] == {"stt": False, "tts": False, "voice_cloning": False}
    assert [case["id"] for case in result["cases"]] == ["hi-ta-01", "ta-hi-01"]
    assert result["cost"]["provider_actual_charge"] is None


@pytest.mark.parametrize("argv", [["--execute"], ["--execute", "--acknowledge-gpu-cost"],
                                  ["--execute", "--approve-plan", "wrong", "--acknowledge-gpu-cost"]])
def test_cli_never_connects_without_exact_approval(argv, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("unapproved network")
    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    assert benchmark.main(argv) == 2


def test_plan_hash_covers_content_budget_endpoint_and_model():
    base = plan()
    assert base == plan()
    for kwargs in [{"max_tokens": 300}, {"model": "different"}, {"endpoint": "http://127.0.0.1:9000/v1"},
                   {"timeout": 20}, {"wall_seconds": 100}]:
        assert plan(**kwargs)["plan_sha256"] != base["plan_sha256"]
    changed = copy.deepcopy(base)
    changed["cases"][0]["source_text"] += "changed"
    with pytest.raises(ValueError):
        benchmark.authorize(changed, changed["plan_sha256"], True)


@pytest.mark.parametrize("endpoint", ["http://example.com/v1", "https://user:pass@example.com/v1",
                                     "https://example.com/v1?key=secret", "https://example.com/#secret",
                                     "file:///tmp/model", "http://127.0.0.1:99999/v1"])
def test_rejects_insecure_or_secret_bearing_endpoints(endpoint):
    with pytest.raises(ValueError):
        plan(endpoint=endpoint)


@pytest.mark.parametrize("limits", [{"max_tokens": 513}, {"timeout": 61}, {"timeout": 0},
                                   {"wall_seconds": 601}, {"wall_seconds": 1}])
def test_rejects_unbounded_plans(limits):
    with pytest.raises(ValueError):
        plan(**limits)


async def test_success_is_response_receipt_not_semantic_acceptance():
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        assert request.headers["Authorization"] == "Bearer " + KEY
        assert body["stream"] is False
        assert body["chat_template_kwargs"] == {"enable_thinking": False}
        assert body["max_tokens"] == 256
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
            "content": "Some translation with 10; " + KEY}}]})

    manifest = plan()
    report = await benchmark.execute(manifest, "http://127.0.0.1:8001/v1", manifest["plan_sha256"], True,
                                     api_key=KEY, transport=httpx.MockTransport(handler))
    assert len(seen) == 2 and report["complete"]
    assert report["meaning_acceptance"] == "not_reviewed"
    assert report["results"][0]["status"] == "response_received"
    assert report["results"][0]["numeric_presence"] == {"10": True}
    assert report["actual_charge"] is None
    encoded = json.dumps(report)
    assert KEY not in encoded and "127.0.0.1" not in encoded
    assert "[REDACTED]" in encoded


@pytest.mark.parametrize("payload", [None, {}, {"choices": []},
    {"choices": [{"finish_reason": "length", "message": {"content": "truncated"}}]},
    {"choices": [{"finish_reason": "stop", "message": {"content": " "}}]},
    {"choices": [{"finish_reason": "stop", "message": {"content": "<think>reasoning</think>hello"}}]},
    {"choices": [{"finish_reason": "stop", "message": {"content": ["wrong"]}}]},
])
async def test_bad_responses_stop_after_one_attempt(payload):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=payload)
    manifest = plan()
    report = await benchmark.execute(manifest, "http://127.0.0.1:8001/v1", manifest["plan_sha256"], True,
                                     api_key=KEY, transport=httpx.MockTransport(handler))
    assert len(calls) == 1
    assert report["stopped_on_error"] and report["unattempted_cases"] == 1
    assert not report["complete"]


@pytest.mark.parametrize("kind", ["timeout", "http", "redirect", "oversize"])
async def test_errors_never_retry_or_export_upstream_secret(kind):
    calls = []
    def handler(request):
        calls.append(request)
        if kind == "timeout":
            raise httpx.ReadTimeout(KEY, request=request)
        if kind == "http":
            return httpx.Response(429, text=KEY)
        if kind == "redirect":
            return httpx.Response(302, headers={"Location": "https://elsewhere.invalid/" + KEY})
        return httpx.Response(200, content=b"x" * 131073)
    manifest = plan()
    report = await benchmark.execute(manifest, "http://127.0.0.1:8001/v1", manifest["plan_sha256"], True,
                                     api_key=KEY, transport=httpx.MockTransport(handler))
    assert len(calls) == 1 and report["stopped_on_error"]
    assert KEY not in json.dumps(report)


async def test_changed_endpoint_and_missing_key_rejected_before_connect():
    manifest = plan()
    with pytest.raises(ValueError):
        await benchmark.execute(manifest, "http://127.0.0.1:9000/v1", manifest["plan_sha256"], True,
                                api_key=KEY)
    with pytest.raises(ValueError):
        await benchmark.execute(manifest, "http://127.0.0.1:8001/v1", manifest["plan_sha256"], True,
                                api_key="")


def test_output_is_never_overwritten(tmp_path):
    target = tmp_path / "plan.json"
    assert benchmark.main(["--output", str(target)]) == 0
    original = target.read_bytes()
    assert benchmark.main(["--output", str(target)]) == 2
    assert target.read_bytes() == original


def valid_config():
    return {"image": "vllm/vllm-openai@sha256:" + "a" * 64,
            "model_revision": "b" * 40, "trust_remote_code": False, "platform": "linux/amd64",
            "model": benchmark.MODEL, "port": 8001}


def test_portable_config_requires_pins_and_binds_only_loopback():
    result = prepare.build_compose(valid_config())
    service = result["services"]["evon"]
    assert service["ports"] == ["127.0.0.1:8001:8000"]
    assert service["restart"] == "no"
    assert "--revision" in service["command"] and "--tokenizer-revision" in service["command"]
    assert "--trust-remote-code" not in service["command"]
    assert service["platform"] == "linux/amd64"
    assert service["env_file"] == [{"path": "credentials.env", "format": "raw", "required": True}]
    assert "VLLM_API_KEY" in service["entrypoint"][2]
    assert service["deploy"]["resources"]["reservations"]["devices"][0]["count"] == 1
    assert service["healthcheck"]["test"][-1].endswith("timeout=3)")


@pytest.mark.parametrize("change", [{"image": "vllm/vllm-openai:latest"}, {"model_revision": "main"},
                                    {"trust_remote_code": True}, {"platform": "linux/arm64"}, {"port": 80}, {"port": True},
                                    {"model": "unknown/model"}])
def test_portable_config_rejects_placeholders_unreviewed_code_and_invalid_inputs(change):
    config = valid_config() | change
    with pytest.raises(ValueError):
        prepare.build_compose(config)


def test_example_is_deliberately_not_executable_until_pins_verified():
    config = json.loads((ROOT / "deploy" / "evon" / "inputs.example.json").read_text())
    with pytest.raises(ValueError):
        prepare.build_compose(config)


def test_metadata_verified_inputs_match_evidence_without_claiming_runtime():
    config = json.loads((ROOT / "deploy" / "evon" / "inputs.verified-2026-10-28.json").read_text())
    evidence = json.loads((ROOT / "deploy" / "evon" / "pins.verified-2026-10-28.json").read_text())
    service = prepare.build_compose(config)["services"]["evon"]
    assert config["image"] == evidence["runtime"]["image"] == service["image"]
    assert config["model_revision"] == evidence["model"]["revision"]
    assert evidence["model"]["trust_remote_code"] is False
    assert evidence["runtime"]["model_load_verified"] is False
    assert evidence["runtime"]["container_started"] is False
    assert evidence["runtime"]["manifest_header_and_content_digest_match"] is True


@pytest.mark.parametrize("payload", [None, {}, {"choices": "not-list"}, {"choices": [None]},
    {"choices": [{"finish_reason": "stop", "message": {"role": "user", "content": "hello"}}]},
    {"choices": [{"finish_reason": "stop", "message": {"content": "hello", "refusal": "no"}}]},
    {"choices": [{"finish_reason": "stop", "message": {"content": "hello", "tool_calls": [{"id": "1"}]}}]},
    {"choices": [{"finish_reason": "stop", "message": {"content": "hello", "function_call": {"name": "x"}}}]},
    {"choices": [{"finish_reason": "stop", "message": {"content": "hello", "reasoning": "hidden"}}]},
    {"choices": [{"finish_reason": "stop", "message": {"content": "hello", "reasoning_content": "hidden"}}]},
    {"choices": [{"finish_reason": "stop", "message": {"content": "<|analysis|>hello"}}]},
    {"choices": [{"finish_reason": "stop", "message": {"content": "<analysis>hello"}}]},
    {"choices": [{"finish_reason": "stop", "message": {"content": "hello"}}] * 2},
    {"choices": [{"finish_reason": "stop", "message": {"content": "hello", "reasoning_content": ""}}]},
])
def test_standalone_response_contract_matches_application(payload):
    from artha_mesh.providers.evon import completed_translation as app_contract

    outcomes = []
    for contract in (app_contract, benchmark.completed_translation):
        try:
            outcomes.append(("accepted", contract(payload)))
        except ValueError:
            outcomes.append(("rejected", None))
    assert outcomes[0] == outcomes[1]
