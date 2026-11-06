"""Five simultaneous local speakers and a sixth listener, with a process per RTC peer.

Uses only synthetic tones, provider doubles, loopback signaling and ephemeral
memberships. Credentials travel through local pipes and are never reported.
"""
import argparse
import asyncio
from collections import Counter
from contextlib import aclosing, AsyncExitStack
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import time


def send(value):
    print(json.dumps(value), flush=True)


async def worker():
    from livekit import rtc
    cfg = json.loads(sys.stdin.readline())
    expected = set(cfg["expected"])
    heard, unexpected, readers = set(), set(), []
    peer = rtc.Room()

    async def observe(track, name):
        async with aclosing(rtc.AudioStream(track, sample_rate=16000, num_channels=1,
                                           capacity=8, frame_size_ms=20)) as stream:
            async for event in stream:
                samples = event.frame.data.cast("B").cast("h")
                if any(abs(s) > 80 for s in samples):
                    heard.add(name)
                    break

    def subscribed(track, publication, remote):
        if remote.identity != cfg["agent"] or publication.name not in expected:
            unexpected.add(publication.name)
        else:
            readers.append(asyncio.create_task(observe(track, publication.name)))
    peer.on("track_subscribed", subscribed)
    audio = None
    try:
        await peer.connect(cfg["url"], cfg["token"])
        peer.local_participant.set_track_subscription_permissions(allow_all_participants=False,
            participant_permissions=[rtc.ParticipantTrackPermission(participant_identity=cfg["agent"], allow_all=True)])
        if cfg["publish"]:
            audio = rtc.AudioSource(16000, 1, queue_size_ms=100)
            await peer.local_participant.publish_track(rtc.LocalAudioTrack.create_audio_track("Test tone", audio),
                rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
        send({"ready":True})
        if (await asyncio.to_thread(sys.stdin.readline)).strip() != "go":
            raise RuntimeError("Missing start barrier")
        first = last = None
        if audio is not None:
            # A 20-ms whole-period tone. Per-frame Python synthesis would add
            # unrelated CPU load to the concurrency exercise.
            frame = struct.pack("<320h", *(int(5000*math.sin(2*math.pi*cfg["hz"]*i/16000)) for i in range(320)))
            first = time.monotonic()
            for _ in range(cfg["frames"]):
                await audio.capture_frame(rtc.AudioFrame(frame, 16000, 1, 320))
            await audio.wait_for_playout()
            last = time.monotonic()
        try:
            async with asyncio.timeout(32):
                while heard != expected and not unexpected:
                    await asyncio.sleep(.05)
        except TimeoutError:
            pass
        send({"heard":len(heard), "expected":len(expected), "unexpected":len(unexpected),
              "passed":heard == expected and not unexpected, "start":first, "end":last})
        # All receivers stay connected until the slowest peer has observed its tracks.
        await asyncio.to_thread(sys.stdin.readline)
    finally:
        for task in readers:
            task.cancel()
        await asyncio.gather(*readers, return_exceptions=True)
        await peer.disconnect()
        if audio:
            await audio.aclose()
    return 2 if unexpected else 0


async def group(folder, report, monitor=False):
    from verify_five_language_routing import (Settings, Providers, fixture_runtime, LANGUAGES,
                                              JoinRoom, UpdateParticipant, until)
    from charcha.services.performance import performance_snapshot
    from charcha.services.screening_runtime import ScreeningRuntime
    from charcha.services.usage import UsageGuard

    settings = Settings(_env_file=None, mode="live", livekit_url="ws://127.0.0.1:17880",
        livekit_internal_url="ws://127.0.0.1:17880", livekit_api_key="devkey", livekit_api_secret="secret",
        evon_base_url="http://127.0.0.1:9/v1", evon_model="synthetic", gnani_api_key="never-sent",
        usage_db_path=folder / "fixture.sqlite", audio_screening_mode="monitor" if monitor else "off", usage_stt_max_retries=0,
        usage_require_flow_approval=True, usage_require_room_scope=True, usage_max_concurrent_stt=5)
    usage = UsageGuard(settings)
    providers = Providers(usage)
    async def release(process):
        if process.stdin:
            process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), 5)
        except TimeoutError:
            report["cleanup_failures"].append("peer_shutdown_timeout")
            process.kill()
            await process.wait()
        if process.returncode != 0:
            report["cleanup_failures"].append("peer_exit_error")

    async def read(process):
        line = await process.stdout.readline()
        if not line:
            raise RuntimeError("RTC peer exited")
        return json.loads(line)

    detector = ScreeningRuntime(settings) if monitor else None
    if detector and not detector.screener.status()["ready"]:
        raise RuntimeError("Install the screening dependency and pinned model first")
    async with fixture_runtime(settings, providers, report, screening=detector) as runtime, AsyncExitStack() as stack:
        room = runtime.store.create_room("Five simultaneous synthetic voices")
        # This ledger and grant exist only inside the disposable, provider-free fixture.
        grant = usage.approve_flow(purpose="live_interpretation", room_code=room.room.code, seconds=120,
            budgets={"stt_connections": 5, "stt_seconds": 30, "mt_requests": 20, "mt_characters": 3000,
                     "tts_requests": 20, "tts_characters": 3000})
        stack.callback(usage.close_flow, grant["id"])
        other_room = runtime.store.create_room("Unapproved fixture meeting")
        assert usage.conference_capacity(1, room_code=other_room.room.code)["status"] == "locked"
        members = []
        for code in [*LANGUAGES, "ta"]:
            members.append(await runtime.service.join(room.room.code, JoinRoom(name="RTC test", language=code, consent=True)))
        peers = []
        for i, member in enumerate(members):
            person = member["participant"]
            expected = [f"translated:{source['participant'].id}:{person.language}" for source in members[:5]
                        if source["participant"].id != person.id]
            process = await asyncio.create_subprocess_exec(sys.executable, __file__, "--worker",
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            stack.push_async_callback(release, process)
            process.stdin.write((json.dumps({"expected":expected, "publish":i < 5, "hz":300 + 50*i,
                "frames": 350 if monitor else 150,
                "token":member["livekit"]["token"], "agent":member["livekit"]["agent_identity"],
                "url":member["livekit"]["url"]})+"\n").encode())
            peers.append(process)
        if not all(reply.get("ready") for reply in await asyncio.gather(*(read(p) for p in peers))):
            raise RuntimeError("A peer failed the ready barrier")
        rtc = runtime.transport.rooms[room.room.code].room
        await until(lambda: all(member["participant"].id in rtc.remote_participants for member in members), 10)
        for member in members[:5]:
            await runtime.service.update(room.room.code, UpdateParticipant(muted=False), member["session_token"])
        await until(lambda: sum(providers.recognition_opened.values()) == 5, 10)
        for peer in peers:
            peer.stdin.write(b"go\n")
        rows = await asyncio.gather(*(read(p) for p in peers))
        report["peer_results"] = [{k:row[k] for k in ("heard","expected","unexpected","passed")} for row in rows]
        report["overlapping_publish_seconds"] = round(min(row["end"] for row in rows[:5]) -
                                                       max(row["start"] for row in rows[:5]), 3)
        report["decoded_recipient_routes"] = sum(row["heard"] for row in rows)
        report["recognizers"] = dict(providers.recognition_opened)
        report["mt_branches"] = len(providers.translations)
        report["tts_branches"] = len(providers.synthesis)
        expected_pairs = {(a,b) for a in LANGUAGES for b in LANGUAGES if a != b}
        if monitor:
            speakers = {m["participant"].id for m in members[:5]}

            def assessed():
                return {s["speaker_id"] for s in room.screening_samples
                        if s["mode"] == "monitor" and s["action"] == "observed"
                        and s["status"] == "assessed" and s["score"] is not None}

            await until(lambda: assessed() == speakers, 10)
            report["assessed_microphones"] = len(assessed())
            report["classifier"] = detector.screener.status()["id"]
        await until(lambda: performance_snapshot(room)["summary"]["live_sample_count"] >= 20, 10)
        report["fixture_performance"] = performance_snapshot(room)["summary"]
        used = usage.inspect_flow(grant["id"])["used"]
        report["fixture_room_reservations"] = used
        report["passed"] = (all(row["passed"] for row in rows) and report["overlapping_publish_seconds"] > 1
            and used["stt_connections"] == 5 and used["mt_requests"] == used["tts_requests"] == 20
            and providers.recognition_opened == Counter(LANGUAGES) and len(providers.translations) == 20
            and set(providers.translations) == expected_pairs and len(providers.synthesis) == 20)
        for peer in peers:
            peer.stdin.write(b"close\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--monitor", action="store_true", help="Assess all five microphones with the installed CPU classifier during the call")
    args = parser.parse_args()
    if args.worker:
        return asyncio.run(worker())
    from run_five_language_calls import ROOT, local_media
    if args.output is None or args.output.exists() or not args.output.resolve().is_relative_to(ROOT / "work"):
        parser.error("Choose a new report file under work/")
    report = {"record_type":"isolated_five_speaker_fixture","passed":False,"provider_requests":0,
              "physical_devices":False,"cleanup_failures":[]}
    try:
        with tempfile.TemporaryDirectory(dir=ROOT / "work") as directory:
            folder = Path(directory)
            with local_media(folder):
                asyncio.run(asyncio.wait_for(group(folder, report, args.monitor), 90))
    except Exception as error:
        report.update(passed=False,error_kind=type(error).__name__)
    if report["cleanup_failures"]:
        report["passed"] = False
    with args.output.open("x", encoding="utf8") as out:
        json.dump(report, out, indent=2)
    send(report)
    return int(not report["passed"])


if __name__ == "__main__":
    sys.exit(main())
