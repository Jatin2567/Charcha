"""Prepare an opt-in, no-provider LAN audio stack; never starts services.

Default invocation is a dry run. TLS validation uses in-memory handshakes,
not sockets. Existing .env files and the system trust store are never changed.
"""
from __future__ import annotations

import argparse
import csv
import io
import ipaddress
import json
import os
from pathlib import Path
import secrets
import re
import ssl
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(value) for value in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
))


class PreparationError(ValueError):
    pass


def private_directory(path: Path) -> None:
    """Protect a new directory before writing credentials, including Windows ACLs."""
    path.mkdir(mode=0o700)
    if os.name != "nt":
        path.chmod(0o700)
        return
    result = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"],
                            capture_output=True, text=True, timeout=10, check=True)
    rows = list(csv.reader(io.StringIO(result.stdout)))
    sid = rows[0][-1].strip() if len(rows) == 1 and rows[0] else ""
    if not re.fullmatch(r"S-1-\d+(?:-\d+)+", sid):
        raise PreparationError("Could not identify the current Windows account for private key protection.")
    subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F"],
                   capture_output=True, timeout=10, check=True)


def validate_ip(value: str) -> str:
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError:
        raise PreparationError("Use the laptop's private LAN IPv4 address, without a URL or port.") from None
    if not any(address in network for network in PRIVATE_NETWORKS):
        raise PreparationError("Only RFC1918 private LAN addresses are accepted; no public, loopback or link-local host.")
    return str(address)


def validate_tls(address: str, certificate: Path, private_key: Path, ca: Path) -> None:
    """Verify chain, validity, IP SAN and key pair using only in-memory TLS."""
    for path in (certificate, private_key, ca):
        if not path.is_file() or path.stat().st_size > 1_048_576:
            raise PreparationError("Supply existing PEM certificate, private key and CA files under 1 MiB each.")
    try:
        server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        # An encrypted key must fail without prompting or reading a password.
        server.load_cert_chain(str(certificate), str(private_key), password=lambda: "")
        client = ssl.create_default_context(cafile=str(ca))
        client.check_hostname = True
        server_in, server_out = ssl.MemoryBIO(), ssl.MemoryBIO()
        client_in, client_out = ssl.MemoryBIO(), ssl.MemoryBIO()
        server_tls = server.wrap_bio(server_in, server_out, server_side=True)
        client_tls = client.wrap_bio(client_in, client_out, server_hostname=address)
        client_done = server_done = False
        for _ in range(32):
            if not client_done:
                try:
                    client_tls.do_handshake()
                    client_done = True
                except ssl.SSLWantReadError:
                    pass
            outgoing = client_out.read()
            if outgoing:
                server_in.write(outgoing)
            if not server_done:
                try:
                    server_tls.do_handshake()
                    server_done = True
                except ssl.SSLWantReadError:
                    pass
            outgoing = server_out.read()
            if outgoing:
                client_in.write(outgoing)
            if client_done and server_done:
                return
        raise PreparationError("The supplied TLS files could not complete an offline verification.")
    except (ssl.SSLError, OSError, ValueError):
        raise PreparationError("TLS verification failed: check the matching unencrypted key, valid certificate chain and exact LAN IP in the certificate's IP SAN.") from None


def plan(address: str) -> dict:
    address = validate_ip(address)
    return {
        "schema_version": 1,
        "prepared_only": True,
        "provider_calls": 0,
        "mode": "transport",
        "screening": "off",
        "frontend": f"https://{address}:8443/#/tests",
        "livekit": f"wss://{address}:8444",
        "lan_ports": {"tcp": [8443, 8444, 7881], "udp": [7882]},
        "requires": ["Docker Engine with Linux containers and Compose v2",
                     "Matching PEM key/certificate with this IPv4 in its IP SAN",
                     "Certificate issuer trusted on both test devices",
                     "Same trusted LAN with client isolation disabled",
                     "Host firewall permits only the test devices on the listed ports"],
        "not_verified": ["Docker build/start", "host port bindings and firewall",
                         "device trust", "WebRTC media routing", "human audio or latency"],
    }


def render(address: str, output: Path, project_root: Path = ROOT) -> dict[str, str]:
    """All generated credentials stay in private output, never in the manifest."""
    summary = plan(address)
    key, secret = "API" + secrets.token_hex(12), secrets.token_urlsafe(48)
    environment = {
        "ARTHA_MODE": "transport", "CORS_ORIGINS": f"https://{address}:8443",
        "LIVEKIT_URL": f"wss://{address}:8444", "LIVEKIT_INTERNAL_URL": "ws://livekit:7880",
        "LIVEKIT_API_KEY": key, "LIVEKIT_API_SECRET": secret,
        "GNANI_API_KEY": "", "EVON_API_KEY": "", "EVON_BASE_URL": "", "EVON_MODEL": "",
        "LOCAL_AUDIO_LAB_ENABLED": "false", "AUDIO_SCREENING_MODE": "off",
        "USAGE_SHOW_PRIVATE_BALANCE": "false", "USAGE_REQUIRE_FLOW_APPROVAL": "true",
        "USAGE_STT_SECONDS_PER_DAY": "0", "USAGE_STT_CONNECTIONS_PER_DAY": "0",
        "USAGE_MT_REQUESTS_PER_DAY": "0", "USAGE_MT_CHARACTERS_PER_DAY": "0",
        "USAGE_TTS_REQUESTS_PER_DAY": "0", "USAGE_TTS_CHARACTERS_PER_DAY": "0",
        "USAGE_VOICE_ENROLLMENTS_PER_DAY": "0", "USAGE_DB_PATH": "/app/data/usage.sqlite3",
        "MAX_ROOMS": "4", "MAX_PARTICIPANTS": "4", "ROOM_TTL_SECONDS": "3600",
    }
    root_relative = Path(os.path.relpath(project_root, output)).as_posix()
    logging = {"driver": "json-file", "options": {"max-size": "5m", "max-file": "2"}}
    common = {"restart": "no", "logging": logging, "stop_grace_period": "20s"}
    compose = {
        "name": "artha-mesh-lan-test",
        "services": {
            "livekit": {
                **common, "image": "livekit/livekit-server:v1.9.1",
                "command": ["--config", "/etc/livekit.yaml"],
                "volumes": ["./livekit.yaml:/etc/livekit.yaml:ro"],
                "ports": [f"{address}:7881:7881/tcp", f"{address}:7882:7882/udp"],
            },
            "api": {
                **common, "build": {"context": root_relative, "dockerfile": "Dockerfile.api"},
                "env_file": ["./api.env"], "volumes": ["usage-ledger:/app/data"],
                "depends_on": ["livekit"], "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "healthcheck": {"test": ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"],
                                "interval": "10s", "timeout": "5s", "retries": 6, "start_period": "10s"},
            },
            "web": {
                **common, "build": {"context": root_relative, "dockerfile": "Dockerfile.web"},
                "depends_on": {"api": {"condition": "service_healthy"}},
            },
            "edge": {
                **common, "image": "nginx:1.27-alpine",
                "volumes": ["./nginx.conf:/etc/nginx/conf.d/default.conf:ro", "./tls:/etc/artha-tls:ro"],
                "ports": [f"{address}:8443:8443/tcp", f"{address}:8444:8444/tcp"],
                "depends_on": ["web", "livekit"],
            },
        },
        "volumes": {"usage-ledger": {}},
    }
    tls = """    ssl_certificate /etc/artha-tls/cert.pem;
    ssl_certificate_key /etc/artha-tls/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    access_log off;
    server_tokens off;
"""
    nginx = "map $http_upgrade $artha_connection { default upgrade; '' close; }\n"
    for port, upstream in ((8443, "web:80"), (8444, "livekit:7880")):
        nginx += f"""server {{
    listen {port} ssl;
    server_name {address};
{tls}    client_max_body_size 12m;
    location / {{
        proxy_pass http://{upstream};
        proxy_http_version 1.1;
        proxy_set_header Host $http_host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $artha_connection;
        proxy_read_timeout 3600s;
        proxy_buffering off;
    }}
}}
"""
    livekit = (
        "port: 7880\nbind_addresses: [0.0.0.0]\ndevelopment: false\n"
        "rtc:\n  tcp_port: 7881\n  udp_port: 7882\n"
        f"  node_ip: {address}\n  use_external_ip: false\n"
        "  stun_servers: []\n  allow_tcp_fallback: true\n"
        "logging:\n  level: warn\n  pion_level: error\n"
        f"keys:\n  {key}: {secret}\n"
    )
    return {
        "compose.json": json.dumps(compose, indent=2) + "\n",
        "manifest.json": json.dumps(summary, indent=2) + "\n",
        "api.env": "# PRIVATE LOCAL-TEST CREDENTIALS. Never publish.\n" + "".join(f"{name}={value}\n" for name, value in environment.items()),
        "nginx.conf": nginx, "livekit.yaml": livekit,
    }


def prepare(address: str, certificate: Path, private_key: Path, ca: Path,
            output: Path, project_root: Path = ROOT) -> dict:
    address = validate_ip(address)
    output = output.resolve()
    project_root = project_root.resolve()
    work = (project_root / "work").resolve()
    if not work.is_relative_to(project_root) or not output.is_relative_to(work) or output == work:
        raise PreparationError("Choose a new output directory under this repository's ignored work/ directory.")
    if output.exists():
        raise PreparationError("Output already exists; preserve its credentials and choose a new directory.")
    validate_tls(address, certificate, private_key, ca)
    contents = render(address, output, project_root)
    manifest = plan(address)
    manifest["tls_verified_offline"] = True
    contents["manifest.json"] = json.dumps(manifest, indent=2) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".lan-prepare-", dir=output.parent) as temporary:
        staged = Path(temporary) / "generated"
        private_directory(staged)
        for name, content in contents.items():
            target = staged / name
            target.write_text(content, encoding="utf-8")
            target.chmod(0o600)
        tls = staged / "tls"
        tls.mkdir(mode=0o700)
        for name, source in (("cert.pem", certificate), ("key.pem", private_key), ("ca.pem", ca)):
            target = tls / name
            target.write_bytes(source.read_bytes())
            target.chmod(0o600)
        staged.rename(output)
    summary = plan(address)
    summary["tls_verified_offline"] = True
    summary["output"] = str(output)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip", required=True, help="Laptop's RFC1918 LAN IPv4")
    parser.add_argument("--write", action="store_true", help="Write private configuration after offline TLS verification; never start it")
    parser.add_argument("--certificate", type=Path)
    parser.add_argument("--private-key", type=Path)
    parser.add_argument("--ca", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "work" / "lan")
    args = parser.parse_args(argv)
    try:
        summary = plan(args.ip)
        if args.write:
            if not all((args.certificate, args.private_key, args.ca)):
                raise PreparationError("--write requires --certificate, --private-key and --ca.")
            summary = prepare(args.ip, args.certificate, args.private_key, args.ca, args.output)
        else:
            summary["dry_run"] = True
            summary["tls_verified_offline"] = False
        print(json.dumps(summary, indent=2))
        return 0
    except (PreparationError, OSError, subprocess.SubprocessError):
        # No paths or secret contents from an underlying parser are printed.
        import sys
        error = sys.exc_info()[1]
        print(str(error) if isinstance(error, PreparationError) else "Could not read or prepare local files; no service was started.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
