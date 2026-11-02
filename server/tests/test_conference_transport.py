"""Camera grants and microphone lifecycle separation; no camera/network access."""
import asyncio
import base64
import json
import importlib.util
from pathlib import Path
from types import SimpleNamespace

from livekit import rtc

from artha_mesh.config import Settings
from artha_mesh.models import Participant
from artha_mesh.services.routing import recipients_for, target_languages
from artha_mesh.store import Store
from artha_mesh.transport.livekit import RoomTransport
from artha_mesh.transport.tokens import room_token


def claims(token):
    body = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))


def test_member_can_publish_opt_in_camera_and_microphone_but_not_screen_share():
    settings = Settings(_env_file=None, livekit_api_key="devkey", livekit_api_secret="test-only-secret-long-enough-for-sha256")
    video = claims(room_token(settings, "test-room", "member", "Member"))["video"]
    assert video["canPublishSources"] == ["microphone", "camera"]
    assert video["canPublish"] is True and video["canSubscribe"] is True
    assert video["canPublishData"] is False and video["canUpdateOwnMetadata"] is False
    assert "screen_share" not in video["canPublishSources"]
    assert "screen_share_audio" not in video["canPublishSources"]


def transport():
    store = Store(Settings(_env_file=None))
    return RoomTransport(store, store.create_room("Camera lifecycle"), None, None)


def test_interpreter_unsubscribes_camera_without_opening_audio_reader():
    instance = transport()
    changes = []
    instance._track_subscribed(
        SimpleNamespace(kind=rtc.TrackKind.KIND_VIDEO),
        SimpleNamespace(source=rtc.TrackSource.SOURCE_CAMERA, set_subscribed=changes.append),
        SimpleNamespace(identity="source"),
    )
    assert changes == [False] and instance.readers == {}


async def test_camera_unsubscribe_preserves_microphone_and_microphone_unsubscribe_cancels_it():
    instance = transport()
    task = asyncio.create_task(asyncio.Event().wait())
    instance.readers["source"] = task
    participant = SimpleNamespace(identity="source")
    try:
        instance._track_unsubscribed(
            SimpleNamespace(kind=rtc.TrackKind.KIND_VIDEO),
            SimpleNamespace(source=rtc.TrackSource.SOURCE_CAMERA), participant,
        )
        assert instance.readers["source"] is task and not task.cancelling()
        instance._track_unsubscribed(
            SimpleNamespace(kind=rtc.TrackKind.KIND_AUDIO),
            SimpleNamespace(source=rtc.TrackSource.SOURCE_SCREENSHARE_AUDIO), participant,
        )
        assert instance.readers["source"] is task and not task.cancelling()
        instance._track_unsubscribed(
            SimpleNamespace(kind=rtc.TrackKind.KIND_AUDIO),
            SimpleNamespace(source=rtc.TrackSource.SOURCE_MICROPHONE), participant,
        )
        assert "source" not in instance.readers and task.cancelling()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def test_five_languages_have_twenty_directed_pairs_and_share_one_target_track():
    participants = [Participant(id=code, name=code, language=code) for code in ("hi", "ta", "bn", "te", "mr")]
    pairs = {(source.language, target) for source in participants for target in target_languages(participants, source.id)}
    assert len(pairs) == 20 and all(source != target for source, target in pairs)
    participants.append(Participant(id="ta-second", name="Tamil listener", language="ta"))
    assert target_languages(participants, "hi") == {"ta", "bn", "te", "mr"}
    assert recipients_for(participants, "hi", "ta") == ["ta", "ta-second"]
    assert recipients_for(participants, "ta", "ta") == ["ta-second"]


async def test_synthetic_verifier_does_not_emit_transcripts_for_decoder_silence():
    path = Path(__file__).resolve().parents[2] / "scripts/verify_five_language_routing.py"
    spec = importlib.util.spec_from_file_location("five_language_rtc_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fixture = module.Providers()

    async def audio():
        for _ in range(30):
            yield b"\x00\x00" * 320
        yield b"\x40\x10" * 8000
        yield b"\x40\x10" * 8000

    results = [row async for row in fixture.transcribe(audio(), "hi")]
    assert len(results) == 1 and results[0].text.endswith("hi")
    assert fixture.recognition_opened == {"hi": 1}
    assert fixture.recognition_closed == {"hi": 1}
