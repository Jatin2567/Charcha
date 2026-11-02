from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from urllib.parse import urlsplit

import httpx

from ..config import Settings
from ..errors import ProviderError
from ..models import LANGUAGE_NAMES
from ..services.usage import UsageGuard, provider_error
from .clauses import ClauseSplitter
from .translation_prompt import PROMPT_VERSION, check_target_script, translation_messages


_REASONING_MARKER = re.compile(
    r"</?(?:think|thinking|analysis|reasoning)(?=[\s>])|<\|(?:analysis|assistant|im_start|im_end)\|>",
    re.IGNORECASE,
)


def modal_proxy_headers(endpoint: str, key: str = "", secret: str = "") -> dict[str, str]:
    """Send the optional proxy credential pair only to Modal's HTTPS origin."""
    if not key and not secret:
        return {}
    if not key or not secret or any(
        len(value) > 4096 or any(not 33 <= ord(char) <= 126 for char in value)
        for value in (key, secret)
    ):
        raise ValueError("Invalid proxy authentication configuration")
    parsed = urlsplit(endpoint)
    host = parsed.hostname or ""
    if (parsed.scheme != "https" or not host.endswith(".modal.run")
            or not host.removesuffix(".modal.run") or parsed.port not in (None, 443)
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("Invalid proxy authentication destination")
    return {"Modal-Key": key, "Modal-Secret": secret}


def completed_translation(payload: object) -> str:
    """Accept a finished text answer, never a partial answer or reasoning channel.

    This checks the serving contract, not translation accuracy. Meaning, language
    and preservation of negation still require bilingual acceptance testing.
    """
    if not isinstance(payload, dict):
        raise ValueError("Invalid translation response")
    choices = payload.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError("Invalid translation response")
    choice = choices[0]
    if not isinstance(choice, dict) or choice.get("finish_reason") != "stop":
        # A token-limit cutoff can omit a final negation or condition. Do not speak
        # partial text, silently strip it, or spend credits retrying automatically.
        raise ValueError("Incomplete translation response")
    message = choice.get("message")
    if not isinstance(message, dict) or message.get("role", "assistant") != "assistant":
        raise ValueError("Invalid translation response")
    if (message.get("tool_calls") or message.get("function_call")
            or message.get("refusal")
            or message.get("reasoning_content") not in (None, "")
            or message.get("reasoning") not in (None, "")):
        raise ValueError("Unexpected translation channel")
    text = message.get("content")
    if (not isinstance(text, str) or not text.strip() or len(text) > 8000
            or _REASONING_MARKER.search(text)):
        raise ValueError("Invalid translation response")
    return text.strip()


def stream_delta(payload: object) -> tuple[str, str | None]:
    """Return (content delta, finish_reason) from one streamed chunk.

    Reasoning, tool and refusal channels are rejected exactly as in the
    non-streamed contract; a role-only first chunk yields an empty delta.
    """
    if not isinstance(payload, dict):
        raise ValueError("Invalid translation stream")
    choices = payload.get("choices")
    if not isinstance(choices, list):
        raise ValueError("Invalid translation stream")
    if not choices:
        return "", None  # usage-only trailer chunk
    if len(choices) != 1 or not isinstance(choices[0], dict):
        raise ValueError("Invalid translation stream")
    choice = choices[0]
    delta = choice.get("delta") or {}
    if not isinstance(delta, dict) or delta.get("role", "assistant") != "assistant":
        raise ValueError("Invalid translation stream")
    if (delta.get("tool_calls") or delta.get("function_call") or delta.get("refusal")
            or delta.get("reasoning_content") not in (None, "")
            or delta.get("reasoning") not in (None, "")):
        raise ValueError("Unexpected translation channel")
    content = delta.get("content") or ""
    if not isinstance(content, str):
        raise ValueError("Invalid translation stream")
    finish = choice.get("finish_reason")
    if finish is not None and not isinstance(finish, str):
        raise ValueError("Invalid translation stream")
    return content, finish


class EvonTranslator:
    """Evon open weights hosted behind an OpenAI-compatible chat completion API."""

    def __init__(self, settings: Settings, usage: UsageGuard | None = None):
        self.settings = settings
        self.usage = usage or UsageGuard(settings)
        self.client = httpx.AsyncClient(timeout=settings.provider_timeout_seconds,
                                       follow_redirects=False, trust_env=False)

    def _prepare(self, text: str, source: str, target: str, stream: bool):
        if (not isinstance(source, str) or source not in LANGUAGE_NAMES
                or not isinstance(target, str) or target not in LANGUAGE_NAMES):
            raise ProviderError("Unsupported translation language", False)
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            raise ProviderError("Utterances must contain 1–2000 characters", False)
        if source == target:
            return None
        self.usage.require_live()
        if not self.settings.evon_base_url or not self.settings.evon_model:
            raise ProviderError("Evon hosting is not configured", False)
        headers = {"Content-Type": "application/json"}
        key = self.settings.evon_api_key.get_secret_value()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        modal_key = self.settings.evon_modal_key.get_secret_value()
        modal_secret = self.settings.evon_modal_secret.get_secret_value()
        try:
            headers.update(modal_proxy_headers(self.settings.evon_base_url, modal_key, modal_secret))
        except ValueError:
            # Reject configuration before reserving a provider operation.
            raise ProviderError("Evon proxy authentication or destination is invalid", False) from None
        request = {
            "model": self.settings.evon_model,
            "messages": translation_messages(text, source, target),
            "temperature": 0.0,
            # Never lower this to gain speed: a cutoff drops trailing negations.
            "max_tokens": 1024,
            "stream": stream,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if stream:
            request["stream_options"] = {"include_usage": False}
        url = self.settings.evon_base_url.rstrip("/") + "/chat/completions"
        return url, headers, request, tuple(v for v in (key, modal_key, modal_secret) if v)

    async def translate(self, text: str, source: str, target: str) -> str:
        prepared = self._prepare(text, source, target, stream=False)
        if prepared is None:
            return text
        url, headers, request, secrets = prepared
        try:
            async with self.usage.operation({"mt_requests": 1, "mt_characters": len(text)}):
                response = await self.client.post(url, headers=headers, json=request)
                response.raise_for_status()
                translated = completed_translation(response.json())
                if any(value in translated for value in secrets):
                    raise ValueError("Unexpected credential reflection")
                return check_target_script(translated, target)
        except httpx.HTTPStatusError as exc:
            raise provider_error("Translation service rejected the request; check provider access and quota", status=exc.response.status_code) from None
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            # Deliberately do not attach request URL/headers/body or upstream text.
            raise ProviderError("Translation service failed; repeat the phrase or try again") from None

    async def translate_stream(self, text: str, source: str, target: str) -> AsyncIterator[str]:
        """Yield the translation clause by clause while the model is still decoding.

        The whole source utterance is sent in one request, so meaning is decided
        with full context; only speech start moves earlier. One usage operation
        is charged per request. If the stream ends without ``finish_reason ==
        "stop"`` (for example a token-limit cutoff) a ProviderError is raised
        after the clauses already released, and nothing after the cutoff is
        spoken. The caller must surface that error to participants.
        """
        prepared = self._prepare(text, source, target, stream=True)
        if prepared is None:
            yield text
            return
        url, headers, request, secrets = prepared
        splitter = ClauseSplitter(self.settings.evon_clause_min_chars,
                                  self.settings.evon_clause_max_chars)
        full = ""

        def checked(piece: str) -> str | None:
            clause = piece.strip()
            if not clause:
                return None
            if any(value in full for value in secrets):
                raise ValueError("Unexpected credential reflection")
            return check_target_script(clause, target)

        try:
            async with self.usage.operation({"mt_requests": 1, "mt_characters": len(text)}):
                async with self.client.stream("POST", url, headers=headers, json=request) as response:
                    response.raise_for_status()
                    finish: str | None = None
                    done = False
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or line.startswith(":"):
                            continue
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            done = True
                            break
                        if finish is not None:
                            # Only an empty usage trailer may follow the finish chunk.
                            delta, extra = stream_delta(json.loads(data))
                            if delta or extra:
                                raise ValueError("Invalid translation stream")
                            continue
                        delta, finish = stream_delta(json.loads(data))
                        if delta:
                            full += delta
                            if len(full) > 8000 or _REASONING_MARKER.search(full):
                                raise ValueError("Invalid translation response")
                            for piece in splitter.feed(delta):
                                clause = checked(piece)
                                if clause:
                                    yield clause
                    if finish != "stop" or not done:
                        raise ValueError("Incomplete translation response")
                    if not full.strip():
                        raise ValueError("Invalid translation response")
                    check_target_script(full.strip(), target)
                    for piece in splitter.flush():
                        clause = checked(piece)
                        if clause:
                            yield clause
        except httpx.HTTPStatusError as exc:
            raise provider_error("Translation service rejected the request; check provider access and quota", status=exc.response.status_code) from None
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            raise ProviderError("Translation service failed; repeat the phrase or try again") from None

    async def aclose(self):
        await self.client.aclose()
