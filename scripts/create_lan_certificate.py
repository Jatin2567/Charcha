"""Create a short-lived, one-use development issuer and LAN TLS certificate.

Offline only: uses an existing OpenSSL executable, never installs software or
trust, changes a firewall, contacts a provider, or reads application settings.
The CA signing key is discarded before successful completion. Only the leaf
server key is retained in the ignored, private output directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import ssl
import subprocess
import tempfile

from prepare_lan_test import PreparationError, ROOT, private_directory, validate_ip, validate_tls


def find_openssl() -> str:
    executable = shutil.which("openssl")
    if executable:
        return executable
    candidate = Path("C:/Program Files/Git/mingw64/bin/openssl.exe")
    if candidate.is_file():
        return str(candidate)
    raise PreparationError("An existing OpenSSL executable is required; this script installs nothing.")


def generate(address: str, output: Path, days: int = 7, project_root: Path = ROOT) -> dict:
    address = validate_ip(address)
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 7:
        raise PreparationError("Certificate lifetime must be from 1 to 7 days.")
    output, project_root = output.resolve(), project_root.resolve()
    work = (project_root / "work").resolve()
    if not work.is_relative_to(project_root) or not output.is_relative_to(work) or output == work:
        raise PreparationError("Choose a new output directory under this repository's ignored work/ directory.")
    if output.exists():
        raise PreparationError("Output already exists; preserve it and choose a new directory.")
    executable = find_openssl()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".lan-tls-", dir=output.parent) as temporary:
        private = Path(temporary) / "private"
        private_directory(private)
        staged = private / "result"
        private_directory(staged)
        identifier = secrets.token_hex(6)
        root_config = private / "issuer.cnf"
        root_config.write_text(f"""[req]
prompt = no
distinguished_name = dn
x509_extensions = issuer
[dn]
CN = Artha Mesh LAN test {identifier}
O = Local development only
[issuer]
basicConstraints = critical,CA:TRUE,pathlen:0
keyUsage = critical,keyCertSign,cRLSign
extendedKeyUsage = serverAuth
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always
nameConstraints = critical,permitted;IP:{address}/255.255.255.255,permitted;DNS:{identifier}.invalid
""", encoding="ascii")
        leaf_config = private / "leaf.cnf"
        leaf_config.write_text(f"""[req]
prompt = no
distinguished_name = dn
req_extensions = leaf
[dn]
CN = Artha Mesh LAN test
[leaf]
basicConstraints = critical,CA:FALSE
keyUsage = critical,digitalSignature,keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = IP:{address}
""", encoding="ascii")

        def openssl(*args: str) -> None:
            subprocess.run([executable, *args], capture_output=True, timeout=30, check=True)

        openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-sha256",
                "-keyout", str(private / "issuer-key.pem"), "-out", str(staged / "ca.pem"),
                "-days", str(days + 1), "-config", str(root_config))
        openssl("req", "-new", "-newkey", "rsa:2048", "-nodes", "-sha256",
                "-keyout", str(staged / "key.pem"), "-out", str(private / "leaf.csr"),
                "-config", str(leaf_config))
        openssl("x509", "-req", "-in", str(private / "leaf.csr"),
                "-CA", str(staged / "ca.pem"), "-CAkey", str(private / "issuer-key.pem"),
                "-set_serial", str(secrets.randbits(159) or 1), "-days", str(days), "-sha256",
                "-extfile", str(leaf_config), "-extensions", "leaf", "-out", str(staged / "cert.pem"))
        validate_tls(address, staged / "cert.pem", staged / "key.pem", staged / "ca.pem")
        issuer_der = ssl.PEM_cert_to_DER_cert((staged / "ca.pem").read_text(encoding="ascii"))
        leaf_der = ssl.PEM_cert_to_DER_cert((staged / "cert.pem").read_text(encoding="ascii"))
        (staged / "artha-lan-ca.cer").write_bytes(issuer_der)
        summary = {
            "schema_version": 1, "record_type": "lan_certificate_preparation",
            "ip": address, "certificate_days": days, "issuer_days": days + 1,
            "issuer_sha256": hashlib.sha256(issuer_der).hexdigest().upper(),
            # Windows certificate-store identifier, not a signature algorithm.
            "issuer_windows_thumbprint": hashlib.sha1(issuer_der).hexdigest().upper(),
            "leaf_sha256": hashlib.sha256(leaf_der).hexdigest().upper(),
            "tls_verified_offline": True, "issuer_signing_key_retained": False,
            "trusted_on_this_device": False, "firewall_changed": False,
            "provider_calls": 0, "output": str(output),
            "public_certificate_for_other_device": str(output / "artha-lan-ca.cer"),
            "warning": "Development only. Trust is a separate device action. Remove this issuer after testing. Regenerate if the IP changes or the certificate expires.",
        }
        (staged / "manifest.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        for path in staged.iterdir():
            path.chmod(0o600)
        # The result retains its restrictive explicit Windows ACL after rename.
        staged.rename(output)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip", required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "work" / "lan-tls")
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(generate(args.ip, args.output, args.days), indent=2))
        return 0
    except (PreparationError, OSError, subprocess.SubprocessError) as error:
        import sys
        print(str(error) if isinstance(error, PreparationError) else
              "Local certificate preparation failed; no trust, firewall or service was changed.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
