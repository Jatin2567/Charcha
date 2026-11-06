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
from .usage import current_provider_flow, provider_eligibility, provider_flow, provider_room


class QueueExpired(ProviderError):
    def __init__(self):
        super().__init__("A queued phrase was skipped because interpretation fell behind. Its caption is kept; pause and repeat it.", True)


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
    flow_id: str | None = None
    predecessor: asyncio.Event | None = None
    delivered: asyncio.Event = field(default_factory=asyncio.Event)
    queue_depth: int = 0
    speech_timing: dict | None = None


class Pipeline:
    """Bounded preparation lookahead with strictly ordered audio per speaker."""

    def __init__(self, store: Store, translator, speech):
        self.store = store
        self.translator = translator
        self.tts = speech
        self.transport = None
        self.queues: dict[tuple[str, str], asyncio.Queue] = {}
        self.workers: dict[tuple[str, str], asyncio.Task] = {}
        self.active: dict[tuple[str, str], set[asyncio.Task]] = {}
        self.waiting: dict[tuple[str, str], dict[str, WorkItem]] = {}
        self.cancelling: dict[tuple[str, str], asyncio.Event] = {}

    async def submit(
        self, state: RoomState, speaker: Participant, text: str,
        stt_ms: float | None = None, from_audio: bool = False, *, replaces: Turn | None = None,
        speech_timing: dict | None = None,
    ) -> str:
        if state.room.mode == "transport":
            raise HTTPException(409, "Interpretation is disabled in transport mode; use the microphone for original audio")
        text = text.strip()
        if not text or len(text) > 2000:
            raise HTTPException(422, "Utterances must contain 1–2000 characters")
        if self.store.settings.mode == "demo" and not replaces and sample_for(text, speaker.language) is None:
            raise HTTPException(422, "Local demo supports only the sample phrases shown in the meeting")
        if replaces and text == replaces.text:
            raise HTTPException(422, "Change the wording before sharing your correction")
        if len(state.turns) >= self.store.settings.max_turns_per_room:
            raise HTTPException(429, "Conversation transcript limit reached; start a new conversation")
        key = (state.room.code, speaker.id)
        if key in self.cancelling:
            raise HTTPException(409, "Interpretation is stopping for this microphone; wait and repeat the phrase")
        if key not in self.workers or self.workers[key].done():
            self.queues[key] = asyncio.Queue(maxsize=self.store.settings.max_pending_turns)
            self.workers[key] = asyncio.create_task(self._worker(key))
        queue = self.queues[key]
        if queue.full():
            raise HTTPException(429, "Interpretation queue is full; pause before speaking again")
        if replaces and (replaces.speaker_id != speaker.id or replaces.superseded_by or replaces.status == "processing"):
            raise HTTPException(409, "Open the latest completed version to make a correction")
        turn = Turn(speaker_id=speaker.id, speaker_name=speaker.name,
                    source_language=speaker.language, text=text, replaces_id=replaces.id if replaces else None)
        turn.listeners = {p.id: p.name for p in self._active_participants(state)
                          if p.id != speaker.id and not p.is_demo and not p.is_agent}
        turn.listeners_recorded = True
        state.turns.append(turn)
        item = WorkItem(state, speaker.model_copy(deep=True), turn, stt_ms, from_audio,
                        queue_depth=queue.qsize(), speech_timing=speech_timing)
        usage = getattr(self.tts, "usage", None)
        item.flow_id = (usage.queued_turn_flow(state.room.code)
                        if self.store.settings.mode == "live" and self.store.settings.usage_require_room_scope and usage
                        else current_provider_flow())
        item.targets = tuple(sorted(target_languages(self._active_participants(state), speaker.id)))
        queue.put_nowait(item)
        self.waiting.setdefault(key, {})[turn.id] = item
        self._queue_status(state, speaker.id)
        if replaces:
            replaces.superseded_by = turn.id
            state.broadcast("transcript.final", {"turn": replaces.model_dump(mode="json")})
        state.broadcast("transcript.final", {"turn": turn.model_dump(mode="json")})
        return turn.id

    async def _worker(self, key):
        queue = self.queues[key]
        running = self.active.setdefault(key, set())
        items = {}
        previous = None
        limit = self.store.settings.translation_lookahead if self.store.settings.mode == "live" else 1
        try:
            while True:
                for task in tuple(running):
                    if task.done():
                        running.remove(task)
                        items.pop(task, None)
                if len(running) >= limit:
                    await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
                    continue
                item = await queue.get()
                self.waiting.get(key, {}).pop(item.turn.id, None)
                item.predecessor, previous = previous, item.delivered
                task = asyncio.create_task(self._run_item(item, queue))
                running.add(task)
                items[task] = item
                self._queue_status(item.state, item.speaker.id)
        finally:
            for task in running:
                task.cancel()
            await asyncio.gather(*running, return_exceptions=True)
            for task, item in items.items():
                if item.processing_at is None:
                    self._record_unstarted(item, "cancelled", "queue")
                    item.turn.status = "error"
                    item.turn.recovery_reason = "interrupted"
                    item.delivered.set()
                    queue.task_done()
                    item.state.broadcast("transcript.final", {"turn": item.turn.model_dump(mode="json")})
            self.active.pop(key, None)

    async def _run_item(self, item, queue):
        item.processing_at = time.perf_counter()
        try:
            if self._too_old(item):
                raise QueueExpired()
            # Approval context belongs to each turn, including the lookahead task.
            with provider_flow(item.flow_id):
                await self._process(item)
        except asyncio.CancelledError:
            self._record_unstarted(item, "cancelled", "queue")
            item.turn.status = "error"
            item.turn.recovery_reason = "interrupted"
            item.state.broadcast("transcript.final", {"turn": item.turn.model_dump(mode="json")})
            raise
        except Exception as exc:
            expired = isinstance(exc, QueueExpired)
            self._record_unstarted(item, "cancelled" if expired else "error", "queue_expired" if expired else "internal")
            item.turn.status = "error"
            item.turn.recovery_reason = "queue_expired" if expired else "delivery_failed"
            item.state.broadcast("pipeline.error", {
                "message": exc.message if expired else "Interpretation failed; repeat the phrase",
                "utterance_id": item.turn.id, "retryable": True,
            })
            item.state.broadcast("transcript.final", {"turn": item.turn.model_dump(mode="json")})
            item.state.broadcast("pipeline.status", {
                "speaker_id": item.speaker.id, "stage": "error", "utterance_id": item.turn.id,
            })
        finally:
            try:
                # A cancelled middle turn must not let its successor overtake
                # the earlier audio that is still playing. Keep its slot until
                # the predecessor finishes; this also avoids paid speculative
                # work repeatedly expiring behind the same long output.
                if item.predecessor and not item.predecessor.is_set():
                    await item.predecessor.wait()
            finally:
                item.delivered.set()
                queue.task_done()
                self._queue_status(item.state, item.speaker.id, exclude=asyncio.current_task())

    def _too_old(self, item):
        return (self.store.settings.mode == "live" and
                time.perf_counter() - item.queued_at > self.store.settings.translation_queue_max_age_seconds)

    def _queue_status(self, state, speaker_id, *, exclude=None):
        key = (state.room.code, speaker_id)
        pending = list(self.waiting.get(key, {}).values())
        running = sum(not task.done() and task is not exclude for task in self.active.get(key, ()))
        state.broadcast("queue.updated", {"speaker_id": speaker_id, "pending": len(pending),
            "in_flight": running,
            "oldest_wait_ms": milliseconds((time.perf_counter()-pending[0].queued_at)*1000) if pending else 0,
            "max_wait_ms": self.store.settings.translation_queue_max_age_seconds*1000})

    async def _process(self, item: WorkItem):
        state, turn, speaker = item.state, item.turn, item.speaker
        if (not any(p.id == speaker.id for p in state.room.participants)
                or not self._source_active(state, speaker.id)):
            self._record_unstarted(item, "cancelled", "delivery")
            turn.status = "error"
            turn.recovery_reason = "interrupted"
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
        if failures:
            turn.recovery_reason = "queue_expired" if any(isinstance(f, QueueExpired) for f in failures) else "delivery_failed"
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
        with provider_room(item.state.room.code), provider_eligibility(
            lambda: self._require_delivery_active(item.state, item.speaker.id, target)
        ):
            return await self._translate_target_scoped(item, target)

    async def _translate_target_scoped(self, item: WorkItem, target: str) -> dict:
        state, turn, speaker = item.state, item.turn, item.speaker
        sample = self._new_sample(item, target)
        stage = "delivery"
        try:
            self._require_delivery_active(state, speaker.id, target)
            engine = getattr(self.translator, "engine", None)
            if target != speaker.language and engine:
                stage = "model_startup"
                await engine.ensure_ready()
                self._require_delivery_active(state, speaker.id, target)
            if self._can_stream(sample, speaker.language, target):
                return await self._stream_target(item, target, sample)
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
                    self._source_latency(sample)
                    stage = "playout"
                    announce(sample.total_ms or 0, "server_pipeline")
                    state.broadcast("pipeline.status", {
                        "speaker_id": speaker.id, "stage": "speaking", "utterance_id": turn.id,
                    })

                if not self.transport:
                    raise ProviderError("Audio room is not connected", False)
                self._latency_context(on_first_audio, item, target, sample)
                async with asyncio.timeout(self.store.settings.provider_timeout_seconds + 120):
                    await self._speak_prepared(item, target, sample,
                        self.tts.synthesize(text, target, embedding), on_first_audio)
                if sample.total_ms is None:
                    raise ProviderError("No interpreted audio was dispatched; check the listener connection")
            return {"mt": sample.mt_ms or 0, "tts": sample.tts_first_pcm_ms or 0,
                    "total": sample.total_ms or 0,
                    "measured": sample.measurement == "server_first_pcm"}
        except asyncio.CancelledError:
            sample.status, sample.error_stage = "cancelled", sample.error_stage or stage
            raise
        except QueueExpired:
            sample.status, sample.error_stage = "cancelled", "queue_expired"
            raise
        except Exception:
            sample.status, sample.error_stage = "error", sample.error_stage or stage
            raise
        finally:
            self._record_sample(item, target, sample)

    def _can_stream(self, sample: PerformanceSample, source: str, target: str) -> bool:
        settings = self.store.settings
        return (settings.mode == "live" and settings.evon_stream_clauses
                and sample.measurement == "server_first_pcm" and source != target
                and callable(getattr(self.translator, "translate_stream", None))
                and self.transport is not None)

    async def _stream_target(self, item: WorkItem, target: str, sample: PerformanceSample) -> dict:
        """Translate and speak clause by clause on one ordered audio stream.

        One MT request covers the whole utterance. A reader task pulls clauses
        from the model while a synthesis task turns them into PCM one clause at
        a time, so clause N+1 is synthesized while clause N plays. Playback
        order equals model order. Any MT failure (including a token-limit
        cutoff) stops audio at the last complete clause and raises, which the
        worker reports to participants.
        """
        state, turn, speaker = item.state, item.turn, item.speaker
        stage = "voice_reference"
        sample.mt_streamed = True
        try:
            profile_id = state.voice_profiles.get(speaker.id)
            profile = self.store.voices.get(profile_id or "")
            if speaker.voice_mode == "cloned" and (not profile or not profile.embedding):
                raise ProviderError("Voice reference expired; choose a standard voice or enroll again", False)
            embedding = profile.embedding if speaker.voice_mode == "cloned" and profile else None
            stage = "mt"
            started = time.perf_counter()
            tts_started: float | None = None
            clauses: list[str] = []
            text_q: asyncio.Queue = asyncio.Queue(maxsize=8)
            pcm_q: asyncio.Queue = asyncio.Queue(maxsize=4)
            done = object()
            timeout = self.store.settings.provider_timeout_seconds

            def announce(text: str, latency: float, measurement: str):
                state.broadcast("translation.ready", {
                    "utterance_id": turn.id, "speaker_id": speaker.id, "speaker_name": speaker.name,
                    "source_language": speaker.language, "target_language": target, "text": text,
                    "latency_ms": round(latency, 2), "voice_mode": speaker.voice_mode,
                    "measurement": measurement,
                })

            async def read_clauses():
                nonlocal tts_started
                try:
                    async with asyncio.timeout(timeout):
                        async for clause in self.translator.translate_stream(
                                turn.text, speaker.language, target):
                            if not clauses:
                                sample.mt_ms = milliseconds((time.perf_counter() - started) * 1000)
                                tts_started = time.perf_counter()
                            clauses.append(clause)
                            # Partial caption so listeners can read along.
                            turn.translations[target] = " ".join(clauses)
                            await text_q.put(clause)
                    sample.mt_complete_ms = milliseconds((time.perf_counter() - started) * 1000)
                    await text_q.put(done)
                except BaseException as exc:  # forwarded to the audio consumer
                    if isinstance(exc, asyncio.CancelledError):
                        raise
                    await text_q.put(exc)

            async def synthesize_clauses():
                try:
                    while True:
                        clause = await text_q.get()
                        if clause is done or isinstance(clause, BaseException):
                            await pcm_q.put(clause)
                            return
                        self._require_delivery_active(state, speaker.id, target)
                        async for chunk in self.tts.synthesize(clause, target, embedding):
                            size = self.store.settings.audio_sample_rate // 5 * 2
                            for start in range(0, len(chunk), size):
                                await pcm_q.put(chunk[start:start + size])
                except BaseException as exc:
                    if isinstance(exc, asyncio.CancelledError):
                        raise
                    await pcm_q.put(exc)

            async def pcm():
                reader = asyncio.create_task(read_clauses())
                writer = asyncio.create_task(synthesize_clauses())
                try:
                    while True:
                        chunk = await pcm_q.get()
                        if chunk is done:
                            return
                        if isinstance(chunk, BaseException):
                            raise chunk
                        yield chunk
                finally:
                    for task in (reader, writer):
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(reader, writer, return_exceptions=True)

            def on_first_audio():
                nonlocal stage
                if sample.total_ms is not None:
                    return
                first_audio_at = time.perf_counter()
                sample.tts_first_pcm_ms = milliseconds((first_audio_at - (tts_started or started)) * 1000)
                sample.total_ms = milliseconds((sample.stt_ms or 0) + (first_audio_at - item.queued_at) * 1000)
                self._source_latency(sample)
                stage = "playout"
                announce(" ".join(clauses), sample.total_ms or 0, "server_pipeline")
                state.broadcast("pipeline.status", {
                    "speaker_id": speaker.id, "stage": "speaking", "utterance_id": turn.id,
                })

            self._latency_context(on_first_audio, item, target, sample)
            async with asyncio.timeout(timeout + 120):
                await self._speak_prepared(item, target, sample, pcm(), on_first_audio)
            text = " ".join(clauses)
            turn.translations[target] = text
            # Final caption carries the complete text once the model finished.
            announce(text, (sample.stt_ms or 0) + (time.perf_counter() - item.queued_at) * 1000, "text_ready")
            if sample.total_ms is None:
                raise ProviderError("No interpreted audio was dispatched; check the listener connection")
            return {"mt": sample.mt_ms or 0, "tts": sample.tts_first_pcm_ms or 0,
                    "total": sample.total_ms or 0, "measured": True}
        except asyncio.CancelledError:
            sample.status, sample.error_stage = "cancelled", stage
            raise
        except QueueExpired:
            sample.status, sample.error_stage = "cancelled", "queue_expired"
            raise
        except Exception:
            sample.status, sample.error_stage = "error", stage
            raise

    async def _speak_prepared(self, item, target, sample, chunks, on_first_audio):
        """Prepare at most a short PCM prefix while the preceding turn finishes.

        There are at most two turns per speaker. The four 200 ms queue slots
        bound audio retained by this adapter; providers are backpressured and
        cancelled when a listener leaves or a waiting turn expires. A started
        output is never cut off merely to improve a latency number.
        """
        pending: asyncio.Queue = asyncio.Queue(maxsize=4)
        chunk_bytes = self.store.settings.audio_sample_rate // 5 * 2
        iterator = chunks.__aiter__()
        ready = getattr(self.transport, "prepare_output", None)
        if ready:
            await ready(item.state.room.code, item.speaker.id, target)

        async def prepare():
            try:
                async for chunk in iterator:
                    self._require_delivery_active(item.state, item.speaker.id, target)
                    for start in range(0, len(chunk), chunk_bytes):
                        data = chunk[start:start + chunk_bytes]
                        if sample.preparation_ms is None:
                            sample.preparation_ms = milliseconds((time.perf_counter() -
                                (item.processing_at if item.processing_at is not None else item.queued_at))*1000)
                        await pending.put(data)
            except asyncio.CancelledError:
                raise
            except BaseException as exc:
                await pending.put(exc)
            else:
                await pending.put(None)

        producer = asyncio.create_task(prepare())
        try:
            first = await pending.get()
            if isinstance(first, BaseException):
                raise first
            if first is None:
                raise ProviderError("Synthesis returned no audio")
            wait_started = time.perf_counter()
            try:
                if item.predecessor and not item.predecessor.is_set():
                    remaining = self.store.settings.translation_queue_max_age_seconds - (wait_started-item.queued_at)
                    if remaining <= 0:
                        raise QueueExpired()
                    try:
                        await asyncio.wait_for(item.predecessor.wait(), remaining)
                    except TimeoutError:
                        raise QueueExpired() from None
            finally:
                sample.output_wait_ms = milliseconds((time.perf_counter()-wait_started)*1000)
            self._require_delivery_active(item.state, item.speaker.id, target)

            async def prepared():
                yield first
                while True:
                    value = await pending.get()
                    if value is None:
                        return
                    if isinstance(value, BaseException):
                        raise value
                    yield value

            await self.transport.speak(item.state.room.code, item.speaker.id, target, prepared(), on_first_audio)
        finally:
            producer.cancel()
            await asyncio.gather(producer, return_exceptions=True)
            close = getattr(iterator, "aclose", None)
            if close:
                await close()

    @staticmethod
    def _source_latency(sample):
        if sample.source_end_server_ms is not None:
            value = time.monotonic()*1000 - sample.source_end_server_ms
            sample.source_end_to_first_pcm_ms = milliseconds(value)

    @staticmethod
    def _latency_context(callback, item, target, sample):
        callback.latency_context = {"utterance_id": item.turn.id, "source_language": item.speaker.language,
            "target_language": target, "source_end_server_ms": sample.source_end_server_ms,
            "source_end_status": sample.source_end_status}

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
            queue_depth=item.queue_depth if measured else None,
            **({key: item.speech_timing.get(key) for key in
                ("source_end_server_ms", "source_end_to_transcript_ms", "source_end_status")}
               if measured and item.from_audio and item.speech_timing else {}),
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
        participants = [p for p in state.room.participants if self.store.is_active(state.room.code, p.id)]
        audio = getattr(self.transport, "rooms", {}).get(state.room.code) if self.transport else None
        if self.store.settings.mode == "live" and audio and audio.room:
            # An HTTP membership alone is not a connected listener. Do not spend
            # MT/TTS attempts on a peer that has not joined (or has lost) media.
            if audio.closed or audio.disconnected or getattr(audio, "reconnecting", False):
                return []
            remote = audio.room.remote_participants
            return [p for p in participants if p.id in remote and not p.is_agent]
        return participants

    def _require_delivery_active(self, state: RoomState, speaker_id: str, target: str):
        if not self._source_active(state, speaker_id):
            raise ProviderError("Membership expired; rejoin the conversation", False)
        if state.room.voice_required:
            profile = self.store.voices.get(state.voice_profiles.get(speaker_id, ""))
            if not profile or not profile.embedding:
                raise ProviderError("Complete your meeting voice setup before speaking", False)
        if not recipients_for(self._active_participants(state), speaker_id, target):
            raise ProviderError("The listener left before interpretation completed", False)

    async def cancel_speaker(self, code: str, speaker_id: str):
        key = (code, speaker_id)
        if existing := self.cancelling.get(key):
            await existing.wait()
            return
        completed = asyncio.Event()
        self.cancelling[key] = completed
        worker = self.workers.pop(key, None)
        queue = self.queues.pop(key, None)
        interrupted = False
        try:
            if worker:
                worker.cancel()
                # Keep the guard until all native/provider cleanup completes,
                # even if a disconnect cancels the caller during shutdown.
                while not worker.done():
                    try:
                        await asyncio.shield(worker)
                    except asyncio.CancelledError:
                        if not worker.done():
                            interrupted = True
                    except Exception:
                        break  # Retrieve the terminal error below.
                await asyncio.gather(worker, return_exceptions=True)
            if queue:
                while not queue.empty():
                    item = queue.get_nowait()
                    self._record_unstarted(item, "cancelled", "queue")
                    item.turn.status = "error"
                    item.turn.recovery_reason = "interrupted"
                    item.state.broadcast("transcript.final", {"turn": item.turn.model_dump(mode="json")})
                    queue.task_done()
        finally:
            self.waiting.pop(key, None)
            self.cancelling.pop(key, None)
            completed.set()
            state = self.store.rooms.get(code)
            if state:
                self._queue_status(state, speaker_id)
        if interrupted:
            raise asyncio.CancelledError

    async def close_room(self, code: str):
        for room_code, speaker_id in list(self.workers):
            if room_code == code:
                await self.cancel_speaker(room_code, speaker_id)

    async def aclose(self):
        for code, speaker_id in list(self.workers):
            await self.cancel_speaker(code, speaker_id)
