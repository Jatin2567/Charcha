import asyncio
import time

import pytest
from conftest import auth, create_member
from fastapi import HTTPException

from artha_mesh.config import Settings
from artha_mesh.errors import ProviderError
from artha_mesh.models import Participant
from artha_mesh.providers.demo import SAMPLES, DemoTranslator
from artha_mesh.services.pipeline import Pipeline
from artha_mesh.services.rooms import RoomService
from artha_mesh.store import Store


def wait_for_turn(client, code, member, utterance_id):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        snapshot = client.get(f"/api/rooms/{code}/transcript", headers=auth(member)).json()
        turn = next((item for item in snapshot["turns"] if item["id"] == utterance_id), None)
        if turn and turn["status"] in ("complete", "error"):
            return turn, snapshot["metrics"]
        time.sleep(0.01)
    raise AssertionError("Submitted demonstration turn never completed")


def test_demo_rejects_unknown_text_without_fabricating_translation(client):
    code, speaker = create_member(client)
    create_member(client, code, name="Listener", language="ta")
    rejected = client.post(f"/api/rooms/{code}/text", headers=auth(speaker), json={"text": "arbitrary unheard sentence"})
    assert rejected.status_code == 422
    assert client.get(f"/api/rooms/{code}/transcript", headers=auth(speaker)).json()["turns"] == []
    posted = client.post(f"/api/rooms/{code}/text", headers=auth(speaker), json={"text": SAMPLES[0]["hi"]})
    assert posted.status_code == 202
    turn, metrics = wait_for_turn(client, code, speaker, posted.json()["utterance_id"])
    assert turn["status"] == "complete"
    assert turn["translations"] == {"ta": SAMPLES[0]["ta"]}
    assert metrics["simulated"] is True
    assert metrics["total_ms"] == metrics["stt_ms"] == metrics["tts_ms"] == 0
    assert speaker["livekit"] is None


def test_confirmations_are_member_scoped_idempotent_and_human_initiated(client):
    code, speaker = create_member(client)
    _, listener = create_member(client, code, name="Listener", language="ta")
    _, outsider = create_member(client)
    posted = client.post(f"/api/rooms/{code}/text", headers=auth(speaker), json={"text": SAMPLES[2]["hi"]})
    utterance_id = posted.json()["utterance_id"]
    turn, _ = wait_for_turn(client, code, speaker, utterance_id)
    assert turn["confirmed_by"] == []
    body = {"utterance_id": utterance_id}
    assert client.post(f"/api/rooms/{code}/confirmations", headers=auth(outsider), json=body).status_code == 403
    for _ in range(2):
        confirmed = client.post(f"/api/rooms/{code}/confirmations", headers=auth(listener), json=body)
        assert confirmed.json()["confirmed_by"] == [listener["participant"]["id"]]
    assert client.post(f"/api/rooms/{code}/confirmations", headers=auth(speaker), json={"utterance_id": "missing"}).status_code == 404


def setup_pipeline(*, pending=8, translator=None):
    store = Store(Settings(mode="demo", max_pending_turns=pending, _env_file=None))
    state = store.create_room("Pipeline invariants")
    speaker = Participant(id="source", name="Source", language="hi")
    state.room.participants.extend([speaker, Participant(id="listener", name="Listener", language="ta")])
    return store, state, speaker, Pipeline(store, translator or DemoTranslator(), None)


async def test_source_fifo_bounded_queue_and_cancel_do_not_strand_turns():
    entered = asyncio.Event()
    released = asyncio.Event()

    class BlockingTranslator:
        async def translate(self, text, source, target):
            entered.set()
            await released.wait()
            return "fixture translation"

    _, state, speaker, pipeline = setup_pipeline(pending=1, translator=BlockingTranslator())
    try:
        first = await pipeline.submit(state, speaker, SAMPLES[0]["hi"])
        await asyncio.wait_for(entered.wait(), 1)
        second = await pipeline.submit(state, speaker, SAMPLES[1]["hi"])
        with pytest.raises(HTTPException) as error:
            await pipeline.submit(state, speaker, SAMPLES[2]["hi"])
        assert error.value.status_code == 429
        assert [turn.id for turn in state.turns] == [first, second]
        await pipeline.cancel_speaker(state.room.code, speaker.id)
        assert all(turn.status == "error" for turn in state.turns)
        assert not pipeline.queues
        assert not pipeline.workers
    finally:
        released.set()
        await pipeline.aclose()


async def test_leaving_room_cancels_in_progress_and_queued_source_turns():
    entered = asyncio.Event()

    class BlockedTranslator:
        async def translate(self, *_args):
            entered.set()
            await asyncio.Event().wait()

    class Transport:
        def __init__(self):
            self.removed = []

        async def remove(self, code, participant_id):
            self.removed.append((code, participant_id))

    store, state, speaker, pipeline = setup_pipeline(translator=BlockedTranslator())
    transport = Transport()
    service = RoomService(store, pipeline, transport, None)
    token = store.issue_session(state, speaker.id)
    try:
        await pipeline.submit(state, speaker, SAMPLES[0]["hi"])
        await asyncio.wait_for(entered.wait(), 1)
        await pipeline.submit(state, speaker, SAMPLES[1]["hi"])
        await service.leave(state.room.code, speaker.id, token)
        assert all(turn.status == "error" for turn in state.turns)
        assert all(participant.id != speaker.id for participant in state.room.participants)
        assert transport.removed == [(state.room.code, speaker.id)]
        with pytest.raises(HTTPException) as error:
            store.authenticate(token, state.room.code)
        assert error.value.status_code == 401
    finally:
        await pipeline.aclose()


async def test_source_turns_keep_order_and_targets_fan_out_concurrently():
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    starts = []
    finished = []

    class Translator:
        async def translate(self, text, source, target):
            starts.append((text, target))
            if text == SAMPLES[0]["hi"]:
                if len(starts) == 2:
                    first_started.set()
                await release_first.wait()
            finished.append((text, target))
            return "fixture " + target

    _, state, speaker, pipeline = setup_pipeline(translator=Translator())
    state.room.participants.extend([
        Participant(id="bn-listener", name="Bengali", language="bn"),
        Participant(id="second-ta", name="Tamil 2", language="ta"),
    ])
    try:
        await pipeline.submit(state, speaker, SAMPLES[0]["hi"])
        await pipeline.submit(state, speaker, SAMPLES[1]["hi"])
        await asyncio.wait_for(first_started.wait(), 1)
        assert {target for text, target in starts} == {"ta", "bn"}
        assert all(text == SAMPLES[0]["hi"] for text, _ in starts)
        release_first.set()
        await asyncio.wait_for(pipeline.queues[(state.room.code, speaker.id)].join(), 1)
        assert all(turn.status == "complete" for turn in state.turns)
        assert len(starts) == 4  # 2 turns × 2 unique languages; third listener shares ta.
        assert [text for text, _ in finished[:2]] == [SAMPLES[0]["hi"]] * 2
        assert [text for text, _ in finished[2:]] == [SAMPLES[1]["hi"]] * 2
    finally:
        release_first.set()
        await pipeline.aclose()


async def test_provider_failure_marks_one_turn_and_fifo_processes_the_next():
    class FailsFirst:
        async def translate(self, text, source, target):
            if text == SAMPLES[0]["hi"]:
                raise ProviderError("fixture provider outage")
            return "recovered"

    _, state, speaker, pipeline = setup_pipeline(translator=FailsFirst())
    try:
        await pipeline.submit(state, speaker, SAMPLES[0]["hi"])
        await pipeline.submit(state, speaker, SAMPLES[1]["hi"])
        await asyncio.wait_for(pipeline.queues[(state.room.code, speaker.id)].join(), 1)
        assert [turn.status for turn in state.turns] == ["error", "complete"]
        assert state.turns[1].translations["ta"] == "recovered"
    finally:
        await pipeline.aclose()


async def test_scripted_demo_lifecycle_marks_presenters_and_runs_actual_sample_pipeline(monkeypatch):
    store, state, human, pipeline = setup_pipeline()
    service = RoomService(store, pipeline, None, None)
    original_sleep = asyncio.sleep

    async def skip_animation_delay(_seconds):
        await original_sleep(0)

    monkeypatch.setattr("artha_mesh.services.rooms.asyncio.sleep", skip_animation_delay)
    try:
        await service.start_demo(state.room.code)
        with pytest.raises(HTTPException) as error:
            await service.start_demo(state.room.code)
        assert error.value.status_code == 409
        await asyncio.wait_for(state.demo_task, 2)
        assert len(state.turns) == 6
        assert all(turn.status == "complete" for turn in state.turns)
        presenters = [participant for participant in state.room.participants if participant.is_demo]
        assert {participant.language for participant in presenters} == {"hi", "ta", "bn"}
        assert all(turn.speaker_id.startswith("demo-") for turn in state.turns)
        assert state.metrics.simulated is True
    finally:
        await pipeline.aclose()
