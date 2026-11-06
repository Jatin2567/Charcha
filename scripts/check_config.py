"""Report configuration names/status without printing any secret values."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from charcha.config import Settings  # noqa: E402
from charcha.services.readiness import production_configuration_issues  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production", action="store_true", help="Check public deployment TLS, origins and self-hosted credentials without contacting providers.")
    args = parser.parse_args(argv)
    try:
        settings = Settings()
    except ValidationError as exc:
        print("Configuration validation failed. Values are redacted:")
        for error in exc.errors(include_input=False, include_url=False):
            print(f"{'.'.join(str(part) for part in error['loc'])}: invalid configuration ({error['type']})")
        return 1
    print(f"Mode: {settings.mode}")
    missing = settings.missing_live_config()
    required = ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "GNANI_API_KEY", "EVON_BASE_URL", "EVON_MODEL")
    for name in required:
        print(f"{name}: {'missing' if name in missing else 'configured'}")
    if args.production:
        issues = production_configuration_issues(settings)
        for item in issues:
            print(f"{item['key']}: {item['detail']}")
        if issues:
            print("Production configuration needs the changes above. No provider calls were made.")
            return 1
        print("Production configuration checks passed. DNS, TLS certificates, firewall, API access, quota and live audio still require deployment validation.")
        return 0
    if missing:
        print("Scripted demo is available. Live interpretation requires the missing settings.")
        return 1 if settings.mode == "live" else 0
    print("All required values are present. This does not verify provider access or live audio.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
