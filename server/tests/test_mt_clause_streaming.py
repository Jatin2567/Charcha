"""Clause-level MT streaming: offline fixtures only, no provider connections."""
import asyncio
import json
from contextlib import asynccontextmanager

import httpx
import pytest

from artha_mesh.config import Settings
from artha_mesh.errors import ProviderError
from artha_mesh.models import Participant, Turn
from artha_mesh.providers.clauses import ClauseSplitter
from artha_mesh.providers.evon import EvonTranslator, stream_delta
from artha_mesh.services.performance import performance_snapshot
from artha_mesh.services.pipeline import Pipeline, WorkItem
from artha_mesh.store import Store

KEY = "private-fixture-key"


def sse(deltas, finish="stop", done=True, **extra):
    lines = [json.dumps({"choices": [{"delta": {"role": "assistant"}, "finish_reason": None}]})]
    for index, delta in enumerate(deltas):
        last = index == len(deltas) - 1
        lines.append(json.dumps({"choices": [{"delta": {"content": delta, **(extra if last else {})},
                                              "finish_reason": finish if last else None}]}))
    body = "".join(f"data: {line}\n\n" for line in lines)
    return body + ("data: [DONE]\n\n" if done else "")


@asynccontextmanager
async def adapter(body, seen=None):
    def handler(request):
        if seen is not None:
            seen.append(json.loads(request.content))
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    translator = EvonTranslator(Settings(mode="live", evon_base_url="https://fixture.invalid/v1",
                                         evon_model="evon-fixture", evon_api_key=KEY, _env_file=None))
    await translator.client.aclose()
    translator.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        yield translator
    finally:
        await translator.aclose()


async def collect(translator, text="कल मत आना, मैं घर पर नहीं रहूँगा।", target="hi", source="en"):
    return [clause async for clause in translator.translate_stream(text, source, target)]


def used(translator, key):
    return next(row["used"] for row in translator.usage.snapshot()["resources"] if row["key"] == key)


# --- splitter -------------------------------------------------------------

def test_splitter_preserves_text_and_splits_on_danda_and_long_commas():
    splitter = ClauseSplitter(min_chars=10, max_chars=60)
    text = "कल मत आना। मैं घर पर नहीं रहूँगा, क्योंकि मुझे बाहर जाना है। ठीक है"
    pieces = []
    for char in text:
        pieces += splitter.feed(char)
    pieces += splitter.flush()
    assert "".join(pieces) == text
    assert [p.strip() for p in pieces] == [
        "कल मत आना।", "मैं घर पर नहीं रहूँगा,", "क्योंकि मुझे बाहर जाना है।", "ठीक है"]


def test_splitter_keeps_short_comma_fragments_and_decimals_together():
    splitter = ClauseSplitter(min_chars=24, max_chars=180)
    pieces = splitter.feed("हाँ, price is 3.5 lakh, okay") + splitter.flush()
    assert pieces == ["हाँ, price is 3.5 lakh, okay"]


def test_splitter_cuts_unpunctuated_text_at_a_space():
    splitter = ClauseSplitter(min_chars=10, max_chars=40)
    text = "word " * 20
    pieces = splitter.feed(text) + splitter.flush()
    assert "".join(pieces) == text
    assert all(len(p) <= 40 for p in pieces) and len(pieces) > 1
    assert all(not p.startswith(" ") for p in pieces)


def test_splitter_rejects_invalid_bounds():
    with pytest.raises(ValueError):
        ClauseSplitter(min_chars=50, max_chars=40)


# --- stream chunk contract -------------------------------------------------

@pytest.mark.parametrize("payload", [
    {"choices": [{"delta": {"reasoning_content": "x"}}]},
    {"choices": [{"delta": {"reasoning": "x"}}]},
    {"choices": [{"delta": {"tool_calls": [{}]}}]},
    {"choices": [{"delta": {"refusal": "no"}}]},
    {"choices": [{"delta": {"role": "user", "content": "x"}}]},
    {"choices": [{"delta": {"content": ["x"]}}]},
    {"choices": [{}, {}]},
    {"choices": None},
    [],
])
def test_stream_delta_rejects_other_channels(payload):
    with pytest.raises(ValueError):
        stream_delta(payload)


# --- adapter ---------------------------------------------------------------

async def test_stream_yields_clauses_and_counts_one_request():
    seen = []
    deltas = ["कल मत ", "आना, मैं घर पर ", "नहीं रहूँगा। ", "फिर मिलेंगे"]
    async with adapter(sse(deltas), seen) as translator:
        translator.settings.evon_clause_min_chars = 8
        clauses = await collect(translator)
        assert clauses == ["कल मत आना,", "मैं घर पर नहीं रहूँगा।", "फिर मिलेंगे"]
        assert used(translator, "mt_requests") == 1
    request = seen[0]
    assert request["stream"] is True and request["max_tokens"] == 1024
    assert request["chat_template_kwargs"] == {"enable_thinking": False}


@pytest.mark.parametrize("body", [
    sse(["कल मत आना, ", "मैं घर पर नहीं"], finish="length"),
    sse(["कल मत आना"], finish=None),
    sse(["कल मत आना"], done=False),
    sse(["<think>private</think>नमस्ते"]),
    sse(["नमस्ते"], reasoning_content="private"),
    sse([f"नमस्ते {KEY}"]),
    sse(["வணக்கம் நண்பரே"]),  # Tamil script for a Hindi target
    sse(["   "]),
    "data: {not json}\n\n",
])
async def test_stream_failures_raise_without_detail(body):
    async with adapter(body) as translator:
        with pytest.raises(ProviderError) as caught:
            await collect(translator)
        assert KEY not in str(caught.value) and "private" not in str(caught.value)


async def test_length_cutoff_never_releases_text_after_the_last_complete_clause():
    body = sse(["कल मत आना। ", "मैं घर पर नहीं"], finish="length")
    released = []
    async with adapter(body) as translator:
        translator.settings.evon_clause_min_chars = 8
        with pytest.raises(ProviderError):
            async for clause in translator.translate_stream("x", "en", "hi"):
                released.append(clause)
    assert released == ["कल मत आना।"]


async def test_same_language_stream_is_passthrough_without_usage():
    async with adapter("") as translator:
        assert await collect(translator, text="नमस्ते", source="hi", target="hi") == ["नमस्ते"]
        assert used(translator, "mt_requests") == 0


# --- pipeline ----------------------------------------------------------------

def streaming_pipeline(translator, speech, *, stream=True):
    store = Store(Settings(mode="live", evon_stream_clauses=stream, _env_file=None))
    state = store.create_room("Streaming")
    speaker = Participant(id="source", name="Speaker", language="en")
    listener = Participant(id="target", name="Listener", language="hi")
    state.room.participants = [speaker, listener]
    for person in state.room.participants:
        store.issue_session(state, person.id)
    pipeline = Pipeline(store, translator, speech)
    turn = Turn(speaker_id=speaker.id, speaker_name=speaker.name, source_language="en", text="private input")
    state.turns.append(turn)
    return state, turn, pipeline, WorkItem(state, speaker, turn, 10.0, True, queued_at=0.0, processing_at=0.0)


class Speech:
    def __init__(self, log):
        self.log = log

    async def synthesize(self, text, *_args):
        self.log.append(("tts", text))
        yield f"pcm:{text}".encode()


class Transport:
    def __init__(self, log):
        self.log = log
        self.played = []

    async def speak(self, code, speaker, target, chunks, callback):
        async for chunk in chunks:
            if not self.played:
                callback()
            self.played.append(chunk)
            self.log.append(("play", chunk))


async def test_first_audio_plays_before_translation_finishes_and_order_is_kept():
    log = []
    release = asyncio.Event()

    class Translator:
        async def translate(self, *_):
            raise AssertionError("streaming path must be used")

        async def translate_stream(self, *_):
            for clause in ["एक।", "दो,", "तीन।"]:
                log.append(("mt", clause))
                yield clause
                if clause == "एक।":
                    # The model keeps decoding only after the first clause played.
                    await asyncio.wait_for(release.wait(), 2)

    transport = Transport(log)
    original = transport.speak

    async def speak(*args):
        chunks = args[3]

        async def watch():
            async for chunk in chunks:
                release.set()
                yield chunk
        await original(*args[:3], watch(), args[4])

    transport.speak = speak
    state, turn, pipeline, item = streaming_pipeline(Translator(), Speech(log))
    pipeline.transport = transport
    events = []
    original_broadcast = state.broadcast
    state.broadcast = lambda kind, payload: (events.append((kind, payload)), original_broadcast(kind, payload))
    await pipeline._process(item)
    assert transport.played == ["pcm:एक।".encode(), "pcm:दो,".encode(), "pcm:तीन।".encode()]
    assert log.index(("play", "pcm:एक।".encode())) < log.index(("mt", "दो,"))
    assert turn.translations["hi"] == "एक। दो, तीन।"
    row = performance_snapshot(state)["samples"][0]
    assert row["mt_streamed"] is True and row["status"] == "complete"
    assert row["mt_complete_ms"] is not None and row["total_ms"] is not None
    ready = [payload for kind, payload in events if kind == "translation.ready"]
    assert ready[-1]["text"] == "एक। दो, तीन।" and ready[-1]["measurement"] == "text_ready"


async def test_mt_failure_after_first_clause_stops_audio_and_records_error():
    log = []

    class Translator:
        async def translate_stream(self, *_):
            yield "एक।"
            raise ProviderError("Translation service failed; repeat the phrase or try again")

    state, turn, pipeline, item = streaming_pipeline(Translator(), Speech(log))
    transport = Transport(log)
    pipeline.transport = transport
    await pipeline._process(item)
    assert transport.played == ["pcm:एक।".encode()]
    row = performance_snapshot(state)["samples"][0]
    assert row["status"] == "error"


async def test_flag_off_uses_full_translation_path():
    log = []

    class Translator:
        async def translate(self, *_):
            return "पूरा वाक्य।"

        async def translate_stream(self, *_):
            raise AssertionError("streaming disabled")
            yield  # pragma: no cover

    state, turn, pipeline, item = streaming_pipeline(Translator(), Speech(log), stream=False)
    pipeline.transport = Transport(log)
    await pipeline._process(item)
    assert ("tts", "पूरा वाक्य।") in log
    assert performance_snapshot(state)["samples"][0]["mt_streamed"] is False
