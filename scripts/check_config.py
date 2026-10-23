"""Report configuration names/status without printing any secret values."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from artha_mesh.config import Settings  # noqa: E402


def main() -> int:
    settings = Settings()
    print(f"Mode: {settings.mode}")
    missing = settings.missing_live_config()
    required = ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "GNANI_API_KEY", "EVON_BASE_URL", "EVON_MODEL")
    for name in required:
        print(f"{name}: {'missing' if name in missing else 'configured'}")
    if missing:
        print("Scripted demo is available. Live interpretation requires the missing settings.")
        return 1 if settings.mode == "live" else 0
    print("All required values are present. This does not verify provider access or live audio.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
