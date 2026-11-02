from __future__ import annotations

import re
from urllib.parse import urlsplit

import httpx

from ..config import Settings
from ..errors import ProviderError
from ..models import LANGUAGE_NAMES
from ..services.usage import UsageGuard, provider_error
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


class EvonTranslator:
    """Evon open weights hosted behind an OpenAI-compatible chat completion API."""

    def __init__(self, settings: Settings, usage: UsageGuard | None = None):
        self.settings = settings
        self.usage = usage or UsageGuard(settings)
        self.client = httpx.AsyncClient(timeout=settings.provider_timeout_seconds,
                                       follow_redirects=False, trust_env=False)

    async def translate(self, text: str, source: str, target: str) -> str:
        if (not isinstance(source, str) or source not in LANGUAGE_NAMES
                or not isinstance(target, str) or target not in LANGUAGE_NAMES):
            raise ProviderError("Unsupported translation language", False)
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            raise ProviderError("Utterances must contain 1–2000 characters", False)
        if source == target:
            return text
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
            "max_tokens": 1024,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        try:
            async with self.usage.operation({"mt_requests": 1, "mt_characters": len(text)}):
                response = await self.client.post(
                    self.settings.evon_base_url.rstrip("/") + "/chat/completions",
                    headers=headers, json=request,
                )
                response.raise_for_status()
                translated = completed_translation(response.json())
                if any(value and value in translated for value in (key, modal_key, modal_secret)):
                    raise ValueError("Unexpected credential reflection")
                return check_target_script(translated, target)
        except httpx.HTTPStatusError as exc:
            raise provider_error("Translation service rejected the request; check provider access and quota", status=exc.response.status_code) from None
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            # Deliberately do not attach request URL/headers/body or upstream text.
            raise ProviderError("Translation service failed; repeat the phrase or try again") from None

    async def aclose(self):
        await self.client.aclose()
