"""Opt-in real WebRTC transport test against a loopback LiveKit dev server.

No microphone, vendor API, cloned voice, or real translation is used. Three
synthetic PCM publishers exercise actual RTC delivery and language permissions.
Run livekit-server --dev first, then this script with the server environment.
"""
from __future__ import annotations

import asyncio
import logging
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from livekit import rtc

from artha_mesh.config import Settings
from artha_mesh.main import create_app
from artha_mesh.models import JoinRoom, UpdateParticipant
from artha_mesh.providers.gnani import Transcript


class TestProviders:
    """Deterministic test doubles; never a substitute for vendor verification."""

    def __init__(self):
        self.translations: list[tuple[str, str]] = []

    async def transcribe(self, audio, language, on_processing=None):
        observed = 0
        emitted = False
        async for chunk in audio:
            observed += len(chunk)
            if observed >= 16000 and not emitted:
                emitted = True
                if on_processing:
                    on_processing()
                yield Transcript(f"Synthetic transport test in {language}", language, 0)

    async def translate(self, text, source, target):
        self.translations.append((source, target))
        return f"Test-only output for {target}"

    async def synthesize(self, text, language, embedding=None):
        # Two seconds makes room for real subscription negotiation and playback.
        rate = 24000
        for offset in range(0, rate * 2, 480):
            yield struct.pack("<480h", *[
                int(6000 * math.sin(2 * math.pi * 440 * (offset + n) / rate))
                for n in range(480)
            ])


async def run():
    settings = Settings(
        _env_file=None, mode="live", livekit_url="ws://127.0.0.1:7880",
        livekit_internal_url="ws://127.0.0.1:7880", livekit_api_key="devkey",
        livekit_api_secret="secret", gnani_api_key="test-double-never-sent",
        evon_base_url="http://127.0.0.1:9/v1", evon_model="test-double",
    )
    app = create_app(settings)
    fake = TestProviders()
    app.state.pipeline.translator = fake
    app.state.pipeline.tts = fake
    app.state.transport.speech = fake
    clients, sources, tasks, streams = [], [], [], []
    received: dict[str, dict[str, int]] = {}
    errors: list[str] = []

    async with app.router.lifespan_context(app):
        state = app.state.store.create_room("Local synthetic RTC verification")
        memberships = []
        try:
            for language in ("hi", "ta", "bn"):
                membership = await app.state.service.join(state.room.code, JoinRoom(
                    name=f"Test {language}", language=language, consent=True,
                ))
                memberships.append(membership)
                await app.state.service.update(
                    state.room.code, UpdateParticipant(muted=False), membership["session_token"],
                )

            for membership in memberships:
                participant = membership["participant"]
                language, identity = participant.language, participant.id
                room = rtc.Room()
                received[language] = {}

                async def consume(track, track_name, language=language):
                    stream = rtc.AudioStream(track, sample_rate=16000, num_channels=1)
                    streams.append(stream)
                    async for event in stream:
                        samples = event.frame.data.cast("B").cast("h")
                        if any(abs(value) > 50 for value in samples):
                            received[language][track_name] = received[language].get(track_name, 0) + len(samples)

                def subscribed(track, publication, remote, language=language, identity=identity, consume=consume):
                    name = publication.name
                    parts = name.split(":")
                    if len(parts) != 3 or parts[0] != "translated" or parts[1] == identity or parts[2] != language:
                        errors.append(f"Unexpected subscribed track for {language}: {name}")
                    task = asyncio.create_task(consume(track, name))
                    tasks.append(task)

                room.on("track_subscribed", subscribed)
                await room.connect(membership["livekit"]["url"], membership["livekit"]["token"])
                room.local_participant.set_track_subscription_permissions(
                    allow_all_participants=False,
                    participant_permissions=[rtc.ParticipantTrackPermission(
                        participant_identity=membership["livekit"]["agent_identity"], allow_all=True,
                    )],
                )
                source = rtc.AudioSource(16000, 1, queue_size_ms=100)
                sources.append(source)
                track = rtc.LocalAudioTrack.create_audio_track(f"source:{identity}", source)
                await room.local_participant.publish_track(track, rtc.TrackPublishOptions(
                    source=rtc.TrackSource.SOURCE_MICROPHONE,
                ))
                clients.append(room)

            async def publish(source):
                for offset in range(0, 16000 * 3, 320):
                    data = struct.pack("<320h", *[
                        int(4000 * math.sin(2 * math.pi * 300 * (offset + n) / 16000))
                        for n in range(320)
                    ])
                    await source.capture_frame(rtc.AudioFrame(data, 16000, 1, 320))
                await source.wait_for_playout()

            await asyncio.gather(*(publish(source) for source in sources))
            for _ in range(80):
                if len(fake.translations) == 6 and all(len(tracks) == 2 for tracks in received.values()):
                    break
                await asyncio.sleep(0.1)
            expected_pairs = {(source, target) for source in ("hi", "ta", "bn") for target in ("hi", "ta", "bn") if source != target}
            assert set(fake.translations) == expected_pairs, f"Fan-out mismatch: {fake.translations}"
            assert len(fake.translations) == 6, "Duplicate target-language synthesis jobs"
            assert not errors, errors
            for task in tasks:
                if task.done() and not task.cancelled() and task.exception():
                    raise task.exception()
            assert all(len(tracks) == 2 for tracks in received.values()), f"Missing audible tracks: {received}"
            print("PASS: three real RTC publishers; six directed translation branches.")
            print("PASS: each listener received two non-silent tracks in its own language.")
            print("PASS: no self-echo, original microphone, or wrong-language subscription.")
            print("Providers were test doubles. This does not verify Gnani/Evon quality or access.")
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for stream in streams:
                await stream.aclose()
            for room in clients:
                await room.disconnect()
            for source in sources:
                await source.aclose()


if __name__ == "__main__":
    logging.getLogger("livekit").setLevel(logging.WARNING)
    asyncio.run(run())
