"""Offline failure and cancellation fixtures: no provider connections or real keys."""
import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest

from artha_mesh.config import Settings
from artha_mesh.errors import ProviderError
from artha_mesh.providers.evon import EvonTranslator, completed_translation


def completion(text="நாளை வர வேண்டாம்.", *, finish="stop", **message_fields):
    return {"choices": [{"finish_reason": finish, "message": {
        "role": "assistant", "content": text, **message_fields,
    }}]}


@asynccontextmanager
async def adapter(handler, *, mode="live"):
    translator = EvonTranslator(Settings(
        mode=mode, evon_base_url="https://fixture.invalid/v1",
        evon_model="evon-fixture", evon_api_key="private-fixture-key", _env_file=None,
    ))
    await translator.client.aclose()
    translator.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        yield translator
    finally:
        await translator.aclose()


def attempts(translator):
    return next(row["used"] for row in translator.usage.snapshot()["resources"]
                if row["key"] == "mt_requests")


@pytest.mark.parametrize("payload", [
    completion("Tomorrow, come", finish="length"),
    completion("Tomorrow, come", finish=None),
    completion(finish="content_filter"),
    completion(finish="tool_calls"),
    {"choices": [{"message": {"content": "Finish status is missing"}}]},
    completion(reasoning_content="private analysis"),
    completion(reasoning="private analysis"),
    completion(refusal="Refused"),
    completion(tool_calls=[{"function": {"name": "private_tool"}}]),
    completion(function_call={"name": "private_tool"}),
    completion(role="user"),
    completion("<think>private analysis</think>வணக்கம்"),
    completion("private analysis</THINK>வணக்கம்"),
    completion("<analysis>private analysis</analysis>வணக்கம்"),
    completion("<|analysis|>private analysis"),
    completion(" " * 10),
    completion("x" * 8001),
    completion(None),
    completion([{"type": "text", "text": "Unsupported content array"}]),
    {"choices": [completion()["choices"][0], completion()["choices"][0]]},
    {"choices": [None]},
    [],
    None,
])
async def test_unfinished_or_wrong_channel_response_never_leaves_adapter(payload):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=payload)

    async with adapter(handler) as translator:
        with pytest.raises(ProviderError) as error:
            await translator.translate("कल मत आना।", "hi", "ta")
        assert len(seen) == 1  # Failure is surfaced, never automatically retried.
        assert attempts(translator) == 1  # An attempted response is not assumed free.
        assert str(error.value) == "Translation service failed; repeat the phrase or try again"


@pytest.mark.parametrize(("text", "source", "target"), [
    ("", "hi", "ta"), (" \n\t", "hi", "ta"), (None, "hi", "ta"),
    ("a" * 2001, "hi", "ta"), ("Hello", "unknown", "ta"),
    ("Hello", "hi", "unknown"), ("Hello", "unknown", "unknown"),
])
async def test_invalid_input_is_rejected_before_request_or_reservation(text, source, target):
    def unexpected_request(_request):
        pytest.fail("Invalid input must not leave the process")

    async with adapter(unexpected_request) as translator:
        with pytest.raises(ProviderError) as error:
            await translator.translate(text, source, target)
        assert not error.value.retryable
        assert attempts(translator) == 0


async def test_supported_same_language_remains_a_no_cost_bypass_even_when_disabled():
    def unexpected_request(_request):
        pytest.fail("Same-language bypass must not call a provider")

    async with adapter(unexpected_request, mode="transport") as translator:
        assert await translator.translate("  कल मत आना।  ", "hi", "hi") == "  कल मत आना।  "


async def test_timeout_remains_sanitized_and_is_not_retried():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("private-fixture-key private-provider-body", request=request)

    async with adapter(handler) as translator:
        with pytest.raises(ProviderError) as error:
            await translator.translate("Hello", "en", "ta")
        assert calls == 1
        assert "private" not in str(error.value)
        assert "fixture.invalid" not in str(error.value)
        assert attempts(translator) == 1


async def test_non_json_upstream_error_is_sanitized_without_retry():
    calls = 0

    def handler(_request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, text="private-provider-body")

    async with adapter(handler) as translator:
        with pytest.raises(ProviderError) as error:
            await translator.translate("Hello", "en", "ta")
        assert calls == 1
        assert "private" not in str(error.value)


async def test_cancellation_propagates_keeps_attempt_and_releases_provider_slot():
    started = asyncio.Event()
    cancelled = asyncio.Event()
    both_followups_started = asyncio.Event()
    calls = 0

    async def handler(_request):
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        if calls == 3:
            both_followups_started.set()
        await both_followups_started.wait()
        return httpx.Response(200, json=completion())

    async with adapter(handler) as translator:
        task = asyncio.create_task(translator.translate("कल मत आना।", "hi", "ta"))
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cancelled.is_set()
        assert calls == 1
        assert attempts(translator) == 1
        # Fill both available slots: this would deadlock if cancellation leaked one.
        results = await asyncio.wait_for(asyncio.gather(
            translator.translate("कल मत आना।", "hi", "ta"),
            translator.translate("कल मत आना।", "hi", "ta"),
        ), 1)
        assert results == ["நாளை வர வேண்டாம்."] * 2
        assert calls == 3
        assert attempts(translator) == 3


def test_completed_text_preserves_normal_script_punctuation_and_empty_reasoning_field():
    assert completed_translation(completion(
        "  நாளை 5:30 மணிக்கு வர வேண்டாம்.\nஅடுத்த நாள் வாருங்கள்.  ", reasoning_content="",
    )) == "நாளை 5:30 மணிக்கு வர வேண்டாம்.\nஅடுத்த நாள் வாருங்கள்."
