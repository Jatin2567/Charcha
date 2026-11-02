"""Two local RTC peers prove camera-SID delivery and original-audio isolation.

Synthetic pixels/PCM only. No camera device, microphone device, interpreter,
provider API, cloned voice or remote server is used. A loopback LiveKit dev SFU
must already be running. This is not browser-capture or translation acceptance.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
from pathlib import Path
import struct
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from livekit import rtc

from artha_mesh.config import Settings
from artha_mesh.transport.tokens import room_token


async def run(diagnostics):
    settings = Settings(_env_file=None, mode="transport", livekit_url="ws://127.0.0.1:7880",
                        livekit_api_key="devkey", livekit_api_secret="secret")
    room_name = "camera-fixture-" + uuid.uuid4().hex[:12]
    sender_id, receiver_id = "synthetic-camera-sender", "synthetic-camera-listener"
    sender, receiver = rtc.Room(), rtc.Room()
    connected, consumers, streams = [], [], []
    camera_source = rtc.VideoSource(64, 48)
    microphone_source = rtc.AudioSource(16000, 1, queue_size_ms=100)
    received_video, detached = asyncio.Event(), asyncio.Event()
    counts = {"decoded_video_frames": 0, "original_audio_subscriptions": 0, "unexpected_subscriptions": 0,
              "synthetic_microphone_frames_sent": 0, "synthetic_camera_frames_sent": 0}
    camera_sid = None

    async def consume(track):
        stream = rtc.VideoStream(track, capacity=4)
        streams.append(stream)
        async for event in stream:
            if event.frame.width > 0 and event.frame.height > 0 and len(event.frame.data) > 0:
                counts["decoded_video_frames"] += 1
                received_video.set()

    def subscribed(track, publication, participant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            counts["original_audio_subscriptions"] += 1
            return
        if (track.kind != rtc.TrackKind.KIND_VIDEO or participant.identity != sender_id
                or publication.source != rtc.TrackSource.SOURCE_CAMERA
                or publication.name != f"camera:{sender_id}" or publication.sid != camera_sid):
            counts["unexpected_subscriptions"] += 1
            return
        consumers.append(asyncio.create_task(consume(track)))

    def unsubscribed(track, publication, participant):
        if participant.identity == sender_id and publication.sid == camera_sid:
            detached.set()

    receiver.on("track_subscribed", subscribed)
    receiver.on("track_unsubscribed", unsubscribed)
    try:
        diagnostics["phase"] = "peer_connect"
        for room, identity in ((sender, sender_id), (receiver, receiver_id)):
            token = room_token(settings, room_name, identity, "Synthetic camera test", ttl_seconds=60)
            async with asyncio.timeout(10):
                await room.connect(settings.livekit_url, token)
            connected.append(room)
            room.local_participant.set_track_subscription_permissions(allow_all_participants=False, participant_permissions=[])
        diagnostics["phase"] = "publish_tracks"
        async with asyncio.timeout(10):
            await sender.local_participant.publish_track(
                rtc.LocalAudioTrack.create_audio_track("synthetic microphone", microphone_source),
                rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE),
            )
            camera = await sender.local_participant.publish_track(
                rtc.LocalVideoTrack.create_video_track(f"camera:{sender_id}", camera_source),
                rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_CAMERA),
            )
        camera_sid = camera.sid
        # Equivalent to the frontend: a human peer receives exactly the camera
        # SID, never allowAll and never the original microphone SID.
        sender.local_participant.set_track_subscription_permissions(
            allow_all_participants=False,
            participant_permissions=[rtc.ParticipantTrackPermission(
                participant_identity=receiver_id, allow_all=False, allowed_track_sids=[camera_sid],
            )],
        )
        diagnostics["phase"] = "synthetic_media"

        async def microphone():
            for offset in range(0, 16000, 320):
                pcm = struct.pack("<320h", *[int(5000 * math.sin(2 * math.pi * 330 * (offset + n) / 16000)) for n in range(320)])
                await microphone_source.capture_frame(rtc.AudioFrame(pcm, 16000, 1, 320))
                counts["synthetic_microphone_frames_sent"] += 1
            await microphone_source.wait_for_playout()

        async def camera_pixels():
            for _ in range(30):
                camera_source.capture_frame(rtc.VideoFrame(64, 48, rtc.VideoBufferType.RGBA,
                                                          b"\x22\x7f\xc0\xff" * (64 * 48)))
                counts["synthetic_camera_frames_sent"] += 1
                await asyncio.sleep(.1)

        async with asyncio.timeout(12):
            await asyncio.gather(microphone(), camera_pixels())
            await received_video.wait()
        assert counts["decoded_video_frames"] > 0
        assert counts["synthetic_microphone_frames_sent"] == 50
        assert counts["original_audio_subscriptions"] == counts["unexpected_subscriptions"] == 0
        diagnostics["phase"] = "camera_unpublish"
        async with asyncio.timeout(8):
            await sender.local_participant.unpublish_track(camera_sid)
            await detached.wait()
        return {"schema_version": 1, "record_type": "two_peer_synthetic_camera_rtc", "passed": True,
                "provider_requests": 0, "synthetic": True, "camera_device_used": False,
                "microphone_device_used": False, "voice_cloning": False, "screening": "off",
                "participants": 2, **counts, "camera_unpublish_detached_receiver": True,
                "permission_policy": "receiver camera SID only; original microphone denied",
                "camera_publisher_grant_verified": True, "browser_capture_verified": False,
                "real_device_verified": False, "translation_verified": False, "latency": None,
                "checks": ["human participant JWT permits camera publishing", "receiver decoded synthetic camera video",
                           "synthetic microphone transmitted without any receiver audio subscription",
                           "camera unpublish caused receiver track detach"],
                "limitations": "Two Python SDK peers on loopback. Does not verify browser permission/capture, hardware, multi-device video or translated audio."}
    finally:
        async def close(name, operation, seconds=3):
            try:
                await asyncio.wait_for(operation(), seconds)
            except Exception as error:
                diagnostics["cleanup_failures"].append({"resource": name, "kind": type(error).__name__})
        for task in consumers:
            task.cancel()
        await close("consumer_tasks", lambda: asyncio.gather(*consumers, return_exceptions=True))
        for stream in streams:
            await close("video_stream", stream.aclose)
        for room in connected:
            await close("peer_disconnect", room.disconnect, 4)
        await close("camera_source", camera_source.aclose)
        await close("microphone_source", microphone_source.aclose)
        diagnostics["counts"] = counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new report filename; existing evidence is preserved")
    logging.basicConfig(level=logging.ERROR)
    diagnostics = {"phase": "starting", "cleanup_failures": []}

    async def bounded():
        async with asyncio.timeout(50):
            return await run(diagnostics)
    try:
        report = asyncio.run(bounded())
    except Exception as error:
        report = {"schema_version": 1, "record_type": "two_peer_synthetic_camera_rtc", "passed": False,
                  "failure_kind": type(error).__name__, "failed_phase": diagnostics["phase"],
                  "provider_requests": 0, "synthetic": True, "camera_device_used": False,
                  "microphone_device_used": False, "voice_cloning": False, "screening": "off",
                  "latency": None, **diagnostics.get("counts", {})}
    report["cleanup_failures"] = diagnostics["cleanup_failures"]
    if report["passed"] and diagnostics["cleanup_failures"]:
        report.update(passed=False, checks_passed_before_cleanup=True, failure_kind="cleanup_incomplete")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
