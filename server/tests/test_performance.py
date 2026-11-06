import asyncio
import json

import pytest
from conftest import auth, create_member

from charcha.config import Settings
from charcha.errors import ProviderError
from charcha.models import Participant, PerformanceSample, Turn, VoiceProfile
from charcha.providers.demo import SAMPLES, DemoTranslator
from charcha.services.performance import milliseconds, performance_snapshot
from charcha.services.pipeline import Pipeline, WorkItem
from charcha.services.readiness import readiness_snapshot
from charcha.store import Store, StoredVoice


def test_performance_requires_membership_for_exact_room_and_has_no_transcript(client):
    code, member = create_member(client)
    _, outsider = create_member(client)
    route = f"/api/rooms/{code}/performance"
    assert client.get(route).status_code == 401
    assert client.get(route, headers=auth(outsider)).status_code == 403
    response = client.get(route, headers=auth(member))
    assert response.status_code == 200
    data = response.json()
    assert data["samples"] == []
    assert data["summary"]["p50_ms"] is data["summary"]["p95_ms"] is None
    assert data["measurement"]["stt"] == "processing_to_transcript"
    assert data["measurement"]["receiver_playback_measured"] is False
    assert member["session_token"] not in response.text
    assert "speaker_name" not in response.text


def test_readiness_shows_configuration_in_demo_without_exposing_values(client):
    settings = Settings(mode="demo", gnani_api_key="secret-gnani-value",
                        livekit_api_secret="secret-livekit-value", _env_file=None)
    data = readiness_snapshot(settings)
    encoded = json.dumps(data)
    rows = {row["key"]: row for row in data["requirements"]}
    assert rows["GNANI_API_KEY"]["configured"] is True
    assert rows["LIVEKIT_API_SECRET"]["configured"] is True
    assert rows["CHARCHA_MODE"]["configured"] is False
    assert rows["EVON_BASE_URL"]["configured"] is False
    assert rows["EVON_API_KEY"]["required"] is False
    assert data["provider_verification"] == "not_checked"
    assert "secret-gnani-value" not in encoded
    assert "secret-livekit-value" not in encoded
    assert all(row["status"] == "manual" for row in data["deployment_checks"])
    # Readiness endpoint is intentionally public but redacted, just like health.
    client.app.state.settings.gnani_api_key = settings.gnani_api_key
    assert client.get("/api/readiness").status_code == 200


def test_percentiles_exclude_simulated_forwarded_failed_and_cancelled_rows_and_bound_retention():
    store = Store(Settings(mode="live", _env_file=None))
    state = store.create_room("Bounded timings")
    for index in range(1005):
        state.performance_samples.append(PerformanceSample(
            utterance_id=str(index), source_language="hi", target_language="ta",
            input_kind="text", measurement="server_first_pcm", total_ms=index,
        ))
    assert len(state.performance_samples) == 1000
    assert state.performance_samples[0].utterance_id == "5"
    state.performance_samples.clear()
    for value in range(1, 21):
        state.performance_samples.append(PerformanceSample(
            utterance_id=str(value), source_language="hi", target_language="ta",
            input_kind="text", measurement="server_first_pcm", total_ms=value * 10,
        ))
    for measurement, status in [("simulated", "complete"), ("source_forwarded", "complete"),
                                ("server_first_pcm", "error"), ("server_first_pcm", "cancelled")]:
        state.performance_samples.append(PerformanceSample(
            utterance_id="excluded", source_language="hi", target_language="bn",
            input_kind="audio", measurement=measurement, status=status, total_ms=99999,
        ))
    data = performance_snapshot(state)
    assert data["summary"]["p50_ms"] == 100
    assert data["summary"]["p95_ms"] == 190
    assert data["summary"]["sample_count"] == 24
    assert data["summary"]["live_sample_count"] == 20
    assert data["summary"]["error_count"] == data["summary"]["cancelled_count"] == 1
    assert data["summary"]["forwarded_count"] == data["summary"]["simulated_count"] == 1
    directions = {row["target_language"]: row for row in data["summary"]["by_direction"]}
    assert directions["bn"]["p95_ms"] is None
    assert directions["ta"]["live_sample_count"] == 20


class Clock:
    def __init__(self):
        self.value = 10.0

    def __call__(self):
        return self.value


def live_pipeline(translator, speech=None):
    store = Store(Settings(mode="live", _env_file=None))
    state = store.create_room("Measured branches")
    speaker = Participant(id="source", name="Secret speaker name", language="hi")
    listener = Participant(id="target", name="Target", language="ta")
    state.room.participants = [speaker, listener]
    for person in state.room.participants:
        store.issue_session(state, person.id)
    return store, state, speaker, Pipeline(store, translator, speech)


@pytest.mark.parametrize("from_audio,reported_stt", [(True, 40.0), (False, None), (True, None)])
async def test_timing_ends_at_first_pcm_not_playout_and_typed_stt_is_na(monkeypatch, from_audio, reported_stt):
    clock = Clock()
    monkeypatch.setattr("charcha.services.pipeline.time.perf_counter", clock)

    class Translator:
        async def translate(self, *_args):
            clock.value += 0.025
            return "private translated text"

    class Speech:
        async def synthesize(self, *_args):
            yield b"pcm"

    class Transport:
        async def speak(self, code, speaker, target, chunks, callback):
            async for _chunk in chunks:
                clock.value += 0.075
                callback()
            clock.value += 5  # Must not contaminate first-PCM latency.

    _, state, speaker, pipeline = live_pipeline(Translator(), Speech())
    pipeline.transport = Transport()
    turn = Turn(speaker_id=speaker.id, speaker_name=speaker.name, source_language="hi", text="private input text")
    state.turns.append(turn)
    item = WorkItem(state, speaker, turn, reported_stt, from_audio, queued_at=9.5, processing_at=9.7)
    await pipeline._process(item)
    data = performance_snapshot(state)
    row = data["samples"][0]
    assert row["queue_ms"] == 200
    assert row["mt_ms"] == 25
    assert row["tts_first_pcm_ms"] == 75
    assert row["total_ms"] == 600 + (reported_stt or 0)
    assert row["stt_ms"] == (reported_stt if from_audio else None)
    assert row["input_kind"] == ("audio" if from_audio else "text")
    assert row["voice_mode"] == "standard"
    assert row["error_stage"] is None
    assert state.metrics.total_ms == row["total_ms"]
    assert "private" not in json.dumps(data)
    assert "Secret speaker name" not in json.dumps(data)


async def test_language_branches_record_failure_stage_without_stopping_successful_branch():
    class Translator:
        async def translate(self, text, source, target):
            if target == "bn":
                raise ProviderError("sensitive upstream response must not be stored")
            return "translated"

    class Speech:
        async def synthesize(self, *_args):
            yield b"pcm"

    class Transport:
        async def speak(self, code, speaker, target, chunks, callback):
            async for _chunk in chunks:
                callback()

    store, state, speaker, pipeline = live_pipeline(Translator(), Speech())
    bengali = Participant(name="Bengali", language="bn")
    state.room.participants.append(bengali)
    store.issue_session(state, bengali.id)
    pipeline.transport = Transport()
    try:
        await pipeline.submit(state, speaker, "private sentence")
        await asyncio.wait_for(pipeline.queues[(state.room.code, speaker.id)].join(), 1)
        data = performance_snapshot(state)
        rows = {row["target_language"]: row for row in data["samples"]}
        assert rows["bn"]["status"] == "error"
        assert rows["bn"]["error_stage"] == "mt"
        assert rows["bn"]["total_ms"] is None
        assert rows["ta"]["status"] == "complete"
        assert data["summary"]["live_sample_count"] == 1
        assert data["summary"]["error_count"] == 1
        assert "sensitive upstream" not in json.dumps(data)
    finally:
        await pipeline.aclose()


async def test_cancellation_covers_running_and_queued_branches():
    entered = asyncio.Event()

    class Translator:
        async def translate(self, *_args):
            entered.set()
            await asyncio.Event().wait()

    _, state, speaker, pipeline = live_pipeline(Translator())
    try:
        first = await pipeline.submit(state, speaker, "first")
        await asyncio.wait_for(entered.wait(), 1)
        second = await pipeline.submit(state, speaker, "second")
        await pipeline.cancel_speaker(state.room.code, speaker.id)
        data = performance_snapshot(state)
        rows = {row["utterance_id"]: row for row in data["samples"]}
        assert rows[first]["status"] == rows[second]["status"] == "cancelled"
        assert rows[first]["error_stage"] == "mt"
        assert rows[second]["error_stage"] == "queue"
        assert data["summary"]["cancelled_count"] == 2
        assert data["summary"]["p50_ms"] is None
    finally:
        await pipeline.aclose()


@pytest.mark.parametrize("failure", ["synthesis", "no_audio", "playout"])
async def test_audio_failure_stage_and_missing_first_pcm_are_not_successes(failure):
    class Translator:
        async def translate(self, *_args):
            return "translation"

    class Speech:
        async def synthesize(self, *_args):
            if failure == "synthesis":
                raise ProviderError("upstream failure")
            if failure == "playout":
                yield b"pcm"

    class Transport:
        async def speak(self, code, speaker, target, chunks, callback):
            async for _chunk in chunks:
                callback()
            if failure == "playout":
                raise ProviderError("connection lost after dispatch")

    _, state, speaker, pipeline = live_pipeline(Translator(), Speech())
    pipeline.transport = Transport()
    try:
        await pipeline.submit(state, speaker, "example")
        await asyncio.wait_for(pipeline.queues[(state.room.code, speaker.id)].join(), 1)
        data = performance_snapshot(state)
        row = data["samples"][0]
        assert row["status"] == "error"
        assert row["error_stage"] == ("playout" if failure == "playout" else "tts")
        assert (row["total_ms"] is not None) == (failure == "playout")
        assert data["summary"]["live_sample_count"] == 0
        assert data["summary"]["p95_ms"] is None
    finally:
        await pipeline.aclose()


async def test_demo_has_no_timings_and_same_language_audio_is_separate():
    demo_store = Store(Settings(mode="demo", _env_file=None))
    state = demo_store.create_room("Demonstration")
    speaker = Participant(name="Speaker", language="hi")
    state.room.participants = [speaker, Participant(name="Tamil", language="ta")]
    pipeline = Pipeline(demo_store, DemoTranslator(), None)
    try:
        await pipeline.submit(state, speaker, SAMPLES[0]["hi"])
        await asyncio.wait_for(pipeline.queues[(state.room.code, speaker.id)].join(), 1)
        data = performance_snapshot(state)
        row = data["samples"][0]
        assert row["measurement"] == "simulated"
        assert all(row[key] is None for key in ["queue_ms", "stt_ms", "mt_ms", "tts_first_pcm_ms", "total_ms"])
        assert data["summary"]["p95_ms"] is None
    finally:
        await pipeline.aclose()

    store, state, speaker, pipeline = live_pipeline(None)
    state.room.participants[1].language = "hi"
    try:
        await pipeline.submit(state, speaker, "forward source audio", 123, True)
        await asyncio.wait_for(pipeline.queues[(state.room.code, speaker.id)].join(), 1)
        data = performance_snapshot(state)
        assert data["samples"][0]["measurement"] == "source_forwarded"
        assert data["samples"][0]["total_ms"] is None
        assert data["summary"]["live_sample_count"] == 0
        assert data["summary"]["forwarded_count"] == 1
        assert data["summary"]["p50_ms"] is None
    finally:
        await pipeline.aclose()


async def test_same_language_typed_clone_records_voice_mode_and_skips_mt():
    class Translator:
        async def translate(self, *_args):
            raise AssertionError("Same-language text must bypass MT")

    class Speech:
        async def synthesize(self, text, language, embedding):
            assert language == "hi"
            assert embedding == {"private_embedding": [0.1, 0.2]}
            yield b"pcm"

    class Transport:
        async def speak(self, code, speaker, target, chunks, callback):
            async for _chunk in chunks:
                callback()

    store, state, speaker, pipeline = live_pipeline(Translator(), Speech())
    state.room.participants[1].language = "hi"
    speaker.voice_mode = "cloned"
    profile = VoiceProfile(name="Private profile name", mode="live")
    store.voices[profile.id] = StoredVoice(profile, "private_owner_digest", {"private_embedding": [0.1, 0.2]})
    state.voice_profiles[speaker.id] = profile.id
    pipeline.transport = Transport()
    try:
        await pipeline.submit(state, speaker, "Same-language typed message")
        await asyncio.wait_for(pipeline.queues[(state.room.code, speaker.id)].join(), 1)
        data = performance_snapshot(state)
        row = data["samples"][0]
        assert row["voice_mode"] == "cloned"
        assert row["input_kind"] == "text"
        assert row["mt_ms"] is row["stt_ms"] is None
        assert row["measurement"] == "server_first_pcm"
        assert row["status"] == "complete"
        assert row["total_ms"] is not None
        assert "private_" not in json.dumps(data)
        assert profile.id not in json.dumps(data)
    finally:
        await pipeline.aclose()


@pytest.mark.parametrize("case", ["forwarded", "failed", "no_listeners"])
async def test_turn_without_synthesized_success_clears_latest_legacy_stages_only(case):
    class Translator:
        async def translate(self, *_args):
            raise ProviderError("fixture unavailable")

    _, state, speaker, pipeline = live_pipeline(Translator())
    if case == "forwarded":
        state.room.participants[1].language = "hi"
    elif case == "no_listeners":
        state.room.participants = [speaker]
    state.performance_samples.append(PerformanceSample(
        utterance_id="earlier-success", source_language="hi", target_language="ta",
        input_kind="audio", measurement="server_first_pcm", total_ms=500,
    ))
    for name in ["stt_ms", "mt_ms", "tts_ms", "total_ms"]:
        setattr(state.metrics, name, 123)
    state.metrics.p50_ms = state.metrics.p95_ms = 500
    try:
        await pipeline.submit(state, speaker, "latest turn", 20, True)
        await asyncio.wait_for(pipeline.queues[(state.room.code, speaker.id)].join(), 1)
        assert state.metrics.stt_ms == state.metrics.mt_ms == state.metrics.tts_ms == state.metrics.total_ms == 0
        assert state.metrics.p50_ms == state.metrics.p95_ms == 500
        assert performance_snapshot(state)["summary"]["p95_ms"] == 500
        assert state.metrics.turns == 1
        if case == "no_listeners":
            assert len(state.performance_samples) == 1  # Only the earlier fixture row.
            assert state.turns[0].status == "complete"
    finally:
        await pipeline.aclose()


def test_invalid_measurements_cannot_reach_json():
    assert milliseconds(float("nan")) is None
    assert milliseconds(float("inf")) is None
    assert milliseconds(-1) is None
    assert milliseconds(None) is None


async def test_error_eviction_updates_legacy_percentiles_to_the_retained_window():
    class Translator:
        async def translate(self, *_args):
            raise ProviderError("fixture outage")

    _, state, speaker, pipeline = live_pipeline(Translator())
    state.performance_samples.append(PerformanceSample(
        utterance_id="old-success", source_language="hi", target_language="ta",
        input_kind="text", measurement="server_first_pcm", total_ms=500,
    ))
    for index in range(999):
        state.performance_samples.append(PerformanceSample(
            utterance_id=str(index), source_language="hi", target_language="ta",
            input_kind="text", measurement="server_first_pcm", status="error", error_stage="mt",
        ))
    state.metrics.p50_ms = state.metrics.p95_ms = 500
    try:
        await pipeline.submit(state, speaker, "latest error evicts oldest success")
        await asyncio.wait_for(pipeline.queues[(state.room.code, speaker.id)].join(), 1)
        assert performance_snapshot(state)["summary"]["p95_ms"] is None
        assert state.metrics.p50_ms == state.metrics.p95_ms == 0
    finally:
        await pipeline.aclose()
