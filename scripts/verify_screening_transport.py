"""Real local RTC screening routing check; no microphone or paid providers.

Default uses controlled verdict fixtures to test enforcement, never accuracy.
--actual-model-monitor exercises the installed CPU model with synthetic tones;
monitor must forward regardless of its result. Neither run validates speech.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import struct
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from livekit import rtc  # noqa: E402

from artha_mesh.config import Settings  # noqa: E402
from artha_mesh.main import create_app  # noqa: E402
from artha_mesh.models import JoinRoom, UpdateParticipant  # noqa: E402


async def run(actual_model_monitor=False, output=None, cpu_threads=1):
    settings = Settings(
        _env_file=None, mode="transport", livekit_url="ws://127.0.0.1:7880",
        livekit_internal_url="ws://127.0.0.1:7880", livekit_api_key="devkey",
        livekit_api_secret="secret", gnani_api_key="", evon_api_key="",
        evon_base_url="", evon_model="", audio_screening_mode="monitor" if actual_model_monitor else "enforce",
        audio_screening_cpu_threads=cpu_threads,
        usage_db_path=ROOT / "work/local/screening-rtc.sqlite3",
    )
    app = create_app(settings)
    verdict = ["allow"]
    analyses = []
    counts = {"samples": 0, "first_at": None}
    expected_samples = app.state.screening.screener.window_samples
    if not actual_model_monitor:
        async def controlled(_pcm):
            samples = memoryview(_pcm).cast("h")
            analyses.append({
                "verdict": verdict[0], "input_samples": len(samples),
                "leading_exact_zero_samples": next((i for i, value in enumerate(samples) if value), len(samples)),
                "received_samples_before_verdict": counts["samples"],
                "verdict_at": time.perf_counter(),
            })
            assert len(samples) == expected_samples, "Screening analyzed an incomplete window"
            result = {"verdict": verdict[0], "score": None, "compute_ms": 0,
                      "audio_window_ms": expected_samples * 1000 / 16000, "reasons": ["controlled_fixture_not_a_model_prediction"],
                      "model": {"id": "routing-fixture", "kind": "fixture", "ready": True},
                      "experimental": True}
            return SimpleNamespace(verdict=verdict[0], compute_ms=0, as_dict=lambda: dict(result))
        app.state.screening.analyze = controlled
    elif not app.state.screening.screener.status()["ready"]:
        raise RuntimeError("Actual-model monitor requires the installed local screening model")

    clients, streams, tasks = [], [], []
    source = None
    checks, phases = [], []
    name = "screening-rtc-model-monitor.json" if actual_model_monitor else "screening-rtc-enforce.json"
    destination = Path(output) if output else ROOT / "work/local" / name

    def save_report(passed, failure=None):
        report = {
            "passed": passed, "mode": settings.audio_screening_mode,
            "controlled_verdicts": not actual_model_monitor,
            "synthetic_audio": True, "provider_requests": 0, "accuracy": None,
            "boundary": "source capture to received non-silent PCM in one local process; not acoustic listener playback or translation latency",
            "window_check": "exact decoded sample count and verdict-before-received-audio; decoder startup silence may precede source capture",
            "required_window_samples": expected_samples,
            "checks": checks, "phases": phases,
            "controlled_analysis_inputs": [
                {key: value for key, value in row.items() if key != "verdict_at"} for row in analyses
            ],
        }
        if failure:
            report["failure"] = failure
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))

    async with app.router.lifespan_context(app):
        state = app.state.store.create_room("Local screening RTC verification")
        try:
            members = []
            for name, language in (("Synthetic source", "hi"), ("Synthetic listener", "ta")):
                members.append(await app.state.service.join(state.room.code, JoinRoom(
                    name=name, language=language, consent=True,
                )))
            speaker_id = members[0]["participant"].id

            async def consume(track):
                stream = rtc.AudioStream(track, sample_rate=16000, num_channels=1)
                streams.append(stream)
                async for event in stream:
                    samples = event.frame.data.cast("B").cast("h")
                    if any(abs(value) > 100 for value in samples):
                        counts["samples"] += len(samples)
                        if counts["first_at"] is None:
                            counts["first_at"] = time.perf_counter()

            for index, member in enumerate(members):
                client = rtc.Room()
                if index == 1:
                    def subscribed(track, publication, remote):
                        if publication.name == f"raw:{speaker_id}:all" and remote.identity == members[1]["livekit"]["agent_identity"]:
                            tasks.append(asyncio.create_task(consume(track)))
                    client.on("track_subscribed", subscribed)
                await client.connect(member["livekit"]["url"], member["livekit"]["token"])
                clients.append(client)
            source = rtc.AudioSource(16000, 1, queue_size_ms=100)
            clients[0].local_participant.set_track_subscription_permissions(
                allow_all_participants=False,
                participant_permissions=[rtc.ParticipantTrackPermission(
                    participant_identity=members[0]["livekit"]["agent_identity"], allow_all=True,
                )],
            )
            await clients[0].local_participant.publish_track(
                rtc.LocalAudioTrack.create_audio_track("screening fixture tone", source),
                rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE),
            )

            async def mute(value):
                await app.state.service.update(state.room.code, UpdateParticipant(muted=value), members[0]["session_token"])
                await asyncio.sleep(.4)

            async def publish(seconds):
                for offset in range(0, int(seconds * 16000), 320):
                    data = struct.pack("<320h", *[int(6000 * math.sin(2 * math.pi * 620 * (offset + n) / 16000)) for n in range(320)])
                    await source.capture_frame(rtc.AudioFrame(data, 16000, 1, 320))
                await source.wait_for_playout()

            await mute(False)
            started = time.perf_counter()
            await publish(2)
            await asyncio.sleep(.2)
            if actual_model_monitor:
                assert counts["samples"] > 0, "Monitor incorrectly held original audio"
                checks.append("monitor forwards before a complete model window")
            else:
                assert counts["samples"] == 0, "Enforce leaked audio before verdict"
                checks.append("enforce withholds partial window")
            await publish(2.6)
            async with asyncio.timeout(8):
                while not state.screening_samples or counts["samples"] == 0:
                    await asyncio.sleep(.05)
            first_ms = (counts["first_at"] - started) * 1000
            phase = {"phase": "monitor" if actual_model_monitor else "allow",
                     "capture_to_first_received_pcm_ms": round(first_ms, 2),
                     "result": dict(state.screening_samples[-1])}
            phases.append(phase)
            if not actual_model_monitor:
                # RTC decoder silence may already be buffered before the source
                # capture timer starts. Enforce the full decoded window and verdict
                # ordering directly; elapsed time from the later tone is not proof.
                assert analyses and analyses[0]["input_samples"] == expected_samples
                assert analyses[0]["received_samples_before_verdict"] == 0, "Audio arrived before the first verdict"
                assert counts["first_at"] >= analyses[0]["verdict_at"], "Audio arrived before the full-window verdict"
                phase["capture_to_first_verdict_ms"] = round((analyses[0]["verdict_at"] - started) * 1000, 2)
                checks.append("exact full decoded window assessed before first received audio")
            checks.append("allowed audio crosses the real local RTC relay")

            if not actual_model_monitor:
                for selection in ("suspicious", "unknown"):
                    await mute(True)
                    verdict[0] = selection
                    await mute(False)
                    before = counts["samples"]
                    await publish(4.6)
                    await asyncio.sleep(.4)
                    assert counts["samples"] == before, f"{selection} audio was relayed"
                    result = state.screening_latest[speaker_id]
                    assert result["verdict"] == selection and result["action"] == "withheld"
                    phases.append({"phase": selection, "received_samples": counts["samples"] - before})
                    checks.append(f"enforce withholds {selection} audio")
                await mute(True)
                verdict[0] = "allow"
                await mute(False)
                await publish(.5)
                await mute(True)
                await mute(False)
                before = counts["samples"]
                await publish(2)
                await asyncio.sleep(.2)
                assert counts["samples"] == before, "Mute retained a partial decision window"
                checks.append("mute discards buffered partial audio")
                assert all(row["input_samples"] == expected_samples for row in analyses), "A controlled verdict used an incomplete window"
            assert not state.turns, "Transport test invoked interpretation"
            save_report(True)
        except Exception as exc:
            save_report(False, {"type": type(exc).__name__, "message": str(exc)})
            raise
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for stream in streams:
                await stream.aclose()
            for client in clients:
                await client.disconnect()
            if source:
                await source.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actual-model-monitor", action="store_true")
    parser.add_argument("--cpu-threads", type=int, choices=(1, 2, 4), default=1)
    parser.add_argument("--output", type=Path, help="Save this run separately, including any failure")
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.ERROR)
    asyncio.run(run(arguments.actual_model_monitor, arguments.output, arguments.cpu_threads))
