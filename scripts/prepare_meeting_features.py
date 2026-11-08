"""Configure the existing room server's optional features without changing identity or starting services."""
from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

from prepare_deployment import PreparationError, read_env, runtime_env


def feature_environment(providers: dict[str, str] | None) -> dict[str, str]:
    mode = "transport" if providers is None else "live"
    supplied = dict(providers or {})
    if mode == "live":
        supplied.setdefault("USAGE_MAX_CONCURRENT_STT", "5")
    # Use the standard deployment validation, but export only speech settings.
    # The existing bundle owns the real origins, identity secrets and RTC keys.
    validated = runtime_env({"app_domain": "localhost", "livekit_domain": "localhost"},
                            supplied, "", "", mode=mode)
    features = {key: value for key, value in validated.items()
                if key.startswith(("GNANI_", "EVON_", "TIMBRE_", "USAGE_")) and key != "USAGE_DB_PATH"}
    features.update(CHARCHA_MODE=mode, AUDIO_SCREENING_MODE="off", AUDIO_SCREENING_ON_DEMAND="true", LOCAL_AUDIO_LAB_ENABLED="false",
                    USAGE_REQUIRE_FLOW_APPROVAL="true", USAGE_REQUIRE_ROOM_SCOPE="true", USAGE_SHOW_PRIVATE_BALANCE="false",
                    USAGE_VOICE_ENROLLMENTS_PER_DAY="0", USAGE_STT_MAX_RETRIES="0")
    return features


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path, help="Existing private deployment directory")
    parser.add_argument("--providers", type=Path, help="Private provider environment for live interpretation")
    args = parser.parse_args()
    if not (args.bundle / "compose.json").is_file() or not (args.bundle / "api.env").is_file():
        parser.error("Select an existing generated deployment bundle")
    try:
        values = feature_environment(read_env(args.providers) if args.providers is not None else None)
    except (OSError, PreparationError) as error:
        parser.error(str(error))
    destination = args.bundle / "meeting-features.env"
    private = tempfile.NamedTemporaryFile(dir=args.bundle, mode="w", encoding="utf-8", newline="\n", delete=False)
    temporary = Path(private.name)
    try:
        with private:
            for key, value in sorted(values.items()):
                private.write(f"{key}={value}\n")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Prepared {values['CHARCHA_MODE']} rooms with host-controlled VoiceShield, initially off.")


if __name__ == "__main__":
    main()
