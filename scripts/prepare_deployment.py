"""Prepare a single Linux VM deployment offline; never starts containers or calls APIs.

The Caddy layer-4 topology follows LiveKit's official deployment generator:
https://github.com/livekit/deploy/blob/main/generate/templates/caddy.go
https://github.com/livekit/deploy/blob/main/generate/production.go
Generated files contain secrets and belong only on the deployment server.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import secrets
import stat
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "deploy" / "production" / "generated"
DOMAIN = re.compile(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
CADDY_IMAGE = re.compile(r"livekit/caddyl4(?::[A-Za-z0-9._-]+|@sha256:[a-f0-9]{64})\Z")
BOUNDS = {
    "MAX_PARTICIPANTS": (8, 2, 32), "MAX_ROOMS": (100, 1, 10000),
    "ROOM_TTL_SECONDS": (14400, 60, 86400), "SESSION_TTL_SECONDS": (14400, 60, 86400),
    "MAX_PENDING_TURNS": (8, 1, 32), "MAX_TURNS_PER_ROOM": (1000, 10, 10000),
    "EVENT_QUEUE_SIZE": (128, 4, 1024), "AUDIO_QUEUE_FRAMES": (100, 10, 500),
    "USAGE_STT_SECONDS_PER_DAY": (600, 0, 864000),
    "USAGE_STT_CONNECTIONS_PER_DAY": (30, 0, 100000),
    "USAGE_MT_REQUESTS_PER_DAY": (100, 0, 1000000),
    "USAGE_MT_CHARACTERS_PER_DAY": (30000, 0, 100000000),
    "USAGE_TTS_REQUESTS_PER_DAY": (100, 0, 1000000),
    "USAGE_TTS_CHARACTERS_PER_DAY": (30000, 0, 100000000),
    "USAGE_VOICE_ENROLLMENTS_PER_DAY": (3, 0, 100000),
    "USAGE_MAX_CONCURRENT_STT": (3, 1, 32),
    "USAGE_MAX_CONCURRENT_OPERATIONS": (2, 1, 32),
    "USAGE_MAX_QUEUED_OPERATIONS": (16, 0, 256),
    "USAGE_STT_MAX_RETRIES": (3, 0, 10),
    "USAGE_MAX_LIVE_ROOM_SECONDS": (900, 60, 86400),
}
FLOAT_BOUNDS = {"PROVIDER_TIMEOUT_SECONDS": (45, 1, 120), "USAGE_PROVIDER_ADMISSION_TIMEOUT_SECONDS": (5, 0.01, 30)}
REFERENCE_PRICES = {"USAGE_STT_INR_PER_HOUR", "USAGE_TTS_INR_PER_10000_CHARACTERS"}
PROVIDER_DEFAULTS = {
    "GNANI_STT_URL": "wss://api.vachana.ai/stt/v3/stream",
    "GNANI_TTS_URL": "wss://api.vachana.ai/api/v1/tts",
    "GNANI_EMBEDDING_URL": "https://api.vachana.ai/api/v1/tts/voice-clone/embeddings",
    "TIMBRE_MODEL": "timbre-v2.5", "TIMBRE_VOICE": "Nalini", "VOICE_CLONE_MODEL": "vachana-vc-v1",
}
STOCK_VOICE_KEYS = {"TIMBRE_VOICE_" + language for language in ("HI", "TA", "BN", "EN", "TE", "KN", "ML", "MR", "GU", "PA")}
PROVIDER_KEYS = {"GNANI_API_KEY", "GNANI_STT_MODEL", "EVON_BASE_URL", "EVON_MODEL", "EVON_API_KEY", "EVON_SERVERLESS",
                 "REVIEWER_GPU_ALLOWED_ORIGINS",
                 "CHARCHA_AUTH_DOMAIN", "CHARCHA_AUTH_CLIENT_ID", "CHARCHA_AUTH_CLIENT_SECRET",
                 "CHARCHA_IDENTITY_PROVIDER", "CHARCHA_OIDC_ISSUER",
                 "CHARCHA_ADMIN_SUBJECT", "CHARCHA_ADMIN_CONNECTION", "CHARCHA_MEETING_HOST_EMAIL",
                 "EVON_MODAL_KEY", "EVON_MODAL_SECRET", *STOCK_VOICE_KEYS,
                 *PROVIDER_DEFAULTS, *BOUNDS, *FLOAT_BOUNDS, *REFERENCE_PRICES}


class PreparationError(ValueError):
    """A safe error containing setting names, never supplied setting values."""


def placeholder_hostname(hostname: str) -> bool:
    reserved = ("example.com", "example.org", "example.net")
    return (
        hostname.endswith((".example", ".invalid", ".test"))
        or any(hostname == domain or hostname.endswith("." + domain) for domain in reserved)
    )


def read_env(path: Path, *, raw: bool = False) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name, separator, value = line.partition("=")
        name = name.strip()
        if not separator or not re.fullmatch(r"[A-Z][A-Z0-9_]*", name) or name in values:
            raise PreparationError(f"Invalid or duplicate environment setting on line {line_number}.")
        if not raw:
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise PreparationError(f"Environment setting {name} must be a single printable line.")
        values[name] = value
    return values


def validate_inputs(supplied: object) -> dict[str, str]:
    required = {"app_domain", "livekit_domain", "turn_domain", "public_ipv4"}
    if not isinstance(supplied, dict) or set(supplied) - required - {"caddy_image"} or not required <= set(supplied):
        raise PreparationError("Deployment JSON requires app_domain, livekit_domain, turn_domain and public_ipv4; caddy_image is optional.")
    if any(not isinstance(value, str) for value in supplied.values()):
        raise PreparationError("Deployment JSON values must be strings.")
    config = {name: value.strip().lower() if name.endswith("domain") else value.strip() for name, value in supplied.items()}
    domains = [config[name] for name in ("app_domain", "livekit_domain", "turn_domain")]
    if any(not DOMAIN.fullmatch(domain) or placeholder_hostname(domain) or domain.endswith((".local", ".internal")) for domain in domains) or len(set(domains)) != 3:
        raise PreparationError("Use three different, valid DNS hostnames without a protocol, path or wildcard.")
    try:
        address = ipaddress.ip_address(config["public_ipv4"])
    except ValueError:
        raise PreparationError("public_ipv4 must be the server's public IPv4 address.") from None
    if address.version != 4 or not address.is_global:
        raise PreparationError("public_ipv4 must be a publicly routable IPv4 address.")
    config["caddy_image"] = config.get("caddy_image", "livekit/caddyl4:latest")
    if not CADDY_IMAGE.fullmatch(config["caddy_image"]):
        raise PreparationError("caddy_image must identify the official livekit/caddyl4 image by tag or SHA-256 digest.")
    return config


def validate_url(name: str, value: str, *, websocket: bool = False, private_http: bool = False) -> None:
    if value != value.strip() or any(character.isspace() for character in value):
        raise PreparationError(f"{name} requires a URL without whitespace.")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise PreparationError(f"{name} has an invalid URL.") from None
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or port == 0:
        raise PreparationError(f"{name} requires a URL without credentials, query or fragment.")
    hostname = parsed.hostname.lower()
    try:
        host_address = ipaddress.ip_address(hostname)
        valid_host = not (host_address.is_unspecified or host_address.is_multicast or host_address.is_link_local)
    except ValueError:
        valid_host = bool(DOMAIN.fullmatch(hostname)) or hostname == "localhost"
    if not valid_host or placeholder_hostname(hostname):
        raise PreparationError(f"{name} requires a valid endpoint hostname or IP, not a placeholder.")
    secure = "wss" if websocket else "https"
    if parsed.scheme == secure:
        return
    private = parsed.hostname == "localhost"
    try:
        address = ipaddress.ip_address(parsed.hostname)
        private = address.is_private or address.is_loopback
    except ValueError:
        private = private or parsed.hostname.endswith((".internal", ".local"))
    if private_http and parsed.scheme == "http" and private:
        return
    raise PreparationError(f"{name} requires {secure}; private Evon HTTP is allowed only on a trusted private network.")


def validate_reviewer_origins(value: str) -> str:
    """Canonical public DNS origins only; DNS ownership/egress remain operator checks."""
    if not value.strip():
        return ""
    origins = []
    for item in value.split(","):
        item = item.strip()
        try:
            parsed = urlsplit(item)
            host = parsed.hostname or ""
            try:
                ipaddress.ip_address(host)
            except ValueError:
                pass
            else:
                raise ValueError()
            if (parsed.scheme != "https" or parsed.port not in (None, 443)
                    or len(host.split(".")) < 3 or not DOMAIN.fullmatch(host)
                    or parsed.username or parsed.password or parsed.query or parsed.fragment
                    or parsed.path not in ("", "/") or re.search(r"[\s%\\]", item)
                    or host.endswith((".local", ".internal", ".localhost", ".test", ".invalid", ".example", ".home.arpa", ".onion"))):
                raise ValueError()
            origins.append("https://" + host)
        except ValueError:
            raise PreparationError("REVIEWER_GPU_ALLOWED_ORIGINS requires comma-separated public HTTPS DNS origins without credentials, IP addresses, paths or alternate ports.") from None
    return ",".join(dict.fromkeys(origins))


def runtime_env(config: dict[str, str], supplied: dict[str, str], api_key: str, api_secret: str, *, mode: str = "live") -> dict[str, str]:
    if mode not in {"live", "transport"}:
        raise PreparationError("Deployment mode must be live or transport.")
    settings = dict(PROVIDER_DEFAULTS)
    settings.update({name: value for name, value in supplied.items() if name in PROVIDER_KEYS and value != ""})
    if "REVIEWER_GPU_ALLOWED_ORIGINS" in supplied:
        settings["REVIEWER_GPU_ALLOWED_ORIGINS"] = validate_reviewer_origins(supplied["REVIEWER_GPU_ALLOWED_ORIGINS"])
    if mode == "live" and "EVON_SERVERLESS" in supplied:
        if supplied["EVON_SERVERLESS"] not in {"true", "false"}:
            raise PreparationError("EVON_SERVERLESS requires exactly true or false.")
        settings["EVON_SERVERLESS"] = supplied["EVON_SERVERLESS"]
    if mode == "transport":
        # The first hosted audio test has no inference clients, secrets or allowance.
        settings = {name: value for name, value in settings.items()
                    if not name.startswith(("GNANI_", "EVON_", "TIMBRE_", "VOICE_CLONE_"))}
        for name in BOUNDS:
            if name.startswith("USAGE_") and name.endswith("_PER_DAY"):
                settings[name] = "0"
    if "GNANI_STT_MODEL" in settings:
        if not settings["GNANI_STT_MODEL"].strip():
            settings.pop("GNANI_STT_MODEL")
        elif settings["GNANI_STT_MODEL"] not in {"prisma-v2.5", "prisma-v3.0"}:
            raise PreparationError("GNANI_STT_MODEL requires prisma-v2.5 or prisma-v3.0, or leave it unset.")
    for name in (("GNANI_API_KEY", "EVON_BASE_URL", "EVON_MODEL") if mode == "live" else ()):
        if not settings.get(name, "").strip():
            raise PreparationError(f"{name} is required in the server environment file.")
    for name in (("GNANI_STT_URL", "GNANI_TTS_URL", "GNANI_EMBEDDING_URL", "EVON_BASE_URL") if mode == "live" else ()):
        validate_url(name, settings[name], websocket=name in {"GNANI_STT_URL", "GNANI_TTS_URL"}, private_http=name == "EVON_BASE_URL")
    modal_key, modal_secret = settings.get("EVON_MODAL_KEY", ""), settings.get("EVON_MODAL_SECRET", "")
    if modal_key or modal_secret:
        destination = urlsplit(settings["EVON_BASE_URL"])
        hostname = destination.hostname or ""
        if (not modal_key or not modal_secret
                or any(len(value) > 4096 or any(not 33 <= ord(char) <= 126 for char in value)
                       for value in (modal_key, modal_secret))
                or destination.scheme != "https" or destination.port not in (None, 443)
                or not hostname.endswith(".modal.run") or not hostname.removesuffix(".modal.run")):
            raise PreparationError("EVON_MODAL_KEY/EVON_MODAL_SECRET require a complete header-safe pair and an HTTPS Modal endpoint.")
    for name, (default, minimum, maximum) in BOUNDS.items():
        value = settings.get(name, str(default))
        if not re.fullmatch(r"[0-9]+", value) or not minimum <= int(value) <= maximum:
            raise PreparationError(f"{name} requires an integer within its supported bounds.")
        settings[name] = str(int(value))
    for name, (default, minimum, maximum) in FLOAT_BOUNDS.items():
        try:
            value = float(settings.get(name, str(default)))
        except ValueError:
            raise PreparationError(f"{name} requires a number within its supported bounds.") from None
        if not minimum <= value <= maximum:
            raise PreparationError(f"{name} requires a number within its supported bounds.")
        settings[name] = str(value)
    for name in REFERENCE_PRICES:
        if name in settings:
            try:
                amount = float(settings[name])
            except ValueError:
                raise PreparationError(f"{name} requires a finite nonnegative reference rate.") from None
            if not 0 <= amount <= 1000000:
                raise PreparationError(f"{name} requires a finite nonnegative reference rate.")
            settings[name] = str(amount)
    settings.update({
        "CHARCHA_PUBLIC_ORIGIN": f"https://{config['app_domain']}",
        "CHARCHA_MODE": mode, "CORS_ORIGINS": f"https://{config['app_domain']}",
        "LIVEKIT_URL": f"wss://{config['livekit_domain']}", "LIVEKIT_INTERNAL_URL": "ws://127.0.0.1:7880",
        "LIVEKIT_API_KEY": api_key, "LIVEKIT_API_SECRET": api_secret,
        "USAGE_DB_PATH": "/app/data/usage.sqlite3",
        "USAGE_REQUIRE_FLOW_APPROVAL": "true", "USAGE_SHOW_PRIVATE_BALANCE": "false",
    })
    if mode == "transport":
        settings.update({name: "" for name in ("GNANI_API_KEY", "EVON_BASE_URL", "EVON_MODEL", "EVON_API_KEY", "EVON_MODAL_KEY", "EVON_MODAL_SECRET")})
        settings["EVON_SERVERLESS"] = "false"
        settings.update(AUDIO_SCREENING_MODE="off", LOCAL_AUDIO_LAB_ENABLED="false")
    return settings


def json_text(value: object) -> str:
    return json.dumps(value, indent=2, ensure_ascii=True) + "\n"


def render(config: dict[str, str], settings: dict[str, str], output: Path, project_root: Path) -> dict[str, str]:
    # Match the official TLS termination/proxy order; app HTTP is restricted to HTTP/1.1.
    def route(domain: str, destination: int, http: bool) -> dict:
        tls: dict = {"handler": "tls"}
        if http:
            tls["connection_policies"] = [{"alpn": ["http/1.1"]}]
        return {"match": [{"tls": {"sni": [domain]}}], "handle": [tls, {"handler": "proxy", "upstreams": [{"dial": [f"127.0.0.1:{destination}"]}]}]}

    caddy = {
        "admin": {"disabled": True}, "logging": {"logs": {"default": {"level": "WARN"}}},
        "storage": {"module": "file_system", "root": "/data"},
        "apps": {
            "tls": {"certificates": {"automate": [config['app_domain'], config['livekit_domain'], config['turn_domain']]}},
            "layer4": {"servers": {"main": {"listen": [":443"], "routes": [
                route(config["turn_domain"], 5349, False), route(config["livekit_domain"], 7880, True), route(config["app_domain"], 8080, True),
            ]}}},
        },
    }
    livekit = (
        "# Private signaling; public media/TURN listeners require the documented firewall.\n"
        "port: 7880\nbind_addresses: [127.0.0.1]\ndevelopment: false\n"
        "rtc:\n  tcp_port: 7881\n  port_range_start: 50000\n  port_range_end: 60000\n"
        f"  use_external_ip: false\n  node_ip: {config['public_ipv4']}\n"
        f"  stun_servers: [{json.dumps(config['turn_domain'] + ':3478')}]\n"
        "  allow_tcp_fallback: true\nturn:\n  enabled: true\n"
        f"  domain: {config['turn_domain']}\n  external_tls: true\n  tls_port: 5349\n  udp_port: 3478\n"
        "logging:\n  level: warn\n  pion_level: error\n  json: true\n"
        f"keys:\n  {settings['LIVEKIT_API_KEY']}: {settings['LIVEKIT_API_SECRET']}\n"
    )
    root_relative = Path(os.path.relpath(project_root, output)).as_posix()
    nginx_relative = Path(os.path.relpath(project_root / "deploy" / "production" / "nginx.conf", output)).as_posix()
    logging = {"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}}
    common = {"network_mode": "host", "restart": "unless-stopped", "logging": logging, "stop_grace_period": "30s"}
    compose = {
        "name": "charcha-production",
        "services": {
            "livekit": {**common, "image": "livekit/livekit-server:v1.9.1", "command": ["--config", "/etc/livekit.yaml"], "volumes": ["./livekit.yaml:/etc/livekit.yaml:ro"]},
            "api": {
                **common, "build": {"context": root_relative, "dockerfile": "Dockerfile.api"},
                "command": ["uvicorn", "charcha.main:app", "--host", "127.0.0.1", "--port", "8000", "--workers", "1", "--no-access-log", "--log-level", "warning", "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1"],
                "env_file": [{"path": "./api.env", "format": "raw"}], "volumes": ["usage-ledger:/app/data"],
                "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
                "depends_on": {"livekit": {"condition": "service_started"}},
                "healthcheck": {"test": ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"], "interval": "15s", "timeout": "5s", "retries": 3, "start_period": "15s"},
            },
            "web": {
                **common, "build": {"context": root_relative, "dockerfile": "Dockerfile.web"},
                "volumes": [f"{nginx_relative}:/etc/nginx/conf.d/default.conf:ro"],
                "depends_on": {"api": {"condition": "service_healthy"}},
            },
            "caddy": {
                **common, "image": config["caddy_image"], "command": ["run", "--config", "/etc/caddy.json"],
                "volumes": ["./caddy.json:/etc/caddy.json:ro", "caddy-data:/data"],
                "depends_on": {"web": {"condition": "service_started"}, "livekit": {"condition": "service_started"}},
            },
        },
        "volumes": {"usage-ledger": {"name": "artha-mesh-usage-ledger"}, "caddy-data": {"name": "artha-mesh-caddy-data"}},
    }
    return {
        "compose.json": json_text(compose), "caddy.json": json_text(caddy), "livekit.yaml": livekit,
        "api.env": "# PRIVATE: Docker Compose raw environment; do not publish or log.\n" + "".join(f"{name}={settings[name]}\n" for name in sorted(settings)),
        "manifest.json": json_text({"schema_version": 1, "inputs": config, "prepared_only": True, "note": "No DNS, TLS, Docker, provider access or live audio has been verified."}),
    }


def prepare(config_path: Path, env_path: Path, output: Path = DEFAULT_OUTPUT, project_root: Path = PROJECT_ROOT, *, mode: str = "live") -> dict:
    config = validate_inputs(json.loads(config_path.read_text(encoding="utf-8-sig")))
    supplied = read_env(env_path)
    settings = runtime_env(config, supplied, "API" + secrets.token_hex(12), secrets.token_urlsafe(48), mode=mode)
    if output.exists():
        raise PreparationError("Output directory already exists. Preserve it and its keys; choose a new --output path for a separate deployment.")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Atomic directory rename prevents a partially written stack. No overwriting or implicit key rotation.
    with tempfile.TemporaryDirectory(prefix=".charcha-prepare-", dir=output.parent) as temporary:
        staged = Path(temporary) / "generated"
        staged.mkdir(mode=0o700)
        for name, content in render(config, settings, output, project_root).items():
            path = staged / name
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
        staged.rename(output)
    return {"status": "prepared", "output": str(output), "app_url": f"https://{config['app_domain']}", "provider_calls": 0}


def check(output: Path = DEFAULT_OUTPUT, project_root: Path = PROJECT_ROOT) -> dict:
    if output.is_symlink():
        raise PreparationError("Generated directory must not be a symbolic link.")
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise PreparationError("Unsupported deployment manifest version.")
    config = validate_inputs(manifest.get("inputs"))
    supplied = read_env(output / "api.env", raw=True)
    api_key, api_secret = supplied.get("LIVEKIT_API_KEY", ""), supplied.get("LIVEKIT_API_SECRET", "")
    if not re.fullmatch(r"API[a-f0-9]{24}", api_key) or not re.fullmatch(r"[A-Za-z0-9_-]{64}", api_secret):
        raise PreparationError("Generated LiveKit credentials are missing or invalid.")
    expected = render(config, runtime_env(config, supplied, api_key, api_secret, mode=supplied.get("CHARCHA_MODE", "live")), output, project_root)
    for name, content in expected.items():
        path = output / name
        if path.is_symlink() or path.read_text(encoding="utf-8") != content:
            raise PreparationError(f"Generated {name} differs from validated configuration; prepare a new stack instead of editing topology files.")
        if os.name == "posix" and stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise PreparationError(f"Generated {name} must not be readable or writable by other users.")
    if os.name == "posix" and stat.S_IMODE(output.stat().st_mode) & 0o077:
        raise PreparationError("Generated directory requires private permissions (0700).")
    return {"status": "configuration_valid", "provider_calls": 0, "runtime_verified": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="Non-secret deployment inputs JSON")
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / "server" / ".env", help="Private server environment file")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="Check an existing generated stack offline")
    parser.add_argument("--mode", choices=["live", "transport"], default="live", help="transport disables inference and prepares original-audio meetings")
    args = parser.parse_args()
    try:
        if args.check:
            result = check(Path(os.path.abspath(args.output)))
        else:
            if not args.config:
                parser.error("--config is required when preparing a deployment")
            result = prepare(args.config, args.env_file, Path(os.path.abspath(args.output)), mode=args.mode)
        print(json.dumps(result))
        return 0
    except PreparationError as error:
        print(f"Deployment preparation failed: {error} No containers were started.", file=sys.stderr)
        return 1
    except (OSError, json.JSONDecodeError):
        # Do not expose parser input, secrets, file contents or tracebacks in CLI output.
        print("Deployment preparation failed. Check input setting names, required provider values, supported bounds and output permissions. No containers were started.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
