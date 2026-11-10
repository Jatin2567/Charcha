"""Prepare a private, transport-only VM bundle behind a Google run.app URL.

This command never creates a cloud resource, starts a container or reads server/.env.
Cloud Run must reach the VM's private web listener using Direct VPC egress.
"""
from __future__ import annotations

import argparse
import copy
import ipaddress
import json
import os
import re
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from prepare_deployment import (
    PROJECT_ROOT,
    PreparationError,
    json_text,
    read_env,
    runtime_env,
)


def validate(origin: str, public_ip: str, private_ip: str) -> tuple[str, str, str]:
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)*\.run\.app", parsed.hostname)
        or parsed.netloc != parsed.hostname
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise PreparationError("Use the service's exact HTTPS run.app origin without a path or port.")
    try:
        public, private = ipaddress.ip_address(public_ip), ipaddress.ip_address(private_ip)
    except ValueError:
        raise PreparationError("Provide the VM's public and private IPv4 addresses.") from None
    private_ranges = tuple(ipaddress.ip_network(cidr) for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
    if public.version != 4 or not public.is_global or public.is_multicast or public.is_reserved or private.version != 4 or not any(private in cidr for cidr in private_ranges):
        raise PreparationError("Provide a global public IPv4 address and a non-loopback private IPv4 address.")
    return f"https://{parsed.hostname}", str(public), str(private)


def render(origin: str, public_ip: str, private_ip: str, identity: dict[str, str], root: Path = PROJECT_ROOT, output: Path | None = None) -> dict[str, str]:
    origin, public_ip, private_ip = validate(origin, public_ip, private_ip)
    host = urlsplit(origin).hostname
    # Fresh isolated credentials; no Gnani, Modal or historical account secrets.
    settings = runtime_env(
        {"app_domain": host, "livekit_domain": host},
        {key: identity[key] for key in ("REVIEWER_GPU_ALLOWED_ORIGINS",) if key in identity},
        "API" + secrets.token_hex(12), secrets.token_urlsafe(48), mode="transport",
    )
    settings.update({
        "CHARCHA_IDENTITY_PROVIDER": "keycloak",
        "CHARCHA_OIDC_ISSUER": origin + "/identity/realms/charcha",
        "CHARCHA_AUTH_CLIENT_ID": "charcha-web",
        "CHARCHA_AUTH_CLIENT_SECRET": secrets.token_urlsafe(48),
        # Remains locked until an operator provisions a password+OTP administrator.
        "CHARCHA_ADMIN_SUBJECT": "",
        "CHARCHA_MEETING_HOST_EMAIL": "jatin.aggarwal1098@gmail.com",
    })
    google_keys = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET")
    if bool(identity.get(google_keys[0])) != bool(identity.get(google_keys[1])):
        raise PreparationError("Both Google OAuth settings must be supplied together.")
    google_ready = all(identity.get(key) for key in google_keys)
    context = Path(os.path.relpath(root, output or root / "deploy/gcp/generated")).as_posix()
    db_password = secrets.token_urlsafe(36)
    bootstrap_password = secrets.token_urlsafe(36)
    realm = json.loads((root / "deploy/identity/charcha-realm.json").read_text())
    realm["identityProviders"][0]["enabled"] = google_ready
    # Resolve realm variables offline; do not rely on secrets in a public image.
    replacements = {
        "CHARCHA_PUBLIC_ORIGIN": origin,
        "CHARCHA_AUTH_CLIENT_SECRET": settings["CHARCHA_AUTH_CLIENT_SECRET"],
        **{key: identity.get(key, "") for key in google_keys},
    }
    def substitute(value):
        if isinstance(value, dict):
            return {key: substitute(item) for key, item in value.items()}
        if isinstance(value, list):
            return [substitute(item) for item in value]
        if isinstance(value, str):
            for key, item in replacements.items():
                value = value.replace("${" + key + "}", item)
        return value

    logging = {"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}}
    common = {"restart": "unless-stopped", "logging": logging, "stop_grace_period": "30s"}
    host_common = {**common, "network_mode": "host"}
    services = {
        "livekit": {**host_common, "image": "livekit/livekit-server:v1.9.1", "command": ["--config", "/etc/livekit.yaml"], "volumes": ["./livekit.yaml:/etc/livekit.yaml:ro"]},
        "api": {
            **host_common, "image": "charcha-api:deploy", "build": {"context": context, "dockerfile": "Dockerfile.api"},
            "env_file": [{"path": "./api.env", "format": "raw"}],
            "command": ["uvicorn", "charcha.main:app", "--host", "127.0.0.1", "--port", "8000", "--workers", "1", "--no-access-log", "--log-level", "warning", "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1"],
            "volumes": ["charcha-data:/app/data"], "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
            "healthcheck": {"test": ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"], "interval": "15s", "timeout": "5s", "retries": 5, "start_period": "20s"},
            "depends_on": {"livekit": {"condition": "service_started"}},
        },
        "web": {
            **host_common, "image": "charcha-web:deploy", "build": {"context": context, "dockerfile": "Dockerfile.web"},
            "volumes": ["./nginx.conf:/etc/nginx/conf.d/default.conf:ro"],
            "depends_on": {"api": {"condition": "service_healthy"}},
        },
        "identity-db": {
            **common, "image": "postgres:16-alpine", "networks": ["identity"],
            "env_file": [{"path": "./db.env", "format": "raw"}],
            "volumes": ["charcha-identity:/var/lib/postgresql/data"],
            "healthcheck": {"test": ["CMD-SHELL", "pg_isready -U charcha -d charcha"], "interval": "10s", "timeout": "5s", "retries": 15},
        },
        "identity": {
            **common, "image": "quay.io/keycloak/keycloak:26.7.5", "networks": ["identity"],
            "command": ["start", "--import-realm"],
            "env_file": [{"path": "./identity.env", "format": "raw"}],
            "ports": ["127.0.0.1:8180:8080"],
            "volumes": ["./charcha-realm.json:/opt/keycloak/data/import/charcha-realm.json:ro"],
            "depends_on": {"identity-db": {"condition": "service_healthy"}},
        },
    }
    # Only the Direct VPC subnet may reach this listener; enforce in GCP firewall.
    nginx = (root / "deploy/production/nginx.conf").read_text().replace(
        "# Caddy terminates HTTPS before forwarding HTTP/1.1 over loopback.",
        "# Google Cloud Run terminates HTTPS; GCP firewall permits only Direct VPC ingress.",
    ).replace("listen 127.0.0.1:8080;", f"listen {private_ip}:8080;")
    nginx = nginx.replace("    location /api/ {", """    location /rtc {
        proxy_pass http://127.0.0.1:7880;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 3600s;
        proxy_buffering off;
    }
    location /api/ {""")
    identity_env = {
        "KC_DB": "postgres", "KC_DB_URL": "jdbc:postgresql://identity-db:5432/charcha",
        "KC_DB_USERNAME": "charcha", "KC_DB_PASSWORD": db_password,
        "KC_HOSTNAME": origin + "/identity", "KC_HTTP_ENABLED": "true", "KC_HTTP_RELATIVE_PATH": "/identity",
        "KC_PROXY_HEADERS": "xforwarded", "KC_HEALTH_ENABLED": "true",
        "KC_BOOTSTRAP_ADMIN_USERNAME": "charcha-bootstrap", "KC_BOOTSTRAP_ADMIN_PASSWORD": bootstrap_password,
    }
    def env(values):
        return "# PRIVATE: never commit, publish or include in container build contexts.\n" + "".join(f"{key}={value}\n" for key, value in sorted(values.items()))
    return {
        "compose.json": json_text({"name": "charcha-google", "services": services, "networks": {"identity": {}}, "volumes": {"charcha-data": {}, "charcha-identity": {}}}),
        "api.env": env(settings), "identity.env": env(identity_env),
        "db.env": env({"POSTGRES_DB": "charcha", "POSTGRES_USER": "charcha", "POSTGRES_PASSWORD": db_password}),
        "charcha-realm.json": json_text(substitute(copy.deepcopy(realm))), "nginx.conf": nginx,
        "livekit.yaml": (
            "port: 7880\nbind_addresses: [0.0.0.0]\ndevelopment: false\n"
            "rtc:\n  tcp_port: 7881\n  udp_port: 7882\n  use_external_ip: false\n"
            f"  node_ip: {public_ip}\n  allow_tcp_fallback: true\n"
            "turn:\n  enabled: false\nlogging:\n  level: warn\n  pion_level: error\n"
            f"keys:\n  {settings['LIVEKIT_API_KEY']}: {settings['LIVEKIT_API_SECRET']}\n"
        ),
        "manifest.json": json_text({
            "schema_version": 1, "prepared_only": True, "mode": "transport", "origin": origin,
            "public_ip": public_ip, "private_ip": private_ip, "google_oauth_supplied": google_ready,
            "google_callback": origin + "/identity/realms/charcha/broker/google/endpoint",
            "pending": ["Credit verification and deployment", "Google login acceptance", "Administrator password and OTP provisioning", "Two-device media acceptance", "TURN/TLS for restrictive networks"],
        }),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--public-ip", required=True)
    parser.add_argument("--private-ip", required=True)
    parser.add_argument("--identity-env", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; do not rotate deployed identity or media credentials accidentally.")
    try:
        supplied = read_env(args.identity_env) if args.identity_env else {}
        files = render(args.origin, args.public_ip, args.private_ip, supplied, output=args.output.resolve())
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    args.output.mkdir(parents=True, mode=0o700)
    for name, content in files.items():
        path = args.output / name
        path.write_text(content, encoding="utf-8", newline="\n")
        os.chmod(path, 0o600)
    print(json_text({"prepared": True, "files": len(files), "deployed": False, "provider_calls": 0}))


if __name__ == "__main__":
    main()
