import asyncio

from artha_mesh.config import Settings
from artha_mesh.models import Participant
from artha_mesh.services.routing import recipients_for, target_languages
from artha_mesh.store import Consumer, Store


def test_three_way_routing_no_echo_and_shared_language_fanout():
    participants = [
        Participant(id="a", name="A", language="hi"),
        Participant(id="b", name="B", language="ta"),
        Participant(id="c", name="C", language="bn"),
        Participant(id="d", name="D", language="ta"),
        Participant(id="e", name="E", language="hi"),
        Participant(id="agent", name="Agent", language="en", is_agent=True),
    ]
    assert target_languages(participants, "a") == {"hi", "ta", "bn"}
    assert recipients_for(participants, "a", "ta") == ["b", "d"]
    assert recipients_for(participants, "a", "hi") == ["e"]
    for speaker in participants[:-1]:
        for target in ("hi", "ta", "bn", "en"):
            listeners = recipients_for(participants, speaker.id, target)
            assert speaker.id not in listeners
            assert "agent" not in listeners


async def test_slow_event_consumer_is_disconnected_without_starving_fast_consumer():
    room = Store(Settings(mode="demo", _env_file=None)).create_room("Backpressure")
    slow = Consumer(asyncio.Queue(maxsize=1))
    fast = Consumer(asyncio.Queue(maxsize=4))
    room.consumers.update((slow, fast))
    room.broadcast("one", {"value": 1})
    room.broadcast("two", {"value": 2})
    assert slow.overflow.is_set()
    assert slow not in room.consumers
    assert not fast.overflow.is_set()
    assert [(await fast.queue.get())["type"] for _ in range(2)] == ["one", "two"]
