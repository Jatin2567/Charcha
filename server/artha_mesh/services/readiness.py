"""Redacted setup status. Presence of configuration never implies vendor access."""
from __future__ import annotations

from ..config import Settings
from ..models import now


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
                "Browser-reachable secure room endpoint for live audio.")
    requirement("LIVEKIT_API_KEY", "LiveKit API key", settings.livekit_api_key.get_secret_value(), True,
                "LiveKit", "Server-side room access credential; never exposed to the browser.")
    requirement("LIVEKIT_API_SECRET", "LiveKit API secret", settings.livekit_api_secret.get_secret_value(), True,
                "LiveKit", "Server-side token signing secret; never exposed to the browser.")
    requirement("EVON_BASE_URL", "Evon endpoint", settings.evon_base_url, True, "Evon",
                "Running OpenAI-compatible translation endpoint; supplying a key alone does not host the model.")
    requirement("EVON_MODEL", "Served Evon model", settings.evon_model, True, "Evon",
                "Exact model identifier served by the endpoint; availability is unverified.")
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
        "provider_verification": "not_checked",
        "deployment_checks": [
            {"key": "HTTPS", "label": "HTTPS and browser microphone", "status": "manual",
             "detail": "Use HTTPS outside localhost and verify microphone permission in both browsers."},
            {"key": "NETWORK", "label": "Audio and provider connectivity", "status": "manual",
             "detail": "Verify LiveKit UDP/TURN connectivity and server access to Gnani and Evon."},
            {"key": "COMPUTE", "label": "Evon compute and quota", "status": "manual",
             "detail": "Supply running model compute and enough provider quota; no model is downloaded automatically."},
            {"key": "SPEAKERS", "label": "Consenting test speakers", "status": "manual",
             "detail": "Use at least two devices and Hindi/Tamil/Bengali speakers; cloning requires their own clean 5–30 second spoken reference."},
            {"key": "QUALITY", "label": "Quality and listener latency review", "status": "manual",
             "detail": "Review names, numbers, negation and voice quality. Server first-PCM metrics do not measure listener playback latency."},
            {"key": "RECOVERY", "label": "Recovery and deployment validation", "status": "manual",
             "detail": "Check disconnects, reconnects, expired sessions and Docker deployment on the intended host."},
        ],
    }
