"""No sockets, Docker or provider access: preparation and local TLS only."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "prepare_lan_test.py"
spec = importlib.util.spec_from_file_location("lan_preparation", SCRIPT)
lan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lan)


@pytest.mark.parametrize("address", ["127.0.0.1", "0.0.0.0", "8.8.8.8", "169.254.1.3", "::1", "100.64.0.1", "https://192.168.1.3", "192.168.1.3\nfoo", "224.0.0.1"])
def test_rejects_non_lan_and_injected_addresses(address):
    with pytest.raises(lan.PreparationError):
        lan.plan(address)


def test_plan_is_safe_without_writing_or_tls(tmp_path, capsys):
    output = tmp_path / "not-created"
    assert lan.main(["--ip", "192.168.1.23", "--output", str(output)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["dry_run"] and not report["tls_verified_offline"]
    assert report["mode"] == "transport" and report["provider_calls"] == 0
    assert not output.exists()
    assert "API_KEY" not in json.dumps(report)


def test_requires_certificate_inputs_before_write(tmp_path, capsys):
    assert lan.main(["--ip", "192.168.1.23", "--write", "--output", str(tmp_path / "x")]) == 2
    assert "requires" in capsys.readouterr().err
    assert not (tmp_path / "x").exists()


def test_runtime_has_no_external_provider_or_public_private_api(tmp_path, monkeypatch):
    monkeypatch.setenv("GNANI_API_KEY", "must-not-inherit-this-key")
    monkeypatch.setenv("ARTHA_MODE", "live")
    output = tmp_path / "work" / "lan"
    rendered = lan.render("192.168.1.23", output, tmp_path)
    compose = json.loads(rendered["compose.json"])
    env = dict(line.split("=", 1) for line in rendered["api.env"].splitlines() if "=" in line)
    assert env["ARTHA_MODE"] == "transport"
    assert env["GNANI_API_KEY"] == env["EVON_API_KEY"] == env["EVON_BASE_URL"] == env["EVON_MODEL"] == ""
    assert env["LOCAL_AUDIO_LAB_ENABLED"] == "false"
    assert env["AUDIO_SCREENING_MODE"] == "off"
    assert env["USAGE_SHOW_PRIVATE_BALANCE"] == "false"
    assert env["CORS_ORIGINS"] == "https://192.168.1.23:8443"
    assert env["LIVEKIT_INTERNAL_URL"] == "ws://livekit:7880"
    assert env["LIVEKIT_URL"] == "wss://192.168.1.23:8444"
    assert all(value == "0" for key, value in env.items() if key.endswith("_PER_DAY"))
    assert "ports" not in compose["services"]["api"]
    assert "ports" not in compose["services"]["web"]
    assert compose["services"]["livekit"]["ports"] == ["192.168.1.23:7881:7881/tcp", "192.168.1.23:7882:7882/udp"]
    assert "7880:" not in rendered["compose.json"]
    assert "must-not-inherit-this-key" not in str(rendered)
    assert "stun_servers: []" in rendered["livekit.yaml"]
    assert "use_external_ip: false" in rendered["livekit.yaml"]
    assert "node_ip: 192.168.1.23" in rendered["livekit.yaml"]
    assert env["LIVEKIT_API_SECRET"] in rendered["livekit.yaml"]
    assert env["LIVEKIT_API_SECRET"] not in rendered["manifest.json"]
    assert env["LIVEKIT_API_SECRET"] not in rendered["compose.json"]
    other = lan.render("192.168.1.23", output, tmp_path)
    assert other["api.env"] != rendered["api.env"]


def test_rejects_output_outside_ignored_work_before_reading_cert(tmp_path):
    missing = tmp_path / "missing.pem"
    with pytest.raises(lan.PreparationError, match="ignored work"):
        lan.prepare("192.168.1.23", missing, missing, missing, tmp_path / "published", tmp_path)


def test_existing_output_is_not_overwritten(tmp_path):
    output = tmp_path / "work" / "lan"
    output.mkdir(parents=True)
    sentinel = output / "keep"
    sentinel.write_text("keep")
    missing = tmp_path / "missing.pem"
    with pytest.raises(lan.PreparationError, match="already exists"):
        lan.prepare("192.168.1.23", missing, missing, missing, output, tmp_path)
    assert sentinel.read_text() == "keep"


@pytest.fixture
def certificate(tmp_path):
    # Optional existing executable, not an installation or a trust-store change.
    executable = shutil.which("openssl")
    if not executable:
        candidate = Path("C:/Program Files/Git/mingw64/bin/openssl.exe")
        if candidate.is_file():
            executable = str(candidate)
    if not executable:
        pytest.skip("OpenSSL executable unavailable for ephemeral certificate fixture")
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run([executable, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                    "-keyout", str(key), "-out", str(cert), "-days", "1",
                    "-subj", "/CN=LAN-test-only",
                    "-addext", "subjectAltName=IP:192.168.1.23"],
                   check=True, capture_output=True, timeout=15)
    return cert, key


def test_tls_verification_rejects_wrong_ip_without_network(certificate, monkeypatch):
    import socket

    def no_network(*_args, **_kwargs):
        raise AssertionError("TLS preparation must never open a socket")

    monkeypatch.setattr(socket, "socket", no_network)
    cert, key = certificate
    lan.validate_tls("192.168.1.23", cert, key, cert)
    with pytest.raises(lan.PreparationError, match="TLS verification failed"):
        lan.validate_tls("192.168.1.24", cert, key, cert)


def test_bad_key_or_cert_cannot_write_stack(tmp_path, certificate):
    cert, _key = certificate
    bad = tmp_path / "bad.pem"
    bad.write_text("PRIVATE-MATERIAL-MUST-NOT-APPEAR-IN-ERROR")
    output = tmp_path / "work" / "lan"
    with pytest.raises(lan.PreparationError) as exc:
        lan.prepare("192.168.1.23", cert, bad, cert, output, tmp_path)
    assert "PRIVATE-MATERIAL" not in str(exc.value)
    assert not output.exists()


def test_prepared_stack_copies_only_supplied_tls_and_redacts_report(tmp_path, certificate):
    cert, key = certificate
    output = tmp_path / "work" / "lan"
    report = lan.prepare("192.168.1.23", cert, key, cert, output, tmp_path)
    assert report["tls_verified_offline"] is True
    assert json.loads((output / "manifest.json").read_text())["tls_verified_offline"] is True
    assert (output / "tls" / "cert.pem").read_bytes() == cert.read_bytes()
    assert (output / "tls" / "key.pem").read_bytes() == key.read_bytes()
    assert "PRIVATE KEY" not in json.dumps(report)
    assert "LIVEKIT_API_SECRET" not in json.dumps(report)
    assert report["prepared_only"]
