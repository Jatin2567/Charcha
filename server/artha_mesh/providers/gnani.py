from __future__ import annotations

import asyncio
import base64
import json
import time
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from dataclasses import dataclass

import httpx
import websockets

from ..config import Settings
from ..errors import ProviderError
from ..models import BCP47
from ..services.usage import UsageGuard, provider_error
from ..voice_catalog import select_stock_voice


@dataclass
class Transcript:
    text: str
    segment_id: str
    stt_ms: float | None


class GnaniSpeech:
    def __init__(self, settings: Settings, usage: UsageGuard | None = None):
        self.settings = settings
        self.usage = usage or UsageGuard(settings)
        self.client = httpx.AsyncClient(timeout=settings.provider_timeout_seconds)

    @property
    def headers(self) -> dict[str, str]:
        return {"X-API-Key-ID": self.settings.gnani_api_key.get_secret_value()}

    async def transcribe(
        self, audio: AsyncIterator[bytes], language: str, on_processing=None
    ) -> AsyncIterator[Transcript]:
        """One long-lived stream per speaker, 16kHz signed little-endian PCM mono.

        The provider finalizes VAD segments. The application never invents interim finals.
        Restart connections before the documented fifteen-minute session cap.
        """
        headers = self.headers | {
            "lang_code": BCP47[language], "x-sample-rate": "16000", "x-format": "transcribe",
            "x-min-silence-ms": "600", "x-max-speech-s": "20",
        }
        if self.settings.gnani_stt_model is not None:
            # The streaming endpoint selects v3.0 through the upgrade header,
            # not a query parameter or an additional websocket message.
            headers["model"] = self.settings.gnani_stt_model
        meter = sender = None

        async def metering():
            # First second was reserved before opening. Each subsequent connected
            # second (including idle microphone/handshake time) is reserved in advance.
            next_tick = time.monotonic() + 1
            while True:
                await asyncio.sleep(max(0, next_tick - time.monotonic()))
                self.usage.reserve({"stt_seconds": 1})
                next_tick += 1

        async def guarded(awaitable, *watchers):
            operation = asyncio.ensure_future(awaitable)
            try:
                done, _ = await asyncio.wait([operation, *watchers], return_when=asyncio.FIRST_COMPLETED)
                for watcher in watchers:
                    if watcher in done:
                        watcher.result()  # Budget/provider/source failure interrupts idle receive too.
                        raise ProviderError("Microphone source ended", False)
                return operation.result()
            finally:
                if not operation.done():
                    operation.cancel()
                await asyncio.gather(operation, return_exceptions=True)

        try:
            async with self.usage.operation({"stt_connections": 1, "stt_seconds": 1}, stt=True):
                meter = asyncio.create_task(metering())
                async with AsyncExitStack() as stack:
                    socket = await guarded(stack.enter_async_context(websockets.connect(
                        self.settings.gnani_stt_url, additional_headers=headers,
                        open_timeout=15, close_timeout=2, ping_interval=20, max_size=1024 * 1024,
                    )), meter)
                    ready = json.loads(await guarded(asyncio.wait_for(socket.recv(), 15), meter))
                    if ready.get("type") != "connected":
                        raise provider_error("Speech recognition could not start; check provider access and quota", body=ready)

                    async def send_audio():
                        buffer = bytearray()
                        next_send = time.monotonic()
                        async for data in audio:
                            buffer.extend(data)
                            while len(buffer) >= 1024:
                                delay = next_send - time.monotonic()
                                if delay > 0:
                                    await asyncio.sleep(delay)
                                await socket.send(bytes(buffer[:1024]))
                                del buffer[:1024]
                                next_send = max(next_send + 0.032, time.monotonic())

                    sender = asyncio.create_task(send_audio())
                    processing_at = None
                    seen: set[str] = set()
                    # Idle audio still transmits continuously; recycle before provider cap.
                    async with asyncio.timeout(14 * 60):
                        iterator = aiter(socket)
                        while True:
                            try:
                                raw = await guarded(anext(iterator), meter, sender)
                            except StopAsyncIteration:
                                break
                            message = json.loads(raw)
                            kind = message.get("type")
                            if kind == "processing":
                                processing_at = time.perf_counter()
                                if on_processing:
                                    on_processing()
                            elif kind == "error":
                                raise provider_error("Speech recognition service interrupted; check provider access and quota", body=message)
                            elif kind == "transcript":
                                text = message.get("text", "").strip()
                                segment = str(message.get("segment_id") or message.get("segment_index", ""))
                                if text and segment not in seen:
                                    seen.add(segment)
                                    latency = ((time.perf_counter() - processing_at) * 1000
                                               if processing_at is not None else None)
                                    yield Transcript(text[:2000], segment, round(latency, 2) if latency is not None else None)
                                    processing_at = None
        except asyncio.CancelledError:
            raise
        except ProviderError:
            raise
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            raise provider_error("Speech recognition connection interrupted; check provider access and quota", status=status) from None
        finally:
            for task in (sender, meter):
                if task:
                    task.cancel()
            await asyncio.gather(*(task for task in (sender, meter) if task), return_exceptions=True)

    async def synthesize(
        self, text: str, language: str, embedding: dict | None = None
    ) -> AsyncIterator[bytes]:
        """Streaming PCM. Never decode WAV headers as samples; request raw explicitly."""
        request = {
            "text": text,
            "model": self.settings.voice_clone_model if embedding else self.settings.timbre_model,
            "audio_config": {
                "sample_rate": self.settings.audio_sample_rate, "num_channels": 1,
                "sample_width": 2, "encoding": "linear_pcm", "container": "raw",
            },
        }
        if embedding:
            request["speaker_embedding"] = embedding
        else:
            overrides = {code: getattr(self.settings, f"timbre_voice_{code}") for code in BCP47}
            request.update(voice=select_stock_voice(
                language, model=self.settings.timbre_model,
                global_voice=self.settings.timbre_voice, overrides=overrides,
            ), language=BCP47[language], speed=1.0)
        try:
            async with self.usage.operation({"tts_requests": 1, "tts_characters": len(text)}), websockets.connect(
                self.settings.gnani_tts_url,
                additional_headers=self.headers | {"Content-Type": "application/json"},
                open_timeout=15, close_timeout=5, max_size=4 * 1024 * 1024,
            ) as socket:
                await socket.send(json.dumps(request, ensure_ascii=False))
                byte_count = 0
                async with asyncio.timeout(self.settings.provider_timeout_seconds):
                    async for raw in socket:
                        message = json.loads(raw)
                        if message.get("type") == "error":
                            raise provider_error("Voice synthesis failed; check provider access and quota", body=message)
                        data = message.get("data") or {}
                        encoded = data.get("audio")
                        if encoded:
                            chunk = base64.b64decode(encoded, validate=True)
                            byte_count += len(chunk)
                            if byte_count > self.settings.audio_sample_rate * 2 * 120:
                                raise ProviderError("Synthesis exceeded the audio duration limit", False)
                            yield chunk
                        if message.get("type") == "complete" or data.get("is_final"):
                            if not byte_count:
                                raise ProviderError("Voice synthesis returned no audio")
                            return
                raise ProviderError("Voice synthesis ended before completion")
        except asyncio.CancelledError:
            raise
        except ProviderError:
            raise
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            raise provider_error("Voice synthesis connection failed; check provider access and quota", status=status) from None

    async def enroll(self, clip: bytes) -> dict:
        try:
            async with self.usage.operation({"voice_enrollments": 1}):
                response = await self.client.post(
                    self.settings.gnani_embedding_url, headers=self.headers,
                    files={"audio_file": ("reference.wav", clip, "audio/wav")},
                )
            response.raise_for_status()
            body = response.json()
            embedding = body["data"]["voice_clone_embedding"]
            if not isinstance(embedding, dict):
                raise ValueError("Invalid embedding response")
            if not body.get("success") or not isinstance(embedding.get("embedding"), str):
                raise ValueError("Embedding missing")
            if not embedding["embedding"] or not embedding.get("shape") or not embedding.get("dtype"):
                raise ValueError("Embedding incomplete")
            return embedding
        except httpx.HTTPStatusError as exc:
            raise provider_error("Voice enrollment rejected; check provider access and quota", status=exc.response.status_code) from None
        except (httpx.HTTPError, KeyError, ValueError, TypeError):
            raise ProviderError("Voice enrollment failed; check the reference and try again") from None

    async def aclose(self):
        await self.client.aclose()
