"""Local synthetic WebRTC check. No vendor API, user microphone, or real speech."""
from __future__ import annotations

import asyncio
import array
import logging
import math
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from livekit import rtc

from artha_mesh.config import Settings
from artha_mesh.main import create_app
from artha_mesh.models import JoinRoom, UpdateParticipant
from artha_mesh.providers.gnani import Transcript
from artha_mesh.store import token_digest


class Fixtures:
    def __init__(self):
        self.translations = []
        self.bytes_by_language = {"hi": 0, "ta": 0}

    async def transcribe(self, audio, language, on_processing=None):
        seen = 0
        emitted = False
        async for chunk in audio:
            samples = array.array("h", chunk)
            if not any(abs(value) > 80 for value in samples):
                continue
            self.bytes_by_language[language] += len(chunk)
            seen += len(chunk)
            if seen >= 16000 and not emitted:
                emitted = True
                if on_processing:
                    on_processing()
                yield Transcript("Synthetic fixture in " + language, language, 0)

    async def translate(self, text, source, target):
        self.translations.append((source, target))
        return "Synthetic translation fixture for " + target

    async def synthesize(self, text, language, embedding=None):
        for offset in range(0, 24000 * 2, 480):
            yield struct.pack("<480h", *[
                int(6000 * math.sin(2 * math.pi * 440 * (offset + n) / 24000))
                for n in range(480)
            ])


async def main():
    settings = Settings(
        _env_file=None, mode="live", livekit_url="ws://127.0.0.1:7880",
        livekit_internal_url="ws://127.0.0.1:7880", livekit_api_key="devkey",
        livekit_api_secret="secret", gnani_api_key="test-only-never-sent",
        evon_base_url="http://127.0.0.1:9/v1", evon_model="fixture",
    )
    app = create_app(settings)
    fixture = Fixtures()
    app.state.pipeline.translator = fixture
    app.state.pipeline.tts = fixture
    app.state.transport.speech = fixture
    clients, sources, tasks, streams = [], [], [], []
    received = {}
    errors = []

    async with app.router.lifespan_context(app):
        state = app.state.store.create_room("Synthetic same-language, mute and expiry")
        memberships = []
        try:
            for index, language in enumerate(("hi", "hi", "ta")):
                member = await app.state.service.join(state.room.code, JoinRoom(
                    name=f"Fixture {index}", language=language, consent=True,
                ))
                memberships.append(member)
                await app.state.service.update(state.room.code, UpdateParticipant(muted=False), member["session_token"])
            for index, member in enumerate(memberships):
                participant = member["participant"]
                identity, language = participant.id, participant.language
                received[identity] = {}
                client = rtc.Room()

                async def consume(track, name, identity=identity):
                    stream = rtc.AudioStream(track, sample_rate=16000, num_channels=1)
                    streams.append(stream)
                    async for event in stream:
                        samples = event.frame.data.cast("B").cast("h")
                        if any(abs(value) > 80 for value in samples):
                            received[identity][name] = received[identity].get(name, 0) + len(samples)

                def subscribed(track, publication, remote, identity=identity, language=language, consume=consume):
                    pieces = publication.name.split(":")
                    if (len(pieces) != 3 or pieces[0] != "translated"
                            or pieces[1] == identity or pieces[2] != language):
                        errors.append((identity, publication.name))
                    tasks.append(asyncio.create_task(consume(track, publication.name)))

                client.on("track_subscribed", subscribed)
                await client.connect(member["livekit"]["url"], member["livekit"]["token"])
                client.local_participant.set_track_subscription_permissions(
                    allow_all_participants=False,
                    participant_permissions=[rtc.ParticipantTrackPermission(
                        participant_identity=member["livekit"]["agent_identity"], allow_all=True,
                    )],
                )
                source = rtc.AudioSource(16000, 1, queue_size_ms=100)
                sources.append(source)
                track = rtc.LocalAudioTrack.create_audio_track("fixture microphone", source)
                await client.local_participant.publish_track(track, rtc.TrackPublishOptions(
                    source=rtc.TrackSource.SOURCE_MICROPHONE,
                ))
                clients.append(client)

            # Deliberately create A's 24kHz typed-fallback output before forwarding
            # 16kHz original PCM onto that same speaker/language track.
            first = memberships[0]["participant"]
            await app.state.pipeline.submit(state, first, "Synthetic typed fallback")
            await asyncio.wait_for(app.state.pipeline.queues[(state.room.code, first.id)].join(), 10)
            fixture.translations.clear()
            for counters in received.values():
                counters.clear()

            async def publish(source, seconds=3):
                for offset in range(0, int(16000 * seconds), 320):
                    data = struct.pack("<320h", *[
                        int(4000 * math.sin(2 * math.pi * 300 * (offset + n) / 16000))
                        for n in range(320)
                    ])
                    await source.capture_frame(rtc.AudioFrame(data, 16000, 1, 320))
                await source.wait_for_playout()

            await asyncio.gather(*(publish(source) for source in sources))
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and not all(len(items) == 2 for items in received.values()):
                await asyncio.sleep(0.1)
            assert not errors, errors
            assert all(len(items) == 2 for items in received.values()), received
            assert sorted(fixture.translations) == [("hi", "ta"), ("hi", "ta"), ("ta", "hi")], fixture.translations
            print("PASS: hi-hi-ta listeners each received two non-silent permitted tracks.")
            print("PASS: 16kHz original speech forwards into an existing 24kHz typed-fallback track.")
            print("PASS: one target-language job per unique audience language, no self/original/wrong-language delivery.")

            # Muting through the application must stop server recognition even if
            # a test client intentionally continues publishing microphone PCM.
            await app.state.service.update(state.room.code, UpdateParticipant(muted=True), memberships[2]["session_token"])
            await asyncio.sleep(0.2)
            before = fixture.bytes_by_language["ta"]
            await publish(sources[2], 0.8)
            await asyncio.sleep(0.3)
            assert fixture.bytes_by_language["ta"] == before, fixture.bytes_by_language
            print("PASS: server-side microphone mute stopped recognition despite continuing client PCM.")
            await app.state.service.update(state.room.code, UpdateParticipant(muted=False), memberships[2]["session_token"])
            await publish(sources[2], 1)
            await asyncio.sleep(0.2)
            assert fixture.bytes_by_language["ta"] > before
            print("PASS: unmute restarted recognition from the subscribed microphone.")

            token = memberships[2]["session_token"]
            app.state.store.sessions[token_digest(token)].expires_at = time.time() - 1
            await publish(sources[2], 0.3)
            await asyncio.sleep(0.2)
            before_expired = fixture.bytes_by_language["ta"]
            await publish(sources[2], 0.5)
            await asyncio.sleep(0.2)
            assert fixture.bytes_by_language["ta"] == before_expired
            await app.state.service.prune_expired()
            assert not any(p.id == memberships[2]["participant"].id for p in state.room.participants)
            assert memberships[2]["participant"].id not in app.state.transport.rooms[state.room.code].readers
            assert not app.state.store.is_active(state.room.code, memberships[2]["participant"].id)
            print("PASS: session expiry stopped incoming recognition before sweep; sweep removed membership and RTC reader.")
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for stream in streams:
                await stream.aclose()
            for source in sources:
                await source.aclose()
            for client in clients:
                await client.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    asyncio.run(main())

