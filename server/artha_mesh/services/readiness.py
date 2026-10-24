"""Redacted setup status. Presence of configuration never implies vendor access."""
from __future__ import annotations

import re
from ipaddress import ip_address
from urllib.parse import urlsplit

from ..config import Settings
from ..models import now


def _private_host(host: str) -> bool:
    """Allow private service URLs without trusting public unencrypted endpoints."""
    host = host.rstrip(".").lower()
    try:
        address = ip_address(host)
        return address.is_loopback or address.is_private
    except ValueError:
        return host == "localhost" or "." not in host or host.endswith((".localhost", ".internal", ".local", ".lan", ".test"))


def _url_issue(value: str, schemes: tuple[str, ...], *, public: bool = False) -> str | None:
    try:
        url = urlsplit(value)
        host = url.hostname or ""
        _ = url.port  # Reject malformed ports without printing the input.
    except ValueError:
        return "Use a valid endpoint URL."
    if not host or url.scheme not in schemes:
        return "Use an endpoint URL with the required secure protocol."
    try:
        ip_address(host)
    except ValueError:
        try:
            labels = host.rstrip(".").encode("idna").decode("ascii").split(".")
        except UnicodeError:
            return "Use a valid endpoint hostname."
        if any(not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) for label in labels):
            return "Use a valid endpoint hostname."
    if value != value.strip() or any(character.isspace() for character in value):
        return "Endpoint URLs cannot contain whitespace."
    if url.username is not None or url.password is not None or url.query or url.fragment:
        return "Keep credentials in dedicated secret variables; endpoint URLs cannot include credentials, query strings or fragments."
    normalized_host = host.rstrip(".").lower()
    examples = ("example.com", "example.org", "example.net")
    if normalized_host in examples or normalized_host.endswith(tuple("." + name for name in examples) + (".example", ".invalid")):
        return "Replace the example hostname with your deployed endpoint."
    if public and _private_host(host):
        return "Use a publicly reachable hostname for browsers outside this server."
    if url.scheme in {"http", "ws"} and not _private_host(host):
        return "Use TLS for an endpoint outside your private server network."
    return None


def production_configuration_issues(settings: Settings) -> list[dict[str, str]]:
    """Static, redacted checks only. No network or provider verification is implied."""
    issues: list[dict[str, str]] = []

    def issue(key: str, detail: str):
        issues.append({"key": key, "detail": detail})

    if settings.mode != "live":
        issue("ARTHA_MODE", "Switch to live mode only after the production configuration is ready.")
    missing = settings.missing_live_config()
    for name in missing:
        issue(name, "Required live configuration is missing.")
    required_text = {
        "LIVEKIT_API_KEY": settings.livekit_api_key.get_secret_value(),
        "LIVEKIT_API_SECRET": settings.livekit_api_secret.get_secret_value(),
        "GNANI_API_KEY": settings.gnani_api_key.get_secret_value(),
        "EVON_MODEL": settings.evon_model,
    }
    for name, value in required_text.items():
        if name not in missing and not value.strip():
            issue(name, "Required live configuration cannot be whitespace.")
    endpoints = (
        ("LIVEKIT_URL", settings.livekit_url, ("wss",), True),
        ("LIVEKIT_INTERNAL_URL", settings.livekit_internal_url, ("ws", "wss"), False),
        ("EVON_BASE_URL", settings.evon_base_url, ("http", "https"), False),
        ("GNANI_STT_URL", settings.gnani_stt_url, ("wss",), False),
        ("GNANI_TTS_URL", settings.gnani_tts_url, ("wss",), False),
        ("GNANI_EMBEDDING_URL", settings.gnani_embedding_url, ("https",), False),
    )
    for name, value, schemes, public in endpoints:
        if value and (detail := _url_issue(value, schemes, public=public)):
            issue(name, detail)
    secret = settings.livekit_api_secret.get_secret_value()
    if secret and len(secret.strip()) < 32:
        issue("LIVEKIT_API_SECRET", "Generate a fresh server-side signing secret with at least 32 characters; development defaults are unsuitable.")
    if settings.livekit_api_key.get_secret_value().lower() in {"devkey", "changeme", "replace_me"}:
        issue("LIVEKIT_API_KEY", "Replace development/example room credentials with newly generated self-hosted credentials.")
    if not settings.cors_origins:
        issue("CORS_ORIGINS", "Set the exact HTTPS origin of your deployed frontend.")
    for origin in settings.cors_origins:
        detail = _url_issue(origin, ("https",), public=True)
        if not detail and urlsplit(origin).path not in {"", "/"}:
            detail = "Configure origins only, without paths, query strings or fragments."
        if detail:
            issue("CORS_ORIGINS", "Use explicit public HTTPS frontend origins without wildcards, paths or credentials.")
            break
    return issues


def readiness_snapshot(settings: Settings) -> dict:
    requirements = []

    def requirement(key, label, configured, required, group, detail):
        requirements.append({"key": key, "label": label, "configured": bool(configured),
                             "required": required, "group": group, "detail": detail})

    requirement("ARTHA_MODE", "Live processing enabled", settings.mode == "live", True,
                "Application", "Set live mode after configuring the providers; demo mode uses scripted examples.")
    requirement("GNANI_API_KEY", "Gnani API access", settings.gnani_api_key.get_secret_value(), True,
                "Gnani", "Account must have Prisma STT, Timbre TTS and voice-clone access; usage or quota is unverified.")
    requirement("LIVEKIT_URL", "LiveKit room URL", settings.livekit_url, True, "LiveKit",
                "Public wss:// room endpoint for live audio; your self-hosted server does not require LiveKit Cloud credits.")
    requirement("LIVEKIT_API_KEY", "LiveKit API key", settings.livekit_api_key.get_secret_value(), True,
                "LiveKit", "Generate this credential on your own server and use the same value in LiveKit and this API; never expose it to the browser.")
    requirement("LIVEKIT_API_SECRET", "LiveKit API secret", settings.livekit_api_secret.get_secret_value(), True,
                "LiveKit", "Generate a strong signing secret on your own server; use the same value in LiveKit and this API, never in browser code.")
    requirement("EVON_BASE_URL", "Evon endpoint", settings.evon_base_url, True, "Evon",
                "Running OpenAI-compatible chat-completions endpoint, including its /v1 prefix if applicable. Use your own Evon deployment or an approved hosted endpoint whose API contract matches this adapter.")
    requirement("EVON_MODEL", "Served Evon model", settings.evon_model, True, "Evon",
                "Exact model identifier served by the endpoint. Gnani hosted beta access, compatibility and credit eligibility must be confirmed for your account.")
    requirement("EVON_API_KEY", "Evon endpoint authentication", settings.evon_api_key.get_secret_value(), False,
                "Evon", "Required only if your hosted endpoint requires authentication.")
    requirement("TIMBRE_MODEL", "Timbre model selection", settings.timbre_model, False, "Gnani",
                "Application default exists; compatibility and account entitlement need live validation.")
    requirement("TIMBRE_VOICE", "Standard voice selection", settings.timbre_voice, False, "Gnani",
                "Application default exists; choose an available standard voice for your account.")
    return {
        "mode": settings.mode,
        "generated_at": now().isoformat(),
        "requirements": requirements,
        "configuration_issues": production_configuration_issues(settings),
        "provider_verification": "not_checked",
        "deployment_checks": [
            {"key": "HTTPS", "label": "HTTPS and browser microphone", "status": "manual",
             "detail": "Use HTTPS outside localhost and verify microphone permission in both browsers."},
            {"key": "NETWORK", "label": "Audio and provider connectivity", "status": "manual",
             "detail": "Verify LiveKit UDP/TURN connectivity and server access to Gnani and Evon."},
            {"key": "COMPUTE", "label": "Evon compute and quota", "status": "manual",
             "detail": "Use your approved hosted Evon endpoint if compatible, or supply your own GPU model service. Confirm account access and quota; no model is downloaded automatically."},
            {"key": "SPEAKERS", "label": "Consenting test speakers", "status": "manual",
             "detail": "Use at least two devices and Hindi/Tamil/Bengali speakers; cloning requires their own clean 5–30 second spoken reference."},
            {"key": "QUALITY", "label": "Quality and listener latency review", "status": "manual",
             "detail": "Review names, numbers, negation and voice quality. Server first-PCM metrics do not measure listener playback latency."},
            {"key": "RECOVERY", "label": "Recovery and deployment validation", "status": "manual",
             "detail": "Check disconnects, reconnects, expired sessions and Docker deployment on the intended host."},
        ],
    }
