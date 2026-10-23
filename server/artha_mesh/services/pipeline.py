from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass, field

from fastapi import HTTPException

from ..errors import ProviderError
from ..models import Participant, Turn
from ..providers.demo import sample_for
from ..store import RoomState, Store
from .routing import recipients_for, target_languages


@dataclass
class WorkItem:
    state: RoomState
    speaker: Participant
    turn: Turn
    stt_ms: float
    from_audio: bool
    queued_at: float = field(default_factory=time.perf_counter)


class Pipeline:
    """A bounded FIFO per original speaker; unique listener languages fan out together."""

    def __init__(self, store: Store, translator, speech):
        self.store = store
        self.translator = translator
        self.tts = speech
        self.transport = None
        self.queues: dict[tuple[str, str], asyncio.Queue] = {}
        self.workers: dict[tuple[str, str], asyncio.Task] = {}

    async def submit(
        self, state: RoomState, speaker: Participant, text: str,
        stt_ms: float = 0.0, from_audio: bool = False,
    ) -> str:
        text = text.strip()
        if not text or len(text) > 2000:
            raise HTTPException(422, "Utterances must contain 1–2000 characters")
        if self.store.settings.mode == "demo" and sample_for(text, speaker.language) is None:
            raise HTTPException(422, "Local demo supports only the sample phrases shown in the meeting")
        if len(state.turns) >= self.store.settings.max_turns_per_room:
            raise HTTPException(429, "Conversation transcript limit reached; start a new conversation")
        key = (state.room.code, speaker.id)
        if key not in self.workers or self.workers[key].done():
            self.queues[key] = asyncio.Queue(maxsize=self.store.settings.max_pending_turns)
            self.workers[key] = asyncio.create_task(self._worker(key))
        queue = self.queues[key]
        if queue.full():
            raise HTTPException(429, "Interpretation queue is full; pause before speaking again")
        turn = Turn(speaker_id=speaker.id, speaker_name=speaker.name,
                    source_language=speaker.language, text=text)
        state.turns.append(turn)
        item = WorkItem(state, speaker.model_copy(deep=True), turn, stt_ms, from_audio)
        queue.put_nowait(item)
        state.broadcast("transcript.final", {"turn": turn.model_dump(mode="json")})
        return turn.id

    async def _worker(self, key):
        queue = self.queues[key]
        while True:
            item = await queue.get()
            try:
                await self._process(item)
            except asyncio.CancelledError:
                item.turn.status = "error"
                item.state.broadcast("transcript.final", {"turn": item.turn.model_dump(mode="json")})
                raise
            except Exception:
                # A failed turn must not kill the FIFO and strand subsequent turns.
                item.turn.status = "error"
                item.state.broadcast("pipeline.error", {
                    "message": "Interpretation failed; repeat the phrase",
                    "utterance_id": item.turn.id, "retryable": True,
                })
                item.state.broadcast("transcript.final", {"turn": item.turn.model_dump(mode="json")})
                item.state.broadcast("pipeline.status", {
                    "speaker_id": item.speaker.id, "stage": "error", "utterance_id": item.turn.id,
                })
            finally:
                queue.task_done()

    async def _process(self, item: WorkItem):
        state, turn, speaker = item.state, item.turn, item.speaker
        if (not any(p.id == speaker.id for p in state.room.participants)
                or not self._source_active(state, speaker.id)):
            turn.status = "error"
            state.broadcast("transcript.final", {"turn": turn.model_dump(mode="json")})
            return
        state.broadcast("pipeline.status", {
            "speaker_id": speaker.id, "stage": "translating", "utterance_id": turn.id,
        })
        targets = sorted(target_languages(self._active_participants(state), speaker.id))
        outcomes = await asyncio.gather(
            *(self._translate_target(item, language) for language in targets),
            return_exceptions=True,
        )
        valid = [result for result in outcomes if isinstance(result, dict)]
        failures = [result for result in outcomes if isinstance(result, BaseException)]
        for failure in failures:
            error = failure if isinstance(failure, ProviderError) else ProviderError("Interpretation interrupted")
            state.broadcast("pipeline.error", {
                "message": error.message, "utterance_id": turn.id, "retryable": error.retryable,
            })
        turn.status = "error" if failures else "complete"
        state.broadcast("transcript.final", {"turn": turn.model_dump(mode="json")})
        state.broadcast("pipeline.status", {
            "speaker_id": speaker.id, "stage": "error" if failures else "idle", "utterance_id": turn.id,
        })
        # With zero listeners, there is no translation latency measurement.
        state.metrics.turns = len(state.turns)
        if valid:
            longest = max(valid, key=lambda result: result["total"])
            metrics = state.metrics
            metrics.stt_ms = round(item.stt_ms, 2)
            metrics.mt_ms = round(longest["mt"], 2)
            metrics.tts_ms = round(longest["tts"], 2)
            metrics.total_ms = round(longest["total"], 2)
            if self.store.settings.mode != "demo":
                state.latencies.append(metrics.total_ms)
                ordered = sorted(state.latencies)
                metrics.p50_ms = ordered[math.ceil(len(ordered) * 0.5) - 1]
                metrics.p95_ms = ordered[math.ceil(len(ordered) * 0.95) - 1]
            state.broadcast("metrics.updated", metrics.model_dump(mode="json"))
        else:
            state.broadcast("metrics.updated", state.metrics.model_dump(mode="json"))

    async def _translate_target(self, item: WorkItem, target: str) -> dict:
        state, turn, speaker = item.state, item.turn, item.speaker
        self._require_delivery_active(state, speaker.id, target)
        started = time.perf_counter()
        async with asyncio.timeout(self.store.settings.provider_timeout_seconds):
            text = (turn.text if target == speaker.language else
                    await self.translator.translate(turn.text, speaker.language, target))
        mt_ms = (time.perf_counter() - started) * 1000
        measured_until = time.perf_counter()
        turn.translations[target] = text
        # A membership can expire while MT is awaiting an upstream response.
        # Recheck before starting any additional synthesis/provider work.
        self._require_delivery_active(state, speaker.id, target)

        def announce(latency: float, measurement: str):
            state.broadcast("translation.ready", {
                "utterance_id": turn.id, "speaker_id": speaker.id, "speaker_name": speaker.name,
                "source_language": speaker.language, "target_language": target, "text": text,
                "latency_ms": round(latency, 2), "voice_mode": speaker.voice_mode,
                "measurement": measurement,
            })

        # Captions appear as soon as MT finishes. Audio playout remains awaited
        # separately so this source's next utterance cannot overtake the current one.
        text_latency = item.stt_ms + (measured_until - item.queued_at) * 1000
        announce(text_latency if self.store.settings.mode == "live" else 0.0,
                 "text_ready" if self.store.settings.mode == "live" else "simulated")
        tts_ms = 0.0
        if self.store.settings.mode == "live" and not (item.from_audio and target == speaker.language):
            profile_id = state.voice_profiles.get(speaker.id)
            profile = self.store.voices.get(profile_id or "")
            if speaker.voice_mode == "cloned" and (not profile or not profile.embedding):
                raise ProviderError("Voice reference expired; choose a standard voice or enroll again", False)
            embedding = profile.embedding if speaker.voice_mode == "cloned" and profile else None
            tts_started = time.perf_counter()
            first_audio_at = None

            def on_first_audio():
                nonlocal first_audio_at
                first_audio_at = time.perf_counter()
                announce(item.stt_ms + (first_audio_at - item.queued_at) * 1000, "server_pipeline")
                state.broadcast("pipeline.status", {
                    "speaker_id": speaker.id, "stage": "speaking", "utterance_id": turn.id,
                })

            if not self.transport:
                raise ProviderError("Audio room is not connected", False)
            # The worker waits for playout to preserve source-turn order. Metrics below
            # end at first PCM sent to LiveKit, not at completion or receiver playback.
            async with asyncio.timeout(self.store.settings.provider_timeout_seconds + 120):
                await self.transport.speak(
                    state.room.code, speaker.id, target,
                    self.tts.synthesize(text, target, embedding), on_first_audio,
                )
            if first_audio_at is not None:
                tts_ms = (first_audio_at - tts_started) * 1000
                measured_until = first_audio_at
            else:
                raise ProviderError("No interpreted audio was dispatched; check the listener connection")
        elif self.store.settings.mode == "demo":
            # Zero measurements deliberately avoid fabricating provider performance.
            mt_ms = 0.0
        total = (item.stt_ms + (measured_until - item.queued_at) * 1000
                 if self.store.settings.mode == "live" else 0.0)
        return {"mt": mt_ms, "tts": tts_ms, "total": total}

    def _source_active(self, state: RoomState, speaker_id: str) -> bool:
        return (self.store.settings.mode == "demo"
                or self.store.is_active(state.room.code, speaker_id))

    def _active_participants(self, state: RoomState):
        if self.store.settings.mode == "demo":
            return state.room.participants
        return [p for p in state.room.participants if self.store.is_active(state.room.code, p.id)]

    def _require_delivery_active(self, state: RoomState, speaker_id: str, target: str):
        if not self._source_active(state, speaker_id):
            raise ProviderError("Membership expired; rejoin the conversation", False)
        if not recipients_for(self._active_participants(state), speaker_id, target):
            raise ProviderError("The listener left before interpretation completed", False)

    async def cancel_speaker(self, code: str, speaker_id: str):
        key = (code, speaker_id)
        worker = self.workers.pop(key, None)
        if worker:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
        queue = self.queues.pop(key, None)
        if queue:
            while not queue.empty():
                item = queue.get_nowait()
                item.turn.status = "error"
                item.state.broadcast("transcript.final", {"turn": item.turn.model_dump(mode="json")})
                queue.task_done()

    async def close_room(self, code: str):
        for room_code, speaker_id in list(self.workers):
            if room_code == code:
                await self.cancel_speaker(room_code, speaker_id)

    async def aclose(self):
        for code, speaker_id in list(self.workers):
            await self.cancel_speaker(code, speaker_id)
