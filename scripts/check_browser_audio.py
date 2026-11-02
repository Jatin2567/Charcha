"""Send a quiet synthetic tone to an existing local transport room.

No microphone, speech provider, API key or environment file is used. A human
listener/browser still needs to confirm playback. The fixture membership leaves
automatically, including on a failed setup. This is not a speech/latency test.
"""
from __future__ import annotations

import argparse
import asyncio
import ipaddress
import math
import re
import struct
import sys
from urllib.parse import urlsplit

import httpx


class CheckRejected(Exception):
    """An intentionally redacted failure safe for the local terminal."""


def loopback_url(value: str, schemes: tuple[str, ...]) -> str:
    try:
        parts = urlsplit(value)
        _ = parts.port
        host = parts.hostname or ""
    except ValueError as error:
        raise CheckRejected("Use a valid loopback URL.") from error
    try:
        loopback = host == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = False
    if (not loopback or parts.scheme not in schemes or parts.username is not None
            or parts.password is not None or parts.query or parts.fragment
            or value != value.strip() or any(character.isspace() for character in value)):
        raise CheckRejected("This diagnostic accepts loopback URLs only, without credentials or query strings.")
    return value.rstrip("/")


def bounded_integer(minimum: int, maximum: int):
    def parse(value: str) -> int:
        try:
            number = int(value)
        except ValueError as error:
            raise argparse.ArgumentTypeError("Enter a whole number.") from error
        if number < minimum or number > maximum:
            raise argparse.ArgumentTypeError(f"Enter a value from {minimum} to {maximum}.")
        return number
    return parse


async def _request(client: httpx.AsyncClient, method: str, url: str, **kwargs):
    response = await client.request(method, url, **kwargs)
    if not response.is_success:
        raise CheckRejected(f"Local application request failed (HTTP {response.status_code}).")
    return response.json()


async def perform_check(args, client: httpx.AsyncClient):
    base = loopback_url(args.api_url, ("http", "https"))
    if not re.fullmatch(r"[a-zA-Z0-9_-]{6,100}", args.room):
        raise CheckRejected("Use the room code from an existing local invitation.")
    if not 1 <= args.seconds <= 5 or not 0 <= args.hold <= 30:
        raise CheckRejected("Tone duration or inspection window is outside the local diagnostic limits.")
    # Fail before creating a member or RTC client unless raw transport is explicit.
    health = await _request(client, "GET", base + "/health")
    if health.get("mode") != "transport":
        raise CheckRejected("Refusing this check: the local application must report transport mode.")

    member = None
    room = None
    source = None
    try:
        member = await _request(client, "POST", f"{base}/rooms/{args.room}/join", json={
            "name": "Local test tone", "language": "en", "voice_mode": "standard", "consent": True,
        })
        identity = member.get("participant", {}).get("id", "")
        session_token = member.get("session_token", "")
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", identity) or not session_token:
            raise CheckRejected("The local application returned an invalid fixture membership.")
        if member.get("room", {}).get("mode") != "transport":
            raise CheckRejected("The joined room is not a raw-audio transport test.")
        credentials = member.get("livekit") or {}
        rtc_url = loopback_url(credentials.get("url", ""), ("ws", "wss"))
        if not credentials.get("token") or not credentials.get("agent_identity"):
            raise CheckRejected("The local room has no usable media membership.")
        await _request(client, "PATCH", f"{base}/rooms/{args.room}/participants/me",
                       headers={"Authorization": "Bearer " + session_token}, json={"muted": False})

        from livekit import rtc

        room = rtc.Room()
        async with asyncio.timeout(12):
            await room.connect(rtc_url, credentials["token"], options=rtc.RoomOptions(auto_subscribe=False))
        room.local_participant.set_track_subscription_permissions(
            allow_all_participants=False,
            participant_permissions=[rtc.ParticipantTrackPermission(
                participant_identity=credentials["agent_identity"], allow_all=True,
            )],
        )
        source = rtc.AudioSource(16000, 1, queue_size_ms=100)
        await room.local_participant.publish_track(
            rtc.LocalAudioTrack.create_audio_track("fixture:local-test-tone", source),
            rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE),
        )
        print(f"Fixture participant: {identity}", flush=True)
        print("Quiet local test tone; no microphone or speech API is used.", flush=True)
        await asyncio.sleep(1.5)
        sample_count = 16000 * args.seconds
        async with asyncio.timeout(args.seconds + 8):
            for offset in range(0, sample_count, 320):
                # Gentle fade at either end. Peak amplitude is under 6% of full scale.
                samples = [int(1800 * min(1, (offset + n) / 1600, (sample_count - offset - n) / 1600)
                               * math.sin(2 * math.pi * 660 * (offset + n) / 16000)) for n in range(320)]
                await source.capture_frame(rtc.AudioFrame(struct.pack("<320h", *samples), 16000, 1, 320))
            await source.wait_for_playout()
        print("Tone published. Confirm receipt/playback in the browser; publishing is not a listening pass.", flush=True)
        await asyncio.sleep(2 + args.hold)
    finally:
        # Removing the application membership first stops further relay even if
        # RTC teardown needs its own bounded cleanup window.
        if member and member.get("session_token") and member.get("participant", {}).get("id"):
            try:
                async with asyncio.timeout(4):
                    await _request(client, "POST", f"{base}/rooms/{args.room}/leave",
                                   headers={"Authorization": "Bearer " + member["session_token"]},
                                   json={"participant_id": member["participant"]["id"]})
            except (CheckRejected, httpx.HTTPError, TimeoutError):
                print("Fixture leave could not be confirmed; close the room or let membership expiry remove it.", file=sys.stderr)
        for resource, method in ((source, "aclose"), (room, "disconnect")):
            if resource is not None:
                try:
                    async with asyncio.timeout(4):
                        await getattr(resource, method)()
                except Exception:  # noqa: BLE001 -- SDK cleanup failures must not skip the other resource.
                    print("Local media cleanup did not finish within its limit.", file=sys.stderr)
        if member:
            print("Local tone check ended; fixture cleanup attempted.", flush=True)


async def run(args):
    # Never inherit proxy configuration that could send local memberships away.
    async with httpx.AsyncClient(timeout=4, trust_env=False) as client:
        await perform_check(args, client)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--room", required=True, help="Existing local room code; the browser should already be joined.")
    parser.add_argument("--api-url", default="http://127.0.0.1:5180/api")
    parser.add_argument("--seconds", type=bounded_integer(1, 5), default=3)
    parser.add_argument("--hold", type=bounded_integer(0, 30), default=3,
                        help="Extra seconds to inspect the fixture participant before automatic leave.")
    args = parser.parse_args(argv)
    try:
        asyncio.run(run(args))
        return 0
    except CheckRejected as error:
        print(str(error), file=sys.stderr)
    except KeyboardInterrupt:
        print("Local check interrupted.", file=sys.stderr)
    except Exception:  # noqa: BLE001 -- Redact upstream exceptions that can contain membership tokens.
        # Neither upstream response bodies nor room/media tokens enter terminal output.
        print("Local audio diagnostic failed; check the local application and media connection.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
