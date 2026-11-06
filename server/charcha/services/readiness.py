"""Redacted setup status. Presence of configuration never implies vendor access."""
from __future__ import annotations

import re
from typing import Literal
from ipaddress import ip_address
from urllib.parse import urlsplit
from pydantic import BaseModel

from ..config import Settings
from ..models import now


class ConferenceMembership(BaseModel):
    active: bool
    muted: bool
    language: str
    voice_mode: Literal["standard", "cloned"]


class ConferenceMedia(BaseModel):
    interpreter_connected: bool
    member_connected: bool


class ConferenceAudience(BaseModel):
    other_participants: int
    translation_target_languages: list[str]
    connected_translation_target_languages: list[str]
    same_language_listeners: int


class ConferenceProviders(BaseModel):
    configured: bool
    missing: list[str]
    verification: Literal["not_checked"] = "not_checked"


class ConferenceFlow(BaseModel):
    authorization: Literal["operator", "host_budget"] = "operator"
    required: bool
    status: Literal["locked", "approved", "expired", "exhausted", "unavailable", "not_required"]
    expires_at: str | None
    remaining: dict[str, int | None]


class ConferenceSource(BaseModel):
    recognizer_task_active: bool


class ConferenceMicrophone(BaseModel):
    can_unmute: bool
    may_start_new_source: bool
    reason_code: str
    detail: str


class ConferenceReadiness(BaseModel):
    schema_version: Literal[1] = 1
    room_code: str
    mode: Literal["demo", "transport", "live"]
    generated_at: str
    membership: ConferenceMembership
    media: ConferenceMedia
    audience: ConferenceAudience
    providers: ConferenceProviders
    provider_flow: ConferenceFlow
    source: ConferenceSource
    microphone: ConferenceMicrophone


CONFERENCE_DETAILS = {
    "ready_for_attempt": "An operator grant permits a translation attempt. Provider access and speech quality are not verified.",
    "source_already_active": "Your current source is active. New-source capacity is shown separately; you can always mute.",
    "waiting_for_listener": "You can enable your microphone. Translation waits for a different-language listener.",
    "original_audio_only": "This audience uses your language; original audio needs no speech-provider credits.",
    "media_not_ready": "Wait for your room audio connection before enabling the microphone.",
    "listener_media_not_ready": "Wait for a different-language listener to connect their room audio.",
    "provider_configuration_missing": "Translation configuration is incomplete. Original same-language calls can still work.",
    "provider_flow_locked": "An operator must approve a bounded provider flow before translated microphone audio can start.",
    "provider_flow_expired": "The operator flow expired. A new approval is required before starting another translated source.",
    "provider_flow_exhausted": "The current flow has insufficient remaining resources for this audience. Ask the operator for a new bounded flow.",
    "provider_flow_unavailable": "Provider approval storage or enforcement is unavailable; translated sources are blocked.",
    "voice_setup_required": "Set up your own meeting voice before enabling the microphone.",
    "demo_no_microphone": "This is a scripted demonstration. Use the original-audio or live conference mode for microphone calls.",
}


def conference_readiness(store, state, member, transport, usage) -> ConferenceReadiness:
    """Local state only; no model probes and no provider/approval side effects."""
    settings = store.settings
    audio = getattr(transport, "rooms", {}).get(state.room.code) if transport else None
    connected = bool(audio and audio.room and not audio.closed and not audio.disconnected
                     and not getattr(audio, "reconnecting", False))
    remote = audio.room.remote_participants if connected else {}
    others = [row for row in state.room.participants if row.id != member.id and not row.is_agent and not row.is_demo
              and store.is_active(state.room.code, row.id)]
    targets = sorted({row.language for row in others if row.language != member.language})
    connected_targets = sorted({row.language for row in others if row.language != member.language and row.id in remote})
    active_source = bool(audio and member.id in getattr(audio, "recognition_active", set()) and not member.muted)
    flow = usage.conference_capacity(len(connected_targets) if state.room.mode == "live" else 0,
                                     source_active=active_source, room_code=state.room.code)
    new_flow = (usage.conference_capacity(len(connected_targets), room_code=state.room.code)
                if active_source and state.room.mode == "live" else flow)
    missing = settings.missing_live_config() if state.room.mode == "live" else settings.missing_transport_config() if state.room.mode == "transport" else []
    media_ready = connected and member.id in remote
    allowed, new_allowed = False, False
    if state.room.mode == "demo":
        reason = "demo_no_microphone"
    elif not media_ready or settings.missing_transport_config():
        reason = "media_not_ready"
    elif state.room.voice_required and (member.voice_mode != "cloned" or not (
            store.voices.get(state.voice_profiles.get(member.id, ""))
            and store.voices[state.voice_profiles[member.id]].embedding)):
        reason = "voice_setup_required"
    elif state.room.mode == "transport" or not targets:
        allowed = new_allowed = True
        reason = "original_audio_only" if others else "waiting_for_listener"
        flow = usage.conference_capacity(0)
    elif active_source:
        allowed = True
        new_allowed = not missing and bool(connected_targets) and new_flow["status"] == "approved"
        reason = "source_already_active"
    elif missing:
        reason = "provider_configuration_missing"
    elif not connected_targets:
        reason = "listener_media_not_ready"
    elif flow["status"] != "approved":
        reason = "provider_flow_" + flow["status"]
    else:
        allowed = new_allowed = True
        reason = "ready_for_attempt"
    detail = CONFERENCE_DETAILS[reason]
    if flow.get("authorization") == "host_budget" and reason == "ready_for_attempt":
        detail = "Your host has enabled interpretation. Unmute when you’re ready to speak."
    if flow.get("authorization") == "host_budget" and reason == "provider_flow_exhausted":
        detail = "The shared Gnani allowance is exhausted. A workspace administrator can update it."
    if state.room.mode == "transport" and reason == "original_audio_only":
        detail = "Original audio is shared with connected participants. Speech providers are disabled in this mode."
    elif state.room.mode == "transport" and reason == "waiting_for_listener":
        detail = "You can enable your microphone. Join another participant to hear original audio."
    return ConferenceReadiness(room_code=state.room.code, mode=state.room.mode, generated_at=now().isoformat(),
        membership=ConferenceMembership(active=True, muted=member.muted, language=member.language, voice_mode=member.voice_mode),
        media=ConferenceMedia(interpreter_connected=connected, member_connected=member.id in remote),
        audience=ConferenceAudience(other_participants=len(others), translation_target_languages=targets,
            connected_translation_target_languages=connected_targets,
            same_language_listeners=sum(row.language == member.language for row in others)),
        providers=ConferenceProviders(configured=not missing, missing=missing), provider_flow=ConferenceFlow(**flow),
        source=ConferenceSource(recognizer_task_active=active_source),
        microphone=ConferenceMicrophone(can_unmute=allowed, may_start_new_source=new_allowed,
            reason_code=reason, detail=detail))


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
        issue("CHARCHA_MODE", "Switch to live mode only after the production configuration is ready.")
    if not settings.usage_require_flow_approval:
        issue("USAGE_REQUIRE_FLOW_APPROVAL", "Require an explicit bounded operator grant before any paid provider flow.")
    if settings.usage_show_private_balance:
        issue("USAGE_SHOW_PRIVATE_BALANCE", "Disable private financial snapshots on public deployments; the local-only balance view has no operator sign-in.")
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

    requirement("CHARCHA_MODE", "Live processing enabled", settings.mode == "live", True,
                "Application", "Set live mode after configuring the providers; demo mode uses scripted examples.")
    requirement("USAGE_REQUIRE_FLOW_APPROVAL", "Provider flow permission", settings.usage_require_flow_approval, True,
                "Application", "Every billable flow needs a local operator grant with an expiry and explicit resource budgets; daily caps remain enforced.")
    requirement("GNANI_API_KEY", "Gnani API access", settings.gnani_api_key.get_secret_value(), True,
                "Gnani", "Interpretation uses Prisma STT and Gnani synthesis. Personal voices also require embedding and cloned-synthesis access. Configuration alone does not verify provider access.")
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
             "detail": "Check two devices first, then every language direction you need. Confirm meaning, personal-voice quality and physical playback with listeners; configuration is not a completed evaluation."},
            {"key": "QUALITY", "label": "Quality and listener latency review", "status": "manual",
             "detail": "Review names, numbers, negation and voice quality. Server first-PCM metrics do not measure listener playback latency."},
            {"key": "RECOVERY", "label": "Recovery and deployment validation", "status": "manual",
             "detail": "Check disconnects, reconnects, expired sessions and Docker deployment on the intended host."},
        ],
    }
