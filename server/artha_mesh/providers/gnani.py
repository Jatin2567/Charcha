from __future__ import annotations

import asyncio
import base64
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx
import websockets

from ..config import Settings
from ..errors import ProviderError
from ..models import BCP47


@dataclass
class Transcript:
    text: str
    segment_id: str
    stt_ms: float | None


class GnaniSpeech:
    def __init__(self, settings: Settings):
        self.settings = settings
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
        try:
            async with websockets.connect(
                self.settings.gnani_stt_url, additional_headers=headers,
                open_timeout=15, close_timeout=5, ping_interval=20, max_size=1024 * 1024,
            ) as socket:
                ready = json.loads(await asyncio.wait_for(socket.recv(), 15))
                if ready.get("type") != "connected":
                    raise ProviderError("Speech recognition could not start")

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
                try:
                    # Idle audio still transmits continuously; recycle before provider cap.
                    async with asyncio.timeout(14 * 60):
                        async for raw in socket:
                            if sender.done():
                                sender.result()
                            message = json.loads(raw)
                            kind = message.get("type")
                            if kind == "processing":
                                processing_at = time.perf_counter()
                                if on_processing:
                                    on_processing()
                            elif kind == "error":
                                raise ProviderError("Speech recognition service interrupted")
                            elif kind == "transcript":
                                text = message.get("text", "").strip()
                                segment = str(message.get("segment_id") or message.get("segment_index", ""))
                                if text and segment not in seen:
                                    seen.add(segment)
                                    latency = ((time.perf_counter() - processing_at) * 1000
                                               if processing_at is not None else None)
                                    yield Transcript(text[:2000], segment, round(latency, 2) if latency is not None else None)
                                    processing_at = None
                finally:
                    sender.cancel()
                    await asyncio.gather(sender, return_exceptions=True)
        except asyncio.CancelledError:
            raise
        except ProviderError:
            raise
        except Exception:
            raise ProviderError("Speech recognition connection interrupted; reconnecting") from None

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
            request.update(voice=self.settings.timbre_voice, language=BCP47[language], speed=1.0)
        try:
            async with websockets.connect(
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
                            raise ProviderError("Voice synthesis failed; retry with a standard voice")
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
        except Exception:
            raise ProviderError("Voice synthesis connection failed; please retry") from None

    async def enroll(self, clip: bytes) -> dict:
        try:
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
        except (httpx.HTTPError, KeyError, ValueError, TypeError):
            raise ProviderError("Voice enrollment failed; check the reference and try again") from None

    async def aclose(self):
        await self.client.aclose()
