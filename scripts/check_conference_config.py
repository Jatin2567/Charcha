"""Check local settings and the requested CPU model without opening a provider connection."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("transport", "live"), default="transport")
    args = parser.parse_args()
    try:
        from charcha.config import Settings
        settings = Settings()
        missing = settings.missing_live_config() if args.mode == "live" else settings.missing_transport_config()
        if settings.audio_screening_mode != "off" or settings.audio_screening_on_demand:
            from charcha.services.screening_runtime import ScreeningRuntime
            model = ScreeningRuntime(settings).screener.status()
            if not model["ready"]:
                missing.append("VoiceShield classifier: " + model["reason"])
        if args.mode == "live":
            from charcha.providers.evon import modal_proxy_headers
            modal_proxy_headers(settings.evon_base_url, settings.evon_modal_key.get_secret_value(),
                                settings.evon_modal_secret.get_secret_value())
        print(json.dumps({"configuration_valid": not missing, "mode": args.mode, "missing": missing,
            "providers_verified": False, "provider_calls": 0, "flow_approval_required": True,
            "screening": settings.audio_screening_mode, "voice_cloning": "deferred"}))
        return 0 if not missing else 1
    except Exception:
        print(json.dumps({"configuration_valid": False, "detail": "Configuration is invalid; values are withheld.",
                          "provider_calls": 0, "providers_verified": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
