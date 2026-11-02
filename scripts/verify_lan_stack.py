"""Bounded synthetic acceptance of the prepared HTTPS/WSS LAN stack.

Requires explicit manifest and public CA. Uses two generated-tone RTC peers,
no microphone, .env, speech provider, translation or voice cloning. Trust for
the native RTC library must also be installed normally in the OS trust store.
"""
from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import math
from pathlib import Path
import re
import ssl
import struct
import time
from urllib.parse import urlsplit

import httpx


ROOT = Path(__file__).resolve().parents[1]
PRIVATE = tuple(ipaddress.ip_network(item) for item in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


class ProbeRejected(ValueError):
    """Only fixed, non-sensitive diagnostic codes belong in this exception."""


def private_url(value: str, scheme: str, port: int, path: str) -> str:
    try:
        parts = urlsplit(value)
        address = ipaddress.IPv4Address(parts.hostname or "")
        valid = (parts.scheme == scheme and parts.port == port and parts.path == path
                 and any(address in block for block in PRIVATE) and not parts.username
                 and not parts.password and not parts.query and not parts.fragment
                 and value == value.strip() and not any(c.isspace() for c in value))
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise ProbeRejected("invalid_private_test_url")
    return value


def load_manifest(path: Path) -> dict:
    if path.stat().st_size > 32_768:
        raise ProbeRejected("invalid_manifest")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("mode") != "transport" or manifest.get("screening") != "off":
        raise ProbeRejected("manifest_not_raw_baseline")
    frontend = manifest.get("frontend", "")
    if not isinstance(frontend, str) or not frontend.endswith("/#/tests"):
        raise ProbeRejected("invalid_manifest")
    base = private_url(frontend[:-8], "https", 8443, "")
    media = private_url(manifest.get("livekit", ""), "wss", 8444, "")
    if urlsplit(base).hostname != urlsplit(media).hostname:
        raise ProbeRejected("media_host_mismatch")
    return {"base": base, "media": media}


def check_health(health: object) -> None:
    if not isinstance(health, dict) or health.get("mode") != "transport":
        raise ProbeRejected("application_not_transport_mode")
    states = {item.get("name"): item.get("status") for item in health.get("providers", []) if isinstance(item, dict)}
    if any(states.get(name) != "disabled" for name in ("Prisma STT", "Evon MT", "Timbre TTS")):
        raise ProbeRejected("speech_providers_not_explicitly_disabled")
    if states.get("LiveKit") != "configured":
        raise ProbeRejected("media_not_configured")


async def request(client, method, url, **kwargs):
    response = await client.request(method, url, **kwargs)
    if not response.is_success:
        raise ProbeRejected("application_request_failed")
    if len(response.content) > 262_144:
        raise ProbeRejected("oversized_application_response")
    return response.json()


async def perform(config: dict, client, report: dict) -> None:
    base = config["base"] + "/api"
    check_health(await request(client, "GET", base + "/health"))
    report["checks"].append("transport mode and speech services disabled")
    members, peers, sources, consumers, streams = [], [], [], [], []
    received, first_pcm, capture_at, detached, errors = {}, {}, {}, set(), []
    code = None
    subscriptions = {}
    try:
        created = await request(client, "POST", base + "/rooms", json={"title": "Synthetic LAN acceptance"})
        code = created.get("code", "")
        if not ID.fullmatch(code) or created.get("mode") != "transport":
            raise ProbeRejected("invalid_created_room")
        from livekit import rtc

        async with asyncio.timeout(75):
            for index, language in enumerate(("hi", "ta")):
                member = await request(client, "POST", f"{base}/rooms/{code}/join", json={
                    "name": f"Synthetic LAN peer {index + 1}", "language": language,
                    "consent": True, "voice_mode": "standard",
                })
                members.append(member)
                identity = member.get("participant", {}).get("id", "")
                media = member.get("livekit") or {}
                if (not ID.fullmatch(identity) or not member.get("session_token")
                        or member.get("room", {}).get("mode") != "transport"
                        or member.get("participant", {}).get("voice_mode") != "standard"
                        or media.get("url") != config["media"] or not media.get("token")
                        or not media.get("agent_identity")):
                    raise ProbeRejected("invalid_media_membership")
                await request(client, "PATCH", f"{base}/rooms/{code}/participants/me",
                              headers={"Authorization": "Bearer " + member["session_token"]}, json={"muted": False})
                received[identity] = {}
                peer = rtc.Room()
                peers.append(peer)

                async def consume(track, name, listener=identity):
                    stream = rtc.AudioStream(track, sample_rate=16000, num_channels=1, capacity=50)
                    streams.append(stream)
                    try:
                        async for event in stream:
                            if any(abs(value) > 100 for value in event.frame.data.cast("B").cast("h")):
                                received[listener][name] = received[listener].get(name, 0) + 1
                                first_pcm.setdefault(name, time.perf_counter())
                    finally:
                        await stream.aclose()

                def subscribed(track, publication, remote, listener=identity, consume=consume, agent=media["agent_identity"]):
                    parts = publication.name.split(":")
                    if len(parts) != 3 or parts[0] != "raw" or parts[1] == listener or parts[2] != "all" or remote.identity != agent:
                        errors.append("unexpected_subscription")
                        return
                    task = asyncio.create_task(consume(track, publication.name))
                    subscriptions[(listener, publication.sid)] = task
                    consumers.append(task)

                def unsubscribed(track, publication, remote, listener=identity):
                    task = subscriptions.pop((listener, publication.sid), None)
                    if task:
                        task.cancel()
                    detached.add((listener, publication.name))

                peer.on("track_subscribed", subscribed)
                peer.on("track_unsubscribed", unsubscribed)
                async with asyncio.timeout(15):
                    await peer.connect(media["url"], media["token"])
                peer.local_participant.set_track_subscription_permissions(
                    allow_all_participants=False,
                    participant_permissions=[rtc.ParticipantTrackPermission(participant_identity=media["agent_identity"], allow_all=True)],
                )
                source = rtc.AudioSource(16000, 1, queue_size_ms=100)
                sources.append(source)
                await peer.local_participant.publish_track(
                    rtc.LocalAudioTrack.create_audio_track("fixture:lan-test-tone", source),
                    rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE),
                )

            await asyncio.sleep(1)

            async def publish(index, seconds):
                identity = members[index]["participant"]["id"]
                capture_at.setdefault(f"raw:{identity}:all", time.perf_counter())
                for offset in range(0, int(seconds * 16000), 320):
                    samples = [int(1800 * math.sin(2 * math.pi * (620 + index * 290) * (offset + n) / 16000)) for n in range(320)]
                    await sources[index].capture_frame(rtc.AudioFrame(struct.pack("<320h", *samples), 16000, 1, 320))
                await sources[index].wait_for_playout()

            report["audio_attempted"] = True
            await asyncio.gather(publish(0, 2), publish(1, 2))
            async with asyncio.timeout(8):
                while not all(len(values) == 1 for values in received.values()):
                    if errors:
                        raise ProbeRejected("unexpected_subscription")
                    await asyncio.sleep(.05)
            for index, member in enumerate(members):
                expected = f"raw:{members[1-index]['participant']['id']}:all"
                if set(received[member["participant"]["id"]]) != {expected} or errors:
                    raise ProbeRejected("unexpected_audio_route")
            report["checks"].extend(["HTTPS API and WSS media connected", "two non-silent raw audio directions", "no self or direct-original subscription"])
            report["directions"] = [{"route": f"peer {index+1} to peer {2-index}", "capture_to_received_pcm_ms": round((first_pcm[f"raw:{member['participant']['id']}:all"] - capture_at[f"raw:{member['participant']['id']}:all"]) * 1000, 2)} for index, member in enumerate(members)]
            speaker, listener = members[0], members[1]["participant"]["id"]
            name = f"raw:{speaker['participant']['id']}:all"
            headers = {"Authorization": "Bearer " + speaker["session_token"]}
            await request(client, "PATCH", f"{base}/rooms/{code}/participants/me", headers=headers, json={"muted": True})
            async with asyncio.timeout(6):
                while (listener, name) not in detached:
                    await asyncio.sleep(.05)
            count = received[listener][name]
            await publish(0, .6)
            await asyncio.sleep(.25)
            if received[listener][name] != count:
                raise ProbeRejected("muted_audio_still_received")
            await request(client, "PATCH", f"{base}/rooms/{code}/participants/me", headers=headers, json={"muted": False})
            await publish(0, 1.2)
            async with asyncio.timeout(6):
                while received[listener].get(name, 0) <= count:
                    await asyncio.sleep(.05)
            report["checks"].append("server mute removes receiver track; unmute restores audio")
            transcript = await request(client, "GET", f"{base}/rooms/{code}/transcript", headers=headers)
            if transcript.get("turns") != []:
                raise ProbeRejected("unexpected_interpretation")
            report["checks"].append("no transcript or interpretation")
    finally:
        clean = True
        for member in members:
            try:
                if code and member.get("session_token") and member.get("participant", {}).get("id"):
                    async with asyncio.timeout(4):
                        await request(client, "POST", f"{base}/rooms/{code}/leave",
                                      headers={"Authorization": "Bearer " + member["session_token"]},
                                      json={"participant_id": member["participant"]["id"]})
            except Exception:
                clean = False
        for task in consumers:
            task.cancel()
        if consumers:
            try:
                async with asyncio.timeout(5):
                    await asyncio.gather(*consumers, return_exceptions=True)
            except TimeoutError:
                clean = False
        for resource, method in [*( (source, "aclose") for source in sources), *((peer, "disconnect") for peer in peers)]:
            try:
                async with asyncio.timeout(4):
                    await getattr(resource, method)()
            except Exception:
                clean = False
        report["fixture_cleanup_confirmed"] = clean
        if not clean:
            raise ProbeRejected("fixture_cleanup_incomplete")


async def signaling_join(url, token, identity, code, context):
    """TLS-verified signaling only. Never creates a native RTC peer or sends SDP.

    LiveKit's APIKeyAuthMiddleware accepts Authorization: Bearer; /rtc sends
    its initial SignalResponse on upgrade. See official LiveKit auth.go and
    v1.9.1 rtcservice.go. Keep the membership token out of the URL entirely.
    """
    from websockets.asyncio.client import connect
    from livekit.protocol.rtc import SignalResponse

    class NoRedirectConnect(connect):
        def process_redirect(self, error):
            return error

    async with asyncio.timeout(12):
        async with NoRedirectConnect(
            url + "/rtc?protocol=15&auto_subscribe=0&sdk=python&version=local-signaling-probe",
            ssl=context, proxy=None, additional_headers={"Authorization": "Bearer " + token},
            open_timeout=7, close_timeout=2, max_size=131_072, max_queue=4,
            ping_interval=None,
        ) as socket:
            raw = await socket.recv()
            if not isinstance(raw, bytes):
                raise ProbeRejected("unexpected_signaling_encoding")
            response = SignalResponse.FromString(raw)
            if (response.WhichOneof("message") != "join"
                    or response.join.participant.identity != identity
                    or response.join.room.name != code):
                raise ProbeRejected("unexpected_signaling_join")


async def perform_https(config, client, context, report):
    """Check certificate-verified page/API/signaling without OS trust changes."""
    base = config["base"] + "/api"
    check_health(await request(client, "GET", base + "/health"))
    report["checks"].append("transport mode and speech services disabled")
    page = await client.get(config["base"] + "/")
    if (not page.is_success or "text/html" not in page.headers.get("content-type", "")
            or len(page.content) > 2_097_152 or b'id="root"' not in page.content):
        raise ProbeRejected("frontend_page_failed")
    report["checks"].append("HTTPS frontend and API verified against supplied public CA and IP SAN")
    code, members = None, []
    try:
        async with asyncio.timeout(40):
            created = await request(client, "POST", base + "/rooms", json={"title": "Synthetic LAN signaling acceptance"})
            code = created.get("code", "")
            if not ID.fullmatch(code) or created.get("mode") != "transport":
                raise ProbeRejected("invalid_created_room")
            for index, language in enumerate(("hi", "ta")):
                member = await request(client, "POST", f"{base}/rooms/{code}/join", json={
                    "name": f"Synthetic signaling peer {index + 1}", "language": language,
                    "consent": True, "voice_mode": "standard",
                })
                members.append(member)
                identity = member.get("participant", {}).get("id", "")
                media = member.get("livekit") or {}
                if (not ID.fullmatch(identity) or not member.get("session_token")
                        or member.get("room", {}).get("mode") != "transport"
                        or member.get("participant", {}).get("voice_mode") != "standard"
                        or media.get("url") != config["media"] or not media.get("token")):
                    raise ProbeRejected("invalid_media_membership")
                await signaling_join(media["url"], media["token"], identity, code, context)
            report["checks"].append("two authenticated WSS signaling joins verified with supplied public CA")
            transcript = await request(client, "GET", f"{base}/rooms/{code}/transcript",
                                       headers={"Authorization": "Bearer " + members[0]["session_token"]})
            if transcript.get("turns") != []:
                raise ProbeRejected("unexpected_interpretation")
            report["checks"].append("no transcript or interpretation")
    finally:
        clean = True
        for member in members:
            try:
                if code and member.get("session_token") and member.get("participant", {}).get("id"):
                    async with asyncio.timeout(4):
                        await request(client, "POST", f"{base}/rooms/{code}/leave",
                                      headers={"Authorization": "Bearer " + member["session_token"]},
                                      json={"participant_id": member["participant"]["id"]})
            except Exception:
                clean = False
        report["fixture_cleanup_confirmed"] = clean
        if not clean:
            raise ProbeRejected("fixture_cleanup_incomplete")


async def run(config, ca, report, https_only=False):
    context = ssl.create_default_context(cafile=str(ca))
    async with httpx.AsyncClient(verify=context, timeout=6, trust_env=False, follow_redirects=False) as client:
        if https_only:
            await perform_https(config, client, context, report)
        else:
            await perform(config, client, report)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--ca", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--https-only", action="store_true", help="Verify HTTPS and authenticated WSS signaling with the supplied CA; no native RTC, audio or OS trust changes")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "work") or output.exists():
        parser.error("Choose a new report file under work/; previous evidence is never overwritten.")
    report = {"schema_version": 1, "passed": False, "synthetic": True, "provider_requests": 0,
              "microphone_opened": False, "voice_cloning": "deferred", "checks": [],
              "scope": "https_and_wss_signaling_only" if args.https_only else "synthetic_raw_audio",
              "audio_attempted": False,
              "os_trust_changed": False,
              "boundary": "Generated source PCM to decoded received PCM on one host clock; includes Docker/LAN/TLS setup. Not two physical devices, human listening or translated-speech latency."}
    if args.https_only:
        report["boundary"] = "Supplied-CA certificate/hostname verification, HTTPS frontend/API and authenticated WSS join only. No WebRTC media negotiation, microphone, audio routing, browser trust or second-device acceptance was tested."
    try:
        config = load_manifest(args.manifest)
        asyncio.run(run(config, args.ca, report, https_only=args.https_only))
        report["passed"] = True
    except ProbeRejected as error:
        report["failure_code"] = str(error)
    except (KeyboardInterrupt, asyncio.CancelledError):
        report["failure_code"] = "interrupted"
    except Exception:
        report["failure_code"] = "local_tls_media_or_application_failure"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
