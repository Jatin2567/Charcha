"""Production setup checks stay static and never reveal operator credentials."""
import importlib.util
import json
from pathlib import Path

import pytest
from artha_mesh.config import Settings
from artha_mesh.services.readiness import production_configuration_issues, readiness_snapshot


def production_settings(**overrides):
    values = {
        "mode": "live",
        "usage_require_flow_approval": True,
        "usage_show_private_balance": False,
        "livekit_url": "wss://rtc.artha.in",
        "livekit_internal_url": "ws://127.0.0.1:7880",
        "livekit_api_key": "server-generated-key",
        "livekit_api_secret": "x" * 48,
        "gnani_api_key": "private-gnani-credential",
        "evon_base_url": "http://evon:8001/v1",
        "evon_model": "operator-served-evon-model",
        "cors_origins": ["https://meet.artha.in"],
    }
    values.update(overrides)
    return Settings(**values, _env_file=None)


def issue_keys(settings):
    return {item["key"] for item in production_configuration_issues(settings)}


def test_production_allows_colocated_private_services_but_does_not_claim_access():
    settings = production_settings()
    assert production_configuration_issues(settings) == []
    report = readiness_snapshot(settings)
    assert report["configuration_issues"] == []
    assert report["provider_verification"] == "not_checked"
    assert all(item["status"] == "manual" for item in report["deployment_checks"])
    assert "private-gnani-credential" not in json.dumps(report)


@pytest.mark.parametrize(("name", "value", "key"), [
    ("mode", "demo", "ARTHA_MODE"),
    ("usage_require_flow_approval", False, "USAGE_REQUIRE_FLOW_APPROVAL"),
    ("usage_show_private_balance", True, "USAGE_SHOW_PRIVATE_BALANCE"),
    ("livekit_url", "ws://rtc.artha.in", "LIVEKIT_URL"),
    ("livekit_url", "wss://127.0.0.1:7880", "LIVEKIT_URL"),
    ("livekit_url", "wss://localhost.", "LIVEKIT_URL"),
    ("livekit_url", "wss://rtc.example", "LIVEKIT_URL"),
    ("livekit_url", "wss://rtc.example.com", "LIVEKIT_URL"),
    ("livekit_url", "wss://bad host.artha.in", "LIVEKIT_URL"),
    ("livekit_url", "wss://rtc.artha.in:invalid", "LIVEKIT_URL"),
    ("livekit_internal_url", "ws://public.artha.in:7880", "LIVEKIT_INTERNAL_URL"),
    ("livekit_api_key", "devkey", "LIVEKIT_API_KEY"),
    ("livekit_api_secret", "secret", "LIVEKIT_API_SECRET"),
    ("gnani_api_key", "   ", "GNANI_API_KEY"),
    ("evon_base_url", "http://gpu.artha.in/v1", "EVON_BASE_URL"),
    ("evon_base_url", "https://credential@mt.artha.in/v1", "EVON_BASE_URL"),
    ("evon_base_url", "https://mt.artha.in/v1?key=private", "EVON_BASE_URL"),
    ("evon_base_url", "https://mt.artha.in/v1#private", "EVON_BASE_URL"),
    ("evon_model", "", "EVON_MODEL"),
    ("gnani_stt_url", "ws://provider.artha.in/stt", "GNANI_STT_URL"),
    ("gnani_tts_url", "https://provider.artha.in/tts", "GNANI_TTS_URL"),
    ("gnani_embedding_url", "http://provider.artha.in/embedding", "GNANI_EMBEDDING_URL"),
    ("cors_origins", [], "CORS_ORIGINS"),
    ("cors_origins", ["*"], "CORS_ORIGINS"),
    ("cors_origins", ["http://localhost:5173"], "CORS_ORIGINS"),
    ("cors_origins", ["https://meet.artha.in/path"], "CORS_ORIGINS"),
    ("cors_origins", ["https://meet.artha.in", "https://*.artha.in"], "CORS_ORIGINS"),
])
def test_production_flags_invalid_or_development_configuration(name, value, key):
    assert key in issue_keys(production_settings(**{name: value}))


def test_issues_never_echo_sensitive_configuration_values():
    marker = "do-not-display-this-credential"
    settings = production_settings(
        evon_base_url=f"https://{marker}@gpu.artha.in/v1?key={marker}",
        livekit_api_secret=marker,
        gnani_api_key=marker,
        cors_origins=[f"https://{marker}@meet.artha.in"],
    )
    encoded = json.dumps(readiness_snapshot(settings))
    assert marker not in encoded
    assert "gpu.artha.in" not in encoded


def load_checker():
    path = Path(__file__).resolve().parents[2] / "scripts" / "check_config.py"
    spec = importlib.util.spec_from_file_location("artha_config_checker", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_configuration_cli_production_and_local_modes(capsys, monkeypatch):
    checker = load_checker()
    monkeypatch.setattr(checker, "Settings", lambda: production_settings())
    assert checker.main(["--production"]) == 0
    output = capsys.readouterr().out
    assert "checks passed" in output
    assert "private-gnani-credential" not in output
    monkeypatch.setattr(checker, "Settings", lambda: Settings(mode="demo", _env_file=None))
    assert checker.main([]) == 0
    capsys.readouterr()
    assert checker.main(["--production"]) == 1
    assert "No provider calls were made" in capsys.readouterr().out


def test_configuration_cli_redacts_validation_error_input(capsys, monkeypatch):
    checker = load_checker()

    def invalid_settings():
        return Settings(mode="do-not-display-invalid-value", _env_file=None)

    monkeypatch.setattr(checker, "Settings", invalid_settings)
    assert checker.main([]) == 1
    output = capsys.readouterr().out
    assert "do-not-display-invalid-value" not in output
    assert "invalid configuration" in output
