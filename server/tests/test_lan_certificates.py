"""Exercise real offline certificates, without changing trust or using sockets."""
import importlib.util
import json
from pathlib import Path
import socket
import shutil
import ssl
import subprocess
import sys

import pytest


SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
spec = importlib.util.spec_from_file_location("prepare_lan_test", SCRIPTS / "prepare_lan_test.py")
lan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lan)
sys.modules.setdefault("prepare_lan_test", lan)
spec = importlib.util.spec_from_file_location("create_lan_certificate", SCRIPTS / "create_lan_certificate.py")
certificates = importlib.util.module_from_spec(spec)
spec.loader.exec_module(certificates)


@pytest.mark.parametrize("days", [0, 8, -1, True, 1.5])
def test_rejects_excessive_or_invalid_certificate_lifetime_before_writing(tmp_path, days):
    with pytest.raises(certificates.PreparationError, match="1 to 7"):
        certificates.generate("192.168.1.23", tmp_path / "work" / "tls", days, tmp_path)
    assert not (tmp_path / "work").exists()


def test_rejects_output_outside_private_work(tmp_path):
    with pytest.raises(certificates.PreparationError, match="ignored work"):
        certificates.generate("192.168.1.23", tmp_path / "published", project_root=tmp_path)
    assert not (tmp_path / "published").exists()


def test_never_overwrites_existing_certificates(tmp_path):
    output = tmp_path / "work" / "tls"
    output.mkdir(parents=True)
    sentinel = output / "key.pem"
    sentinel.write_text("keep private material")
    with pytest.raises(certificates.PreparationError, match="already exists"):
        certificates.generate("192.168.1.23", output, project_root=tmp_path)
    assert sentinel.read_text() == "keep private material"


def test_real_short_lived_certificates_validate_offline_and_discard_signer(tmp_path, monkeypatch):
    try:
        executable = certificates.find_openssl()
    except certificates.PreparationError:
        pytest.skip("Existing OpenSSL unavailable; no installation during tests")

    def no_socket(*_args, **_kwargs):
        raise AssertionError("Certificate generation must remain offline")

    monkeypatch.setattr(socket, "socket", no_socket)
    output = tmp_path / "work" / "tls"
    report = certificates.generate("192.168.1.23", output, 1, tmp_path)
    assert report["provider_calls"] == 0
    assert report["tls_verified_offline"] is True
    assert not report["issuer_signing_key_retained"]
    assert not report["trusted_on_this_device"] and not report["firewall_changed"]
    assert set(path.name for path in output.iterdir()) == {"ca.pem", "cert.pem", "key.pem", "charcha-lan-ca.cer", "manifest.json"}
    assert not list((tmp_path / "work").glob(".lan-tls-*"))
    assert (output / "charcha-lan-ca.cer").read_bytes() == ssl.PEM_cert_to_DER_cert((output / "ca.pem").read_text())
    assert len(report["issuer_sha256"]) == 64 and len(report["issuer_windows_thumbprint"]) == 40
    assert "PRIVATE KEY" not in json.dumps(report)
    lan.validate_tls("192.168.1.23", output / "cert.pem", output / "key.pem", output / "ca.pem")
    with pytest.raises(lan.PreparationError):
        lan.validate_tls("192.168.1.24", output / "cert.pem", output / "key.pem", output / "ca.pem")
    issuer = subprocess.run([executable, "x509", "-in", str(output / "ca.pem"), "-text", "-noout"],
                            check=True, capture_output=True, text=True, timeout=10).stdout
    assert "CA:TRUE, pathlen:0" in issuer
    assert "Name Constraints: critical" in issuer
    assert "IP:192.168.1.23/255.255.255.255" in issuer
    assert "TLS Web Server Authentication" in issuer
    leaf = subprocess.run([executable, "x509", "-in", str(output / "cert.pem"), "-text", "-noout"],
                          check=True, capture_output=True, text=True, timeout=10).stdout
    assert "CA:FALSE" in leaf and "IP Address:192.168.1.23" in leaf


def test_command_failure_never_exposes_openssl_output(tmp_path, monkeypatch, capsys):
    def fail(*_args, **_kwargs):
        raise subprocess.CalledProcessError(1, ["openssl"], output="SENSITIVE_OUTPUT", stderr="SENSITIVE_KEY")
    monkeypatch.setattr(certificates, "generate", fail)
    assert certificates.main(["--ip", "192.168.1.23", "--output", str(tmp_path)]) == 2
    error = capsys.readouterr().err
    assert "SENSITIVE" not in error and "preparation failed" in error


def test_firewall_dry_run_is_exact_peer_only_without_requiring_administrator():
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if not executable:
        pytest.skip("PowerShell unavailable for Windows firewall dry-run")
    result = subprocess.run([executable, "-NoProfile", "-File", str(SCRIPTS / "configure_lan_firewall.ps1"),
                             "-LocalIp", "192.168.1.7", "-PeerIp", "192.168.1.99"],
                            capture_output=True, text=True, timeout=20, check=True)
    report = json.loads(result.stdout)
    assert report["action"] == "plan_only"
    assert report["allowed_peer_ip"] == "192.168.1.99" and report["profile"] == "Private"
    assert report["tcp_ports"] == [8443, 8444, 7881] and report["udp_ports"] == [7882]
    assert len(report["rules"]) == 2 and report["rules"][0].endswith("-TCP") and report["rules"][1].endswith("-UDP")


@pytest.mark.parametrize("peer", ["8.8.8.8", "192.168.1.7", "192.168.1.99;bad"])
def test_firewall_plan_rejects_unsafe_or_self_target(peer):
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if not executable:
        pytest.skip("PowerShell unavailable for Windows firewall dry-run")
    result = subprocess.run([executable, "-NoProfile", "-File", str(SCRIPTS / "configure_lan_firewall.ps1"),
                             "-LocalIp", "192.168.1.7", "-PeerIp", peer],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode != 0
