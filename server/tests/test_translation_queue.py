"""Real asyncio pipeline with fake model/PCM: no sockets, providers or billed calls."""
import asyncio
import json
import time
from pathlib import Path

import pytest

from charcha.config import Settings
from charcha.models import Participant
from charcha.services.pipeline import Pipeline
from charcha.store import Store
from fastapi import HTTPException


def setup(translator, speech, transport, *, lookahead=2, age=4):
    store = Store(Settings(_env_file=None, mode="live", translation_lookahead=lookahead,
                           translation_queue_max_age_seconds=age))
    state = store.create_room("Offline queue fixture")
    source = Participant(id="source", name="Source", language="hi")
    listener = Participant(id="listener", name="Listener", language="ta")
    state.room.participants = [source, listener]
    for member in state.room.participants:
        store.issue_session(state, member.id)
    pipeline = Pipeline(store, translator, speech)
    pipeline.transport = transport
    return pipeline, state, source


class Translator:
    def __init__(self):
        self.requests = []

    async def translate(self, text, source, target):
        self.requests.append(text)
        return text


class Speech:
    def __init__(self):
        self.requests = []
        self.closed = []

    async def synthesize(self, text, *_args):
        self.requests.append(text)
        try:
            yield text.encode()*2
        finally:
            self.closed.append(text)


async def test_lookahead_prepares_next_turn_but_audio_never_overlaps_or_reorders():
    first_playing = asyncio.Event()
    release = asyncio.Event()
    order, intervals = [], []
    translator, speech = Translator(), Speech()

    class Transport:
        async def speak(self, _code, _speaker, _target, chunks, first):
            order.append(first.latency_context['utterance_id'])
            intervals.append(('start', time.monotonic()))
            async for _ in chunks:
                first()
            if len(order) == 1:
                first_playing.set()
                await release.wait()
            intervals.append(('end', time.monotonic()))

    pipeline, state, source = setup(translator, speech, Transport())
    try:
        one = await pipeline.submit(state, source, "first", from_audio=True)
        await asyncio.wait_for(first_playing.wait(), 1)
        two = await pipeline.submit(state, source, "second", from_audio=True)
        for _ in range(50):
            if len(speech.requests) == 2:
                break
            await asyncio.sleep(.005)
        assert speech.requests == ['first', 'second']
        assert order == [one]  # Prepared PCM must not enter the current output.
        release.set()
        await asyncio.wait_for(pipeline.queues[(state.room.code, source.id)].join(), 1)
        assert order == [one, two]
        assert [kind for kind, _ in intervals] == ['start', 'end', 'start', 'end']
        assert all(turn.status == 'complete' for turn in state.turns)
        rows = list(state.performance_samples)
        assert all(row.preparation_ms is not None and row.output_wait_ms is not None for row in rows)
    finally:
        release.set()
        await pipeline.aclose()


async def test_stale_unstarted_turn_is_cancelled_visibly_before_provider_use():
    entered, release = asyncio.Event(), asyncio.Event()
    translator, speech = Translator(), Speech()

    class Transport:
        async def speak(self, _code, _speaker, _target, chunks, first):
            async for _ in chunks:
                first()
            entered.set()
            await release.wait()

    pipeline, state, source = setup(translator, speech, Transport(), lookahead=1, age=.1)
    events = []
    state.broadcast = lambda kind, data: events.append((kind, data))
    try:
        await pipeline.submit(state, source, 'first')
        await asyncio.wait_for(entered.wait(), 1)
        stale = await pipeline.submit(state, source, 'keep this caption')
        # Adjust only the queued fixture timestamp; no wall-clock sleep required.
        pipeline.waiting[(state.room.code, source.id)][stale].queued_at -= 1
        release.set()
        await asyncio.wait_for(pipeline.queues[(state.room.code, source.id)].join(), 1)
        assert translator.requests == speech.requests == ['first']
        assert state.turns[-1].text == 'keep this caption' and state.turns[-1].status == 'error'
        assert state.turns[-1].recovery_reason == 'queue_expired'
        row = next(r for r in state.performance_samples if r.utterance_id == stale)
        assert row.status == 'cancelled' and row.error_stage == 'queue_expired' and row.total_ms is None
        assert any(kind == 'pipeline.error' and 'skipped' in data['message'] for kind, data in events)
    finally:
        release.set()
        await pipeline.aclose()


async def test_stale_prepared_turn_never_cuts_off_previous_audio():
    playing, release = asyncio.Event(), asyncio.Event()
    translator, speech = Translator(), Speech()
    starts = []

    class Transport:
        async def speak(self, _code, _speaker, _target, chunks, first):
            starts.append(first.latency_context['utterance_id'])
            async for _ in chunks:
                first()
            playing.set()
            await release.wait()

    pipeline, state, source = setup(translator, speech, Transport(), age=.1)
    try:
        one = await pipeline.submit(state, source, 'first')
        await asyncio.wait_for(playing.wait(), 1)
        two = await pipeline.submit(state, source, 'second')
        three = await pipeline.submit(state, source, 'third')
        await asyncio.sleep(.15)
        assert starts == [one] and not release.is_set()
        assert state.turns[0].status == 'processing'
        row = next(r for r in state.performance_samples if r.utterance_id == two)
        assert row.status == 'cancelled' and row.error_stage == 'queue_expired'
        assert translator.requests == ['first', 'second']
        release.set()
        await asyncio.wait_for(pipeline.queues[(state.room.code, source.id)].join(), 1)
        assert state.turns[0].status == 'complete'
        assert starts == [one]
        third_row = next(r for r in state.performance_samples if r.utterance_id == three)
        assert third_row.status == 'cancelled' and third_row.error_stage == 'queue_expired'
    finally:
        release.set()
        await pipeline.aclose()


async def test_lookahead_is_bounded_and_cancel_closes_all_prepared_streams():
    playing = asyncio.Event()
    translator = Translator()
    closed = []
    produced = []

    class EndlessSpeech:
        async def synthesize(self, text, *_args):
            try:
                while True:
                    produced.append(text)
                    yield b'\0\1' * 2400
            finally:
                closed.append(text)

    class Transport:
        async def speak(self, _code, _speaker, _target, chunks, first):
            first()
            playing.set()
            await asyncio.Event().wait()

    pipeline, state, source = setup(translator, EndlessSpeech(), Transport())
    try:
        await pipeline.submit(state, source, 'first')
        await asyncio.wait_for(playing.wait(), 1)
        for text in ('second', 'third', 'fourth'):
            await pipeline.submit(state, source, text)
        await asyncio.sleep(.02)
        assert translator.requests == ['first', 'second']
        assert len(produced) <= 14  # Queue four + consumer/producer frames per turn.
        await asyncio.wait_for(pipeline.cancel_speaker(state.room.code, source.id), 1)
        assert sorted(closed) == ['first', 'second']
        assert all(turn.status == 'error' for turn in state.turns)
        assert not pipeline.workers and not pipeline.active and not pipeline.waiting
    finally:
        await pipeline.aclose()


async def test_subscriber_readiness_precedes_synthesis_prefetch():
    ready = asyncio.Event()
    translator, speech = Translator(), Speech()

    class Transport:
        async def prepare_output(self, *_args):
            await ready.wait()

        async def speak(self, _code, _speaker, _target, chunks, first):
            async for _ in chunks:
                first()

    pipeline, state, source = setup(translator, speech, Transport())
    try:
        await pipeline.submit(state, source, 'first')
        await asyncio.sleep(.01)
        assert translator.requests == ['first'] and speech.requests == []
        ready.set()
        await asyncio.wait_for(pipeline.queues[(state.room.code, source.id)].join(), 1)
        assert speech.requests == ['first']
    finally:
        await pipeline.aclose()


async def test_cancel_in_progress_rejects_replacement_worker_and_allows_clean_restart():
    entered, closing, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    translator = Translator()

    class SlowCleanupSpeech:
        async def synthesize(self, text, *_args):
            entered.set()
            try:
                await asyncio.Event().wait()
                yield b'\0\1'
            finally:
                closing.set()
                await release.wait()

    class Transport:
        async def speak(self, _code, _speaker, _target, chunks, first):
            async for _ in chunks: first()

    pipeline, state, source = setup(translator, SlowCleanupSpeech(), Transport())
    try:
        await pipeline.submit(state, source, 'first')
        await asyncio.wait_for(entered.wait(), 1)
        stop = asyncio.create_task(pipeline.cancel_speaker(state.room.code, source.id))
        await asyncio.wait_for(closing.wait(), 1)
        duplicate = asyncio.create_task(pipeline.cancel_speaker(state.room.code, source.id))
        with pytest.raises(HTTPException) as exc:
            await pipeline.submit(state, source, 'cannot replace during cleanup')
        assert exc.value.status_code == 409
        assert len(state.turns) == 1 and not duplicate.done()
        release.set()
        await asyncio.wait_for(asyncio.gather(stop, duplicate), 1)
        assert not pipeline.cancelling and not pipeline.workers and not pipeline.queues
        pipeline.tts = Speech()
        await pipeline.submit(state, source, 'restart')
        await asyncio.wait_for(pipeline.queues[(state.room.code, source.id)].join(), 1)
        assert state.turns[-1].status == 'complete'
    finally:
        release.set()
        await pipeline.aclose()


async def queue_fixture(lookahead):
    """Controlled delay fixture. Timing values are NOT live translation benchmarks."""
    first_playing = asyncio.Event()
    translator = Translator()
    starts = []

    class DelayedSpeech:
        async def synthesize(self, text, *_args):
            await asyncio.sleep(.06)
            yield b'\1\0' * 240

    class Transport:
        async def speak(self, _code, _speaker, _target, chunks, first):
            async for _ in chunks:
                starts.append(time.perf_counter())
                first()
            first_playing.set()
            await asyncio.sleep(.16)

    pipeline, state, source = setup(translator, DelayedSpeech(), Transport(), lookahead=lookahead)
    try:
        await pipeline.submit(state, source, 'first')
        await asyncio.wait_for(first_playing.wait(), 1)
        second = await pipeline.submit(state, source, 'second')
        await asyncio.wait_for(pipeline.queues[(state.room.code, source.id)].join(), 2)
        row = next(r for r in state.performance_samples if r.utterance_id == second)
        return {'queue_ms':row.queue_ms, 'output_wait_ms':row.output_wait_ms,
                'first_pcm_from_enqueue_ms':row.total_ms,
                'preparation_ms':row.preparation_ms, 'completed':2}
    finally:
        await pipeline.aclose()


async def test_local_before_after_overlap_fixture(tmp_path):
    before = await queue_fixture(1)
    after = await queue_fixture(2)
    assert before['queue_ms'] > 100 and after['queue_ms'] < 50
    assert after['first_pcm_from_enqueue_ms'] < before['first_pcm_from_enqueue_ms'] - 25
    assert after['output_wait_ms'] > 50  # Waiting was not hidden from the report.
    result = {'kind':'offline_mocked_queue_overlap', 'provider_calls':0, 'baseline_lookahead':1,
              'updated_lookahead':2, 'before':before, 'after':after,
              'live_latency_claim':False}
    (tmp_path/'queue-overlap.json').write_text(json.dumps(result,indent=2))
    print('QUEUE_FIXTURE '+json.dumps(result))
