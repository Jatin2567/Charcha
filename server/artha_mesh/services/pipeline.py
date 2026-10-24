from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from fastapi import HTTPException

from ..errors import ProviderError
from ..models import Participant, PerformanceSample, Turn
from ..providers.demo import sample_for
from ..store import RoomState, Store
from .performance import counts, milliseconds
from .routing import recipients_for, target_languages
from .usage import provider_eligibility


@dataclass
class WorkItem:
    state: RoomState
    speaker: Participant
    turn: Turn
    stt_ms: float | None
    from_audio: bool
    queued_at: float = field(default_factory=time.perf_counter)
    processing_at: float | None = None
    targets: tuple[str, ...] = ()
    recorded_targets: set[str] = field(default_factory=set)


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
        stt_ms: float | None = None, from_audio: bool = False,
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
        item.targets = tuple(sorted(target_languages(self._active_participants(state), speaker.id)))
        queue.put_nowait(item)
        state.broadcast("transcript.final", {"turn": turn.model_dump(mode="json")})
        return turn.id

    async def _worker(self, key):
        queue = self.queues[key]
        while True:
            item = await queue.get()
            item.processing_at = time.perf_counter()
            try:
                await self._process(item)
            except asyncio.CancelledError:
                self._record_unstarted(item, "cancelled", "queue")
                item.turn.status = "error"
                item.state.broadcast("transcript.final", {"turn": item.turn.model_dump(mode="json")})
                raise
            except Exception:
                self._record_unstarted(item, "error", "internal")
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
            self._record_unstarted(item, "cancelled", "delivery")
            turn.status = "error"
            state.broadcast("transcript.final", {"turn": turn.model_dump(mode="json")})
            return
        state.broadcast("pipeline.status", {
            "speaker_id": speaker.id, "stage": "translating", "utterance_id": turn.id,
        })
        targets = sorted(target_languages(self._active_participants(state), speaker.id))
        item.targets = tuple(targets)
        outcomes = await asyncio.gather(
            *(self._translate_target(item, language) for language in targets),
            return_exceptions=True,
        )
        valid = [result for result in outcomes if isinstance(result, dict)
                 and (result["measured"] or self.store.settings.mode == "demo")]
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
        if self.store.settings.mode != "demo":
            summary = counts(list(state.performance_samples))
            state.metrics.p50_ms = summary["p50_ms"] or 0
            state.metrics.p95_ms = summary["p95_ms"] or 0
        if valid:
            longest = max(valid, key=lambda result: result["total"])
            metrics = state.metrics
            metrics.stt_ms = milliseconds(item.stt_ms) or 0
            metrics.mt_ms = round(longest["mt"], 2)
            metrics.tts_ms = round(longest["tts"], 2)
            metrics.total_ms = round(longest["total"], 2)
            if self.store.settings.mode != "demo":
                state.latencies.append(metrics.total_ms)
            state.broadcast("metrics.updated", metrics.model_dump(mode="json"))
        else:
            # Forwarded/no-listener/error turns have no new synthesized measurement.
            # Preserve valid historical percentiles, but never present the previous
            # successful turn's stage timings as though they describe this turn.
            state.metrics.stt_ms = 0
            state.metrics.mt_ms = 0
            state.metrics.tts_ms = 0
            state.metrics.total_ms = 0
            state.broadcast("metrics.updated", state.metrics.model_dump(mode="json"))

    async def _translate_target(self, item: WorkItem, target: str) -> dict:
        with provider_eligibility(lambda: self._require_delivery_active(item.state, item.speaker.id, target)):
            return await self._translate_target_scoped(item, target)

    async def _translate_target_scoped(self, item: WorkItem, target: str) -> dict:
        state, turn, speaker = item.state, item.turn, item.speaker
        sample = self._new_sample(item, target)
        stage = "delivery"
        try:
            self._require_delivery_active(state, speaker.id, target)
            stage = "mt"
            started = time.perf_counter()
            try:
                async with asyncio.timeout(self.store.settings.provider_timeout_seconds):
                    text = (turn.text if target == speaker.language else
                            await self.translator.translate(turn.text, speaker.language, target))
            finally:
                if sample.measurement == "server_first_pcm" and target != speaker.language:
                    sample.mt_ms = milliseconds((time.perf_counter() - started) * 1000)
            turn.translations[target] = text
            # Membership can expire while MT awaits its upstream response.
            stage = "delivery"
            self._require_delivery_active(state, speaker.id, target)

            def announce(latency: float, measurement: str):
                state.broadcast("translation.ready", {
                    "utterance_id": turn.id, "speaker_id": speaker.id, "speaker_name": speaker.name,
                    "source_language": speaker.language, "target_language": target, "text": text,
                    "latency_ms": round(latency, 2), "voice_mode": speaker.voice_mode,
                    "measurement": measurement,
                })

            # Captions appear at MT completion. The worker still awaits audio playout
            # to preserve source-turn order; the timing boundary ends at first PCM.
            text_latency = (sample.stt_ms or 0) + (time.perf_counter() - item.queued_at) * 1000
            announce(text_latency if self.store.settings.mode == "live" else 0.0,
                     "text_ready" if self.store.settings.mode == "live" else "simulated")
            if sample.measurement == "server_first_pcm":
                stage = "voice_reference"
                profile_id = state.voice_profiles.get(speaker.id)
                profile = self.store.voices.get(profile_id or "")
                if speaker.voice_mode == "cloned" and (not profile or not profile.embedding):
                    raise ProviderError("Voice reference expired; choose a standard voice or enroll again", False)
                embedding = profile.embedding if speaker.voice_mode == "cloned" and profile else None
                stage = "tts"
                tts_started = time.perf_counter()

                def on_first_audio():
                    nonlocal stage
                    if sample.total_ms is not None:
                        return
                    first_audio_at = time.perf_counter()
                    sample.tts_first_pcm_ms = milliseconds((first_audio_at - tts_started) * 1000)
                    sample.total_ms = milliseconds(
                        (sample.stt_ms or 0) + (first_audio_at - item.queued_at) * 1000
                    )
                    stage = "playout"
                    announce(sample.total_ms or 0, "server_pipeline")
                    state.broadcast("pipeline.status", {
                        "speaker_id": speaker.id, "stage": "speaking", "utterance_id": turn.id,
                    })

                if not self.transport:
                    raise ProviderError("Audio room is not connected", False)
                async with asyncio.timeout(self.store.settings.provider_timeout_seconds + 120):
                    await self.transport.speak(
                        state.room.code, speaker.id, target,
                        self.tts.synthesize(text, target, embedding), on_first_audio,
                    )
                if sample.total_ms is None:
                    raise ProviderError("No interpreted audio was dispatched; check the listener connection")
            return {"mt": sample.mt_ms or 0, "tts": sample.tts_first_pcm_ms or 0,
                    "total": sample.total_ms or 0,
                    "measured": sample.measurement == "server_first_pcm"}
        except asyncio.CancelledError:
            sample.status, sample.error_stage = "cancelled", stage
            raise
        except Exception:
            sample.status, sample.error_stage = "error", stage
            raise
        finally:
            self._record_sample(item, target, sample)

    def _new_sample(self, item: WorkItem, target: str) -> PerformanceSample:
        if self.store.settings.mode == "demo":
            measurement = "simulated"
        elif item.from_audio and target == item.speaker.language:
            measurement = "source_forwarded"
        else:
            measurement = "server_first_pcm"
        measured = measurement == "server_first_pcm"
        return PerformanceSample(
            utterance_id=item.turn.id,
            source_language=item.speaker.language,
            target_language=target,
            input_kind="audio" if item.from_audio else "text",
            voice_mode=item.speaker.voice_mode,
            measurement=measurement,
            queue_ms=(milliseconds(((item.processing_at or time.perf_counter()) - item.queued_at) * 1000)
                      if measured else None),
            stt_ms=milliseconds(item.stt_ms) if measured and item.from_audio else None,
        )

    @staticmethod
    def _record_sample(item: WorkItem, target: str, sample: PerformanceSample):
        if target not in item.recorded_targets:
            item.state.performance_samples.append(sample)
            item.recorded_targets.add(target)

    def _record_unstarted(self, item: WorkItem, status: str, stage: str):
        for target in item.targets:
            if target not in item.recorded_targets:
                sample = self._new_sample(item, target)
                sample.status, sample.error_stage = status, stage
                self._record_sample(item, target, sample)

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
                self._record_unstarted(item, "cancelled", "queue")
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
