"""Private probe tones use fake local RTC objects; no network or providers."""
import asyncio
from types import SimpleNamespace

import pytest

from charcha.config import Settings
from charcha.errors import ProviderError
from charcha.models import Participant
from charcha.store import Store
from charcha.transport.livekit import RoomTransport


@pytest.fixture
def tone_transport(monkeypatch):
    from livekit import rtc

    store = Store(Settings(mode="transport", _env_file=None))
    state = store.create_room("Receiver-only tone")
    for person in [Participant(id="listener", name="A", language="hi", muted=True),
                   Participant(id="other", name="B", language="ta")]:
        state.room.participants.append(person)
        store.issue_session(state, person.id)
    transport = RoomTransport(store, state, None, None)
    captured, permissions, unpublished, sources = [], [], [], []
    subscribed = asyncio.Event()

    class Source:
        def __init__(self, *_args, **_kwargs):
            self.closed = False
            self.cleared = False
            sources.append(self)

        async def capture_frame(self, frame):
            captured.append(bytes(frame.data))

        async def wait_for_playout(self):
            pass

        def clear_queue(self):
            self.cleared = True

        async def aclose(self):
            self.closed = True

    async def publish(track, _options):
        return SimpleNamespace(sid="private-probe", wait_for_subscription=subscribed.wait)

    async def unpublish(sid):
        unpublished.append(sid)

    monkeypatch.setattr(rtc, "AudioSource", Source)
    monkeypatch.setattr(rtc.LocalAudioTrack, "create_audio_track", lambda name, source: SimpleNamespace(name=name, source=source))
    transport.room = SimpleNamespace(local_participant=SimpleNamespace(
        publish_track=publish, unpublish_track=unpublish,
        set_track_subscription_permissions=lambda **kwargs: permissions.append(kwargs),
    ))
    challenge = {"probe_id": "a" * 24, "listener_id": "listener", "track_name": f"probe:{'a' * 24}:listener"}
    return transport, challenge, subscribed, captured, permissions, unpublished, sources


async def test_tone_waits_for_subscription_and_only_target_listener_can_receive(tone_transport):
    transport, challenge, ready, captured, permissions, unpublished, sources = tone_transport
    task = asyncio.create_task(transport.send_probe(challenge))
    await asyncio.sleep(0.01)
    assert captured == []
    allowed = {p.participant_identity: list(p.allowed_track_sids) for p in permissions[-1]["participant_permissions"]}
    assert allowed == {"listener": ["private-probe"], "other": []}
    assert permissions[-1]["allow_all_participants"] is False
    ready.set()
    await task
    assert len(captured) == 50
    assert any(captured[0])
    assert unpublished == ["private-probe"]
    assert sources[0].closed and sources[0].cleared
    assert not transport.probe_tracks


async def test_cancellation_while_waiting_unpublishes_tone_and_releases_source(tone_transport):
    transport, challenge, _, captured, _, unpublished, sources = tone_transport
    task = asyncio.create_task(transport.send_probe(challenge))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert captured == []
    assert unpublished == ["private-probe"]
    assert sources[0].closed and sources[0].cleared
    assert not transport.probe_tracks


async def test_listener_departure_while_negotiating_never_emits_tone(tone_transport):
    transport, challenge, ready, captured, _, unpublished, sources = tone_transport
    task = asyncio.create_task(transport.send_probe(challenge))
    await asyncio.sleep(0.01)
    transport.state.room.participants = [p for p in transport.state.room.participants if p.id != "listener"]
    ready.set()
    with pytest.raises(ProviderError, match="not delivered"):
        await task
    assert captured == []
    assert unpublished == ["private-probe"]
    assert sources[0].closed
