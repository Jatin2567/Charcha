"""No-network coverage for two independent authentication layers on Modal."""
from contextlib import asynccontextmanager
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

from charcha.config import Settings
from charcha.errors import ProviderError
from charcha.providers.evon import EvonTranslator, modal_proxy_headers


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("modal_auth_benchmark", ROOT / "scripts" / "evon_benchmark.py")
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)
ENDPOINT = "https://private-test--charcha-evon-serve.modal.run/v1"
API_KEY = "test-vllm-private-bearer-value-123456789"
MODAL_KEY = "test-modal-proxy-key-123456789"
MODAL_SECRET = "test-modal-proxy-secret-123456789"


class UsageDouble:
    def __init__(self):
        self.operations = []

    def require_live(self):
        pass

    @asynccontextmanager
    async def operation(self, amounts):
        self.operations.append(amounts)
        yield


def settings(**changes):
    return Settings(_env_file=None, **{
        "mode": "live", "evon_base_url": ENDPOINT, "evon_model": benchmark.MODEL,
        "evon_api_key": API_KEY, "evon_modal_key": MODAL_KEY,
        "evon_modal_secret": MODAL_SECRET, **changes,
    })


def payload(text="A draft translation"):
    return {"choices": [{"finish_reason": "stop", "message": {"content": text}}]}


@pytest.mark.parametrize("helper", [modal_proxy_headers, benchmark.modal_proxy_headers])
@pytest.mark.parametrize("endpoint,key,secret", [
    (ENDPOINT, MODAL_KEY, ""), (ENDPOINT, "", MODAL_SECRET),
    (ENDPOINT, MODAL_KEY + "\r\nInjected: yes", MODAL_SECRET),
    (ENDPOINT, MODAL_KEY, "space is invalid"),
    ("https://modal.run/v1", MODAL_KEY, MODAL_SECRET),
    ("https://not-modal.run/v1", MODAL_KEY, MODAL_SECRET),
    ("https://example.modal.run.attacker.invalid/v1", MODAL_KEY, MODAL_SECRET),
    ("http://example.modal.run/v1", MODAL_KEY, MODAL_SECRET),
    ("http://127.0.0.1:8001/v1", MODAL_KEY, MODAL_SECRET),
    ("https://example.modal.run:8443/v1", MODAL_KEY, MODAL_SECRET),
    ("https://user:pass@example.modal.run/v1", MODAL_KEY, MODAL_SECRET),
    (ENDPOINT + "?token=private", MODAL_KEY, MODAL_SECRET),
    (ENDPOINT + "#private", MODAL_KEY, MODAL_SECRET),
])
def test_proxy_pair_rejects_wrong_destinations_and_header_injection(helper, endpoint, key, secret):
    with pytest.raises(ValueError) as issue:
        helper(endpoint, key, secret)
    assert MODAL_KEY not in str(issue.value) and MODAL_SECRET not in str(issue.value)


def test_valid_auth_matches_standalone_and_remains_private_in_settings():
    expected = {"Modal-Key": MODAL_KEY, "Modal-Secret": MODAL_SECRET}
    assert modal_proxy_headers(ENDPOINT, MODAL_KEY, MODAL_SECRET) == expected
    assert benchmark.modal_proxy_headers(ENDPOINT, MODAL_KEY, MODAL_SECRET) == expected
    assert modal_proxy_headers("http://127.0.0.1:8001/v1") == {}
    encoded = settings().model_dump_json()
    assert API_KEY not in encoded and MODAL_KEY not in encoded and MODAL_SECRET not in encoded


@pytest.mark.parametrize("changes", [
    {"evon_modal_key": ""}, {"evon_modal_secret": ""},
    {"evon_base_url": "https://other.invalid/v1"},
])
async def test_adapter_configuration_failure_precedes_reservation_and_network(changes):
    usage = UsageDouble()
    translator = EvonTranslator(settings(**changes), usage)
    await translator.client.aclose()
    seen = []
    translator.client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: seen.append(request)))
    try:
        with pytest.raises(ProviderError) as issue:
            await translator.translate("An ordinary greeting", "hi", "ta")
        assert not usage.operations and not seen
        assert MODAL_KEY not in str(issue.value) and MODAL_SECRET not in str(issue.value)
    finally:
        await translator.aclose()


async def test_adapter_sends_both_auth_layers_and_never_follows_redirects():
    seen = []

    def handler(request):
        seen.append(request)
        assert request.headers["Authorization"] == "Bearer " + API_KEY
        assert request.headers["Modal-Key"] == MODAL_KEY
        assert request.headers["Modal-Secret"] == MODAL_SECRET
        return httpx.Response(307, headers={"Location": "https://attacker.invalid/" + MODAL_SECRET})

    usage = UsageDouble()
    translator = EvonTranslator(settings(), usage)
    assert translator.client.follow_redirects is False
    await translator.client.aclose()
    translator.client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)
    try:
        with pytest.raises(ProviderError) as issue:
            await translator.translate("An ordinary greeting", "hi", "ta")
        assert len(seen) == 1 and len(usage.operations) == 1
        assert MODAL_SECRET not in str(issue.value)
    finally:
        await translator.aclose()


@pytest.mark.parametrize("credential", [API_KEY, MODAL_KEY, MODAL_SECRET])
async def test_adapter_never_returns_a_reflected_credential(credential):
    translator = EvonTranslator(settings(), UsageDouble())
    await translator.client.aclose()
    translator.client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=payload("translation " + credential))))
    try:
        with pytest.raises(ProviderError) as issue:
            await translator.translate("An ordinary greeting", "hi", "ta")
        assert credential not in str(issue.value)
    finally:
        await translator.aclose()


async def test_adapter_direct_vllm_without_modal_credentials_still_works():
    seen = []

    def handler(request):
        seen.append(request)
        assert "Modal-Key" not in request.headers and "Modal-Secret" not in request.headers
        return httpx.Response(200, json=payload())

    translator = EvonTranslator(settings(evon_base_url="http://127.0.0.1:8001/v1",
                                        evon_modal_key="", evon_modal_secret=""), UsageDouble())
    await translator.client.aclose()
    translator.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        assert await translator.translate("An ordinary greeting", "hi", "ta") == "A draft translation"
        assert len(seen) == 1
    finally:
        await translator.aclose()


def planned(endpoint=ENDPOINT):
    return benchmark.build_plan(benchmark.load_cases(benchmark.DEFAULT_CORPUS, None), endpoint=endpoint)


@pytest.mark.parametrize("key,secret", [(MODAL_KEY, ""), ("", MODAL_SECRET)])
async def test_benchmark_incomplete_pair_cannot_create_a_client(monkeypatch, key, secret):
    def forbidden(**kwargs):
        raise AssertionError("credentials must fail before creating the HTTP client")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    plan = planned()
    with pytest.raises(ValueError):
        await benchmark.execute(plan, ENDPOINT, plan["plan_sha256"], True, api_key=API_KEY,
                                modal_key=key, modal_secret=secret)


async def test_benchmark_secrets_are_sent_only_to_modal_and_redacted_from_output():
    seen = []

    def handler(request):
        seen.append(request)
        assert request.headers["Modal-Key"] == MODAL_KEY
        assert request.headers["Modal-Secret"] == MODAL_SECRET
        assert request.headers["Authorization"] == "Bearer " + API_KEY
        return httpx.Response(200, json=payload("10 " + " ".join((API_KEY, MODAL_KEY, MODAL_SECRET))))

    plan = planned()
    report = await benchmark.execute(plan, ENDPOINT, plan["plan_sha256"], True, api_key=API_KEY,
                                     modal_key=MODAL_KEY, modal_secret=MODAL_SECRET,
                                     transport=httpx.MockTransport(handler))
    assert report["complete"] and len(seen) == 2
    encoded = json.dumps(report)
    assert all(credential not in encoded for credential in (API_KEY, MODAL_KEY, MODAL_SECRET))
    assert "[REDACTED]" in encoded


async def test_benchmark_modal_credentials_cannot_go_to_other_hosts(monkeypatch):
    def forbidden(**kwargs):
        raise AssertionError("wrong host must fail before creating the HTTP client")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    endpoint = "https://elsewhere.invalid/v1"
    plan = planned(endpoint)
    with pytest.raises(ValueError):
        await benchmark.execute(plan, endpoint, plan["plan_sha256"], True, api_key=API_KEY,
                                modal_key=MODAL_KEY, modal_secret=MODAL_SECRET)


async def test_benchmark_proxy_redirect_stops_without_leaking_secrets():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(307, headers={"Location": "https://attacker.invalid/" + MODAL_SECRET},
                              text=MODAL_KEY)

    plan = planned()
    report = await benchmark.execute(plan, ENDPOINT, plan["plan_sha256"], True, api_key=API_KEY,
                                     modal_key=MODAL_KEY, modal_secret=MODAL_SECRET,
                                     transport=httpx.MockTransport(handler))
    assert not report["complete"] and len(seen) == 1
    assert report["results"][0]["http_status"] == 307
    assert MODAL_SECRET not in json.dumps(report) and MODAL_KEY not in json.dumps(report)
