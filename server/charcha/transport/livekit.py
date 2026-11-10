from __future__ import annotations

import asyncio
import time
import math
import struct
import json
from dataclasses import dataclass

from fastapi import HTTPException

from ..errors import ProviderError
from ..services.routing import recipients_for
from ..services.screening_runtime import RoomScreening, ScreeningGate
from ..services.usage import provider_room
from ..services.turn_latency import SourceEndTracker, TOPIC
from ..store import RoomState, Store
from .tokens import agent_identity, room_token

LISTENER_READY_TIMEOUT_SECONDS = 5


@dataclass
class OutputTrack:
    source: object
    publication: object
    speaker_id: str
    language: str
    sample_rate: int
    tts_active: bool = False


class RoomTransport:
    """One server participant per room; never subscribes to its generated tracks."""

    def __init__(self, store: Store, state: RoomState, speech, pipeline, screening=None):
        self.store, self.state, self.speech, self.pipeline = store, state, speech, pipeline
        self.room = None
        self.closed = False
        self.disconnected = False
        self.reconnecting = False
        # Local task lifecycle, not a claim that the remote model is healthy.
        self.recognition_active: dict[str, asyncio.Task] = {}
        self.readers: dict[str, asyncio.Task] = {}
        self.outputs: dict[tuple[str, str], OutputTrack] = {}
        self.output_lock = asyncio.Lock()
        self.tasks: set[asyncio.Task] = set()
        self.permission_signature = None
        self.screening = (RoomScreening(screening, state.room)
                          if screening and state.room.screening_switchable else screening)
        self.screening_gates: dict[str, ScreeningGate] = {}
        self.probe_tracks: dict[str, tuple[str, object]] = {}

    def _task(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        # Retrieve callback failures without emitting upstream exception bodies.
        task.add_done_callback(lambda done: done.exception() if not done.cancelled() else None)
        return task

    async def connect(self):
        from livekit import rtc

        self.room = rtc.Room()
        self.room.on("track_subscribed", self._track_subscribed)
        self.room.on("track_unsubscribed", self._track_unsubscribed)
        self.room.on("participant_disconnected", self._participant_disconnected)
        self.room.on("reconnecting", self._reconnecting)
        self.room.on("reconnected", self._reconnected)
        self.room.on("disconnected", self._disconnected)
        settings = self.store.settings
        identity = agent_identity(self.state.room.id)
        token = room_token(settings, self.state.room.code, identity, "Charcha interpreter", agent=True,
                           ttl_seconds=self.state.expires_at - time.time())
        try:
            async with asyncio.timeout(20):
                await self.room.connect(
                    settings.livekit_internal_url or settings.livekit_url, token,
                    options=rtc.RoomOptions(auto_subscribe=True),
                )
            # Set deny-by-default before any source exists. Newly published tracks stay
            # inaccessible until their explicit recipient SIDs are added below.
            self.room.local_participant.set_track_subscription_permissions(
                allow_all_participants=False, participant_permissions=[]
            )
        except Exception:
            await self.aclose()
            raise ProviderError("Could not connect the audio interpreter; check LiveKit configuration") from None

    def _track_subscribed(self, track, publication, participant):
        from livekit import rtc

        if self.closed or participant.identity.startswith("charcha-agent-"):
            return
        # Camera video is delivered directly between browsers. The interpreter
        # never needs a video subscription or its bandwidth.
        if track.kind != rtc.TrackKind.KIND_AUDIO:
            publication.set_subscribed(False)
            return
        member = next((p for p in self.state.room.participants if p.id == participant.identity), None)
        if not member or member.is_demo:
            return
        if publication.source != rtc.TrackSource.SOURCE_MICROPHONE:
            return
        self._reset_screening(member.id)
        old = self.readers.pop(member.id, None)
        if old:
            old.cancel()
        self.readers[member.id] = self._task(self._read_audio(track, member.id))

    def _track_unsubscribed(self, track, publication, participant):
        from livekit import rtc

        # Camera disable/unsubscribe must not cancel this speaker's independent
        # microphone reader or recognition stream.
        if (track.kind != rtc.TrackKind.KIND_AUDIO
                or publication.source != rtc.TrackSource.SOURCE_MICROPHONE):
            return
        self._reset_screening(participant.identity)
        task = self.readers.pop(participant.identity, None)
        if task:
            task.cancel()

    def _participant_disconnected(self, participant):
        self._reset_screening(participant.identity)
        task = self.readers.pop(participant.identity, None)
        if task:
            task.cancel()
        # A brief network disconnect may be recovered by LiveKit; do not revoke the
        # membership merely because a browser is reconnecting.

    def _reconnecting(self):
        self.reconnecting = True
        self.state.broadcast("pipeline.error", {"message": "Audio network interrupted; reconnecting", "retryable": True})

    def _reconnected(self):
        self.disconnected = False
        self.reconnecting = False
        self._permissions()
        for p in self.state.room.participants:
            self.state.broadcast("pipeline.status", {"speaker_id": p.id, "stage": "listening"})

    def _disconnected(self, *args):
        self.disconnected = True
        self.reconnecting = False
        if not self.closed:
            self.state.broadcast("pipeline.error", {
                "message": "Interpreter disconnected. Leave and rejoin to reconnect audio", "retryable": True,
            })

    async def _read_audio(self, track, speaker_id: str):
        from livekit import rtc

        stream = rtc.AudioStream(
            track=track, sample_rate=16000, num_channels=1,
            capacity=self.store.settings.audio_queue_frames,
            frame_size_ms=20,
        )
        pcm_queue: asyncio.Queue = asyncio.Queue(maxsize=max(
            self.store.settings.audio_queue_frames,
            220 if self.screening and self.screening.mode == "enforce" else 0,
        ))
        # Preserve the beginning of original speech while the first subscriber
        # negotiates. Six seconds of 20-ms PCM is bounded (~192 KiB), longer than
        # the five-second readiness gate; a timed-out gate stops this stream.
        forwarding_queue: asyncio.Queue = asyncio.Queue(maxsize=300)
        transport_only = self.state.room.mode == "transport"
        recognition_ready = asyncio.Event()
        source_timing = SourceEndTracker()
        overflow_reported = False
        forwarding_overflow_reported = False

        async def dispatch(data):
            nonlocal overflow_reported, forwarding_overflow_reported
            speaker = self._speaker(speaker_id)
            if not speaker or speaker.muted:
                return
            if recognition_ready.is_set():
                if pcm_queue.full():
                    pcm_queue.get_nowait()
                    source_timing.reset("source_audio_overflow")
                    if not overflow_reported:
                        overflow_reported = True
                        self.state.broadcast("pipeline.error", {
                            "message": "Audio arrived faster than recognition; repeat the last phrase",
                            "retryable": True,
                        })
                pcm_queue.put_nowait(data)
            language = "all" if transport_only else speaker.language
            if self._output_recipients(speaker_id, language):
                if forwarding_queue.full():
                    forwarding_queue.get_nowait()
                    if not forwarding_overflow_reported:
                        forwarding_overflow_reported = True
                        self.state.broadcast("pipeline.error", {
                            "message": "Original audio could not keep up; repeat the last phrase",
                            "retryable": True,
                        })
                forwarding_queue.put_nowait((data, language))

        async def screening_result(result):
            payload = {**result, "speaker_id": speaker_id}
            self.state.screening_latest[speaker_id] = payload
            self.state.screening_samples.append(payload)
            self.state.broadcast("screening.updated", payload)
            if payload["action"] == "withheld":
                for queue in (pcm_queue, forwarding_queue):
                    while not queue.empty():
                        queue.get_nowait()
                for output in self.outputs.values():
                    if output.speaker_id == speaker_id:
                        output.source.clear_queue()
                await self.pipeline.cancel_speaker(self.state.room.code, speaker_id)
                # An in-flight synthesized capture may have completed during
                # cancellation. Flush again after its worker has stopped.
                for output in self.outputs.values():
                    if output.speaker_id == speaker_id:
                        output.source.clear_queue()
            elif (payload["action"] == "released" and self._recognition_eligible(speaker_id)
                  and not recognition_ready.is_set()):
                # Allow the recognizer to attach before releasing this first window.
                try:
                    await asyncio.wait_for(recognition_ready.wait(), 1)
                except TimeoutError:
                    self.state.broadcast("pipeline.error", {
                        "message": "Recognition was not ready for the screened audio; repeat the phrase",
                        "retryable": True,
                    })

        def screening_active():
            speaker = self._speaker(speaker_id)
            return bool(speaker and not speaker.muted and not self.closed
                        and self.screening_gates.get(speaker_id) is gate)

        gate = ScreeningGate(self.screening, dispatch, screening_result, screening_active) if self.screening else None
        if gate:
            self.screening_gates[speaker_id] = gate

        async def receive():
            async for event in stream:
                if not self._speaker(speaker_id):
                    return
                data = bytes(event.frame.data)
                speaker = self._speaker(speaker_id)
                if speaker and not speaker.muted:
                    source_timing.feed(data)
                if gate:
                    await gate.feed(data)
                elif screening_active():
                    await dispatch(data)

        async def forward():
            resampler = rtc.AudioResampler(16000, self.store.settings.audio_sample_rate, num_channels=1)
            source_started = False
            while True:
                data, language = await forwarding_queue.get()
                speaker = self._speaker(speaker_id)
                if not speaker or speaker.muted or not self._output_recipients(speaker_id, language):
                    continue
                self._permissions()
                output = await self._output(speaker_id, language, self.store.settings.audio_sample_rate)
                await self._wait_for_listener(output, speaker_id, language)
                speaker = self._speaker(speaker_id)
                if not speaker or speaker.muted or not self._output_recipients(speaker_id, language):
                    continue
                if output.tts_active:
                    continue
                if not self._screening_allows_output(speaker_id):
                    continue
                # The decoder can emit zero PCM while a newly subscribed source
                # has not captured anything yet. Negotiate the output using those
                # frames, but do not replay their backlog in real time ahead of
                # the first sound. Exact zero only: quiet speech is never gated,
                # and pauses after the first nonzero sample remain unchanged.
                if not source_started:
                    if not any(data):
                        continue
                    source_started = True
                for frame in resampler.push(rtc.AudioFrame(data, 16000, 1, len(data) // 2)):
                    await output.source.capture_frame(frame)
                    if not self._screening_allows_output(speaker_id):
                        output.source.clear_queue()
                        break

        async def audio():
            recognition_ready.set()
            while True:
                yield await pcm_queue.get()

        draining = False  # Muted, but finishing the phrase spoken before mute.
        drain_heard = asyncio.Event()

        async def recognize():
            nonlocal draining
            retry = 0
            while not self.closed:
                speaker = self._speaker(speaker_id)
                if not speaker:
                    return
                # An empty room or server-muted microphone must never open a paid
                # recognizer. Waiting audio is discarded, never replayed later.
                if not self._recognition_eligible(speaker_id):
                    recognition_ready.clear()
                    while not pcm_queue.empty():
                        pcm_queue.get_nowait()
                    await asyncio.sleep(0.25)
                    continue

                async def consume(language=speaker.language):
                    nonlocal retry
                    owner = asyncio.current_task()
                    self.recognition_active[speaker_id] = owner
                    try:
                        async for segment in self.speech.transcribe(audio(), language, processing):
                            retry = 0
                            current = self._speaker(speaker_id)
                            if current and (
                                (draining and self._recognition_eligible(speaker_id, ignore_mute=True))
                                or (not current.muted and self._recognition_eligible(speaker_id))
                            ):
                                if draining:
                                    drain_heard.set()
                                try:
                                    await self.pipeline.submit(self.state, current, segment.text, segment.stt_ms, True,
                                                               speech_timing=source_timing.take())
                                except HTTPException as exc:
                                    self.state.broadcast("pipeline.error", {"message": str(exc.detail), "retryable": True})
                    finally:
                        # An old, cancelled reader must not erase a replacement
                        # reader's state after a track reconnect.
                        if self.recognition_active.get(speaker_id) is owner:
                            self.recognition_active.pop(speaker_id, None)

                async def eligibility_watch():
                    nonlocal draining
                    grace = self.store.settings.stt_mute_grace_seconds
                    frame = b"\x00" * 640  # 20 ms of 16 kHz mono PCM16 silence
                    while True:
                        if self._recognition_eligible(speaker_id):
                            await asyncio.sleep(0.25)
                            continue
                        if grace <= 0 or not self._recognition_eligible(speaker_id, ignore_mute=True):
                            return
                        # Muted only: dispatch now drops microphone audio, so feed
                        # real-time silence until the provider's VAD finalises the
                        # last phrase, then close. Unmuting resumes normally.
                        draining = True
                        drain_heard.clear()
                        self.state.broadcast("pipeline.status", {"speaker_id": speaker_id, "stage": "finishing"})
                        started = time.monotonic()
                        min_wait = min(grace, 0.9)  # > provider min-silence (600 ms)
                        sent = 0
                        try:
                            while True:
                                elapsed = time.monotonic() - started
                                if self._recognition_eligible(speaker_id):
                                    break  # Unmuted during grace; keep the socket.
                                if (elapsed >= grace or (drain_heard.is_set() and elapsed >= min_wait)
                                        or not self._recognition_eligible(speaker_id, ignore_mute=True)):
                                    return
                                due = int(elapsed / 0.02) + 1
                                while sent < due:
                                    if pcm_queue.full():
                                        pcm_queue.get_nowait()
                                    pcm_queue.put_nowait(frame)
                                    sent += 1
                                await asyncio.sleep(0.05)
                        finally:
                            draining = False

                pending = []
                opened_at = time.monotonic()
                try:
                    self.state.broadcast("pipeline.status", {"speaker_id": speaker_id, "stage": "listening"})
                    def processing():
                        self.state.broadcast("pipeline.status", {"speaker_id": speaker_id, "stage": "transcribing"})

                    opened_at = time.monotonic()
                    consuming = asyncio.create_task(consume())
                    watching = asyncio.create_task(eligibility_watch())
                    pending = [consuming, watching]
                    done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                    if watching in done:
                        # Mute, membership expiry or the last listener leaving closes
                        # even a completely idle provider socket within 250 ms.
                        retry = 0
                        self.state.broadcast("pipeline.status", {"speaker_id": speaker_id, "stage": "idle"})
                        continue
                    consuming.result()
                    if time.monotonic() - opened_at >= self.store.settings.stt_healthy_seconds:
                        # Normal provider close (idle timeout, session cap) after a
                        # healthy run: reconnect silently without spending retries.
                        retry = 0
                        continue
                    # A quick normal close still counts, so a broken endpoint
                    # cannot reconnect in a hot loop.
                    raise ProviderError("Speech recognition stream ended; reconnecting")
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    recognition_ready.clear()
                    if time.monotonic() - opened_at >= self.store.settings.stt_healthy_seconds:
                        retry = 0  # One failure after a healthy run is not "repeated".
                    retry += 1
                    terminal = ((isinstance(exc, ProviderError) and not exc.retryable)
                                or retry > self.store.settings.usage_stt_max_retries)
                    self.state.broadcast("pipeline.error", {
                        "message": (exc.message if isinstance(exc, ProviderError) and not exc.retryable
                                    else "Speech recognition stopped after repeated failures; check setup before toggling the microphone to restart"
                                    if terminal else "Speech recognition interrupted; reconnecting. Repeat the last phrase."),
                        "retryable": not terminal,
                    })
                    # Audio during outages is discarded, never replayed in a burst.
                    while not pcm_queue.empty():
                        pcm_queue.get_nowait()
                    if terminal:
                        # Keep cost-free same-language forwarding alive. Only an
                        # explicit microphone restart may request another recognizer.
                        await asyncio.Event().wait()
                    await asyncio.sleep(min(2 ** min(retry, 4), 15))
                    while not pcm_queue.empty():
                        pcm_queue.get_nowait()
                finally:
                    recognition_ready.clear()
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)

        tasks = [asyncio.create_task(receive()), asyncio.create_task(forward())]
        if not transport_only:
            # The STT connection and its billing ticker inherit this room.
            with provider_room(self.state.room.code):
                tasks.append(asyncio.create_task(recognize()))
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except asyncio.CancelledError:
            raise
        except Exception:
            self.state.broadcast("pipeline.error", {
                "message": "Microphone stream interrupted; toggle your microphone to restart", "retryable": True,
            })
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if gate:
                if self.screening_gates.get(speaker_id) is gate:
                    self._reset_screening(speaker_id)
                    del self.screening_gates[speaker_id]
                await gate.close()
            await stream.aclose()

    def _reset_screening(self, speaker_id):
        gate = self.screening_gates.get(speaker_id)
        if gate:
            gate.reset()
        if self.state.screening_latest.pop(speaker_id, None) is not None:
            self.state.broadcast("screening.cleared", {"speaker_id": speaker_id})

    def reset_screening_windows(self):
        for gate in self.screening_gates.values():
            gate.reset(cancel_analysis=True)

    def _speaker(self, speaker_id):
        if not self.store.is_active(self.state.room.code, speaker_id):
            return None
        return next((p for p in self.state.room.participants if p.id == speaker_id), None)

    def _recognition_eligible(self, speaker_id: str, ignore_mute: bool = False) -> bool:
        if self.state.room.mode == "transport" or self.closed or self.disconnected or self.reconnecting:
            return False
        speaker = self._speaker(speaker_id)
        if not speaker or (speaker.muted and not ignore_mute):
            return False
        if self.state.room.voice_required:
            profile = self.store.voices.get(self.state.voice_profiles.get(speaker_id, ""))
            if speaker.voice_mode != "cloned" or not profile or not profile.embedding:
                return False
        if (self.screening and self.screening.mode == "enforce"
                and self.state.screening_latest.get(speaker_id, {}).get("action") != "released"):
            return False
        listeners = [p for p in self.state.room.participants if p.id != speaker_id and not p.is_agent and not p.is_demo
                     and p.language != speaker.language and self.store.is_active(self.state.room.code, p.id)]
        remote = self.room.remote_participants if self.room else None
        if remote is not None:
            listeners = [p for p in listeners if p.id in remote]
        if not listeners:
            return False
        registry = getattr(self.store, "reviewer_resources", None)
        if registry and self.state.room.engine_on_demand and speaker_id not in self.recognition_active:
            try:
                engine = registry.engine_for(self.state.room.code)
                if not engine or engine.status()["state"] != "ready":
                    return False
            except Exception:
                return False
        if self.store.settings.usage_require_flow_approval:
            # A source already running keeps its reserved connection. New sources
            # wait while approval is locked, including after an audience change.
            usage = getattr(self.speech, "usage", None)
            if usage is None or self.store.settings_for_room(self.state.room.code).missing_live_config():
                return False
            if speaker_id not in self.recognition_active:
                return usage.conference_capacity(len({p.language for p in listeners}),
                                                 room_code=self.state.room.code)["status"] == "approved"
        return True

    def _screening_allows_output(self, speaker_id: str) -> bool:
        return (not self.screening or self.screening.mode != "enforce"
                or self.state.screening_latest.get(speaker_id, {}).get("action") == "released")

    def _output_recipients(self, speaker_id: str, language: str) -> list[str]:
        active = [p for p in self.state.room.participants
                  if not p.is_demo and self.store.is_active(self.state.room.code, p.id)]
        if self.state.room.mode == "transport":
            if language != "all" or not self._speaker(speaker_id):
                return []
            return [p.id for p in active if p.id != speaker_id and not p.is_agent]
        return recipients_for(active, speaker_id, language)

    def _permissions(self):
        from livekit import rtc

        if not self.room or self.closed:
            return
        permissions = []
        for participant in self.state.room.participants:
            if participant.is_agent or participant.is_demo:
                continue
            if not self.store.is_active(self.state.room.code, participant.id):
                continue
            allowed = [
                output.publication.sid for output in self.outputs.values()
                if participant.id in self._output_recipients(output.speaker_id, output.language)
            ]
            allowed.extend(publication.sid for listener, publication in self.probe_tracks.values()
                           if listener == participant.id)
            permissions.append(rtc.ParticipantTrackPermission(
                participant_identity=participant.id, allow_all=False, allowed_track_sids=allowed,
            ))
        signature = tuple((p.participant_identity, tuple(p.allowed_track_sids)) for p in permissions)
        if signature == self.permission_signature:
            return
        self.room.local_participant.set_track_subscription_permissions(
            allow_all_participants=False, participant_permissions=permissions,
        )
        self.permission_signature = signature

    async def send_probe(self, challenge: dict):
        """Generate a dedicated tone for one consenting listener, never a provider call."""
        from livekit import rtc

        listener = challenge["listener_id"]
        probe_id = challenge["probe_id"]
        if not self.room or self.closed or not self._speaker(listener):
            raise ProviderError("Receiver disconnected before the tone started", False)
        source = rtc.AudioSource(24000, 1, queue_size_ms=100)
        publication = None
        try:
            self._permissions()
            track = rtc.LocalAudioTrack.create_audio_track(challenge["track_name"], source)
            publication = await self.room.local_participant.publish_track(
                track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
            )
            self.probe_tracks[probe_id] = (listener, publication)
            self._permissions()
            async with asyncio.timeout(5):
                await publication.wait_for_subscription()
            for frame_index in range(50):
                if self.closed or not self._speaker(listener):
                    raise ProviderError("Receiver disconnected during the tone", False)
                data = struct.pack("<480h", *(int(2600 * math.sin(2 * math.pi * 950 * (frame_index * 480 + n) / 24000))
                                             for n in range(480)))
                await source.capture_frame(rtc.AudioFrame(data, 24000, 1, 480))
            await source.wait_for_playout()
            await asyncio.sleep(.3)  # Leave time for the receiver's analyser poll.
        except asyncio.CancelledError:
            raise
        except Exception:
            self.state.broadcast("probe.error", {"probe_id": probe_id, "listener_id": listener,
                                                 "message": "Receiver tone was not delivered; retry after reconnecting"})
            raise ProviderError("Receiver tone was not delivered; reconnect and try again", False) from None
        finally:
            self.probe_tracks.pop(probe_id, None)
            source.clear_queue()
            if publication and self.room and not self.closed:
                try:
                    await self.room.local_participant.unpublish_track(publication.sid)
                except Exception:
                    pass
            await source.aclose()
            self._permissions()

    async def _output(self, speaker_id: str, language: str, sample_rate: int) -> OutputTrack:
        from livekit import rtc

        key = (speaker_id, language)
        sample_rate = self.store.settings.audio_sample_rate
        async with self.output_lock:
            if key in self.outputs:
                return self.outputs[key]
            if self.closed or not self.room:
                raise ProviderError("Audio room is disconnected")
            self._permissions()  # Explicit deny for the soon-to-be-published unknown SID.
            # Raw audio already arrives in paced 20-ms frames. A synthesis-sized
            # output queue adds unnecessary delay to that path.
            source = rtc.AudioSource(sample_rate, 1, queue_size_ms=60
                                     if self.state.room.mode == "transport" else 250)
            prefix = "raw" if self.state.room.mode == "transport" else "translated"
            track = rtc.LocalAudioTrack.create_audio_track(f"{prefix}:{speaker_id}:{language}", source)
            try:
                publication = await self.room.local_participant.publish_track(
                    track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
                )
            except BaseException:
                await source.aclose()
                raise
            output = OutputTrack(source, publication, speaker_id, language, sample_rate)
            self.outputs[key] = output
            self._permissions()
            return output

    async def _wait_for_listener(self, output: OutputTrack, speaker_id: str, language: str):
        """Gate PCM on a real subscriber; do not consume paid synthesis early."""
        if not self._speaker(speaker_id) or not self._output_recipients(speaker_id, language):
            raise ProviderError("The listener left before audio was ready", False)
        try:
            async with asyncio.timeout(LISTENER_READY_TIMEOUT_SECONDS):
                await output.publication.wait_for_subscription()
        except TimeoutError:
            raise ProviderError("Listener audio is not ready; reconnect and repeat the last phrase", False) from None
        if not self._speaker(speaker_id) or not self._output_recipients(speaker_id, language):
            raise ProviderError("The listener left before audio was ready", False)

    async def prepare_output(self, speaker_id, language):
        """Permit bounded synthesis preparation only after a real listener exists."""
        if not self._speaker(speaker_id) or not self._output_recipients(speaker_id, language):
            raise ProviderError("The listener left before interpretation was ready", False)
        output = await self._output(speaker_id, language, self.store.settings.audio_sample_rate)
        await self._wait_for_listener(output, speaker_id, language)
        if not self._screening_allows_output(speaker_id):
            raise ProviderError("Experimental screening is withholding this speaker's audio", False)

    async def speak(self, speaker_id, language, chunks, on_first_audio):
        from livekit import rtc

        if self.state.room.mode == "transport":
            raise ProviderError("Synthesized audio is disabled in the original-audio transport test", False)
        active = [p for p in self.state.room.participants
                  if self.store.is_active(self.state.room.code, p.id)]
        if not self._speaker(speaker_id) or not recipients_for(active, speaker_id, language):
            return
        rate = self.store.settings.audio_sample_rate
        output = await self._output(speaker_id, language, rate)
        await self._wait_for_listener(output, speaker_id, language)
        if not self._speaker(speaker_id):
            return
        if not self._screening_allows_output(speaker_id):
            raise ProviderError("Experimental screening is withholding this speaker's audio", False)
        # A same-language typed fallback can share the forwarded-source track.
        # Suspend raw frames (including decoder silence) for the duration, otherwise
        # AudioSource.wait_for_playout never drains and two producers interleave PCM.
        output.tts_active = True
        output.source.clear_queue()
        # Same-language forwarded tracks are 16kHz; text fallback into those tracks
        # needs resampling rather than treating 24kHz data as 16kHz.
        resampler = None
        if output.sample_rate != rate:
            resampler = rtc.AudioResampler(rate, output.sample_rate, num_channels=1)
        buffer = bytearray()
        frame_bytes = rate // 50 * 2
        first = True
        marker = None
        timing = getattr(self.store, "turn_latency", None)
        context = getattr(on_first_audio, "latency_context", None)
        # The ordered delivery gate is held before this method. The marker is
        # emitted only for the first real PCM, never while prefetched audio waits.
        async def mark_first():
            nonlocal marker
            if not timing or not context or not self.room:
                return
            try:
                marker = timing.issue(self.state, speaker_id, language, context)
                if marker:
                    listeners = list(timing.markers[marker["marker_id"]].listeners)
                    async with asyncio.timeout(.25):
                        await self.room.local_participant.publish_data(json.dumps(marker), reliable=True,
                            destination_identities=listeners, topic=TOPIC)
            except Exception:
                # Optional timing failures cannot stop conversation audio.
                marker = None

        async def capture(data):
            nonlocal first
            self._permissions()
            frame = rtc.AudioFrame(data, rate, 1, len(data) // 2)
            frames = resampler.push(frame) if resampler else [frame]
            for converted in frames:
                if not self._screening_allows_output(speaker_id):
                    raise ProviderError("Experimental screening withheld this audio", False)
                if first:
                    await mark_first()
                await output.source.capture_frame(converted)
                if not self._screening_allows_output(speaker_id):
                    output.source.clear_queue()
                    raise ProviderError("Experimental screening withheld this audio", False)
                if first:
                    first = False
                    if marker:
                        timing.first_pcm(marker["marker_id"])
                    on_first_audio()

        try:
            async for chunk in chunks:
                if not self._speaker(speaker_id):
                    return
                if not self._screening_allows_output(speaker_id):
                    raise ProviderError("Experimental screening withheld this audio", False)
                buffer.extend(chunk)
                while len(buffer) >= frame_bytes:
                    await capture(bytes(buffer[:frame_bytes]))
                    del buffer[:frame_bytes]
                # The first provider chunk may contain less than 20 ms of PCM.
                # Dispatch its whole samples now rather than waiting for a later
                # chunk (or completion). Retain a split sample's final byte and
                # keep normal 20 ms batching after the first actual dispatch.
                if first and len(buffer) >= 2:
                    whole_sample_bytes = len(buffer) - len(buffer) % 2
                    await capture(bytes(buffer[:whole_sample_bytes]))
                    del buffer[:whole_sample_bytes]
            if buffer:
                if len(buffer) % 2:
                    raise ProviderError("Synthesis returned malformed PCM audio")
                await capture(bytes(buffer))
            if resampler:
                for final in resampler.flush():
                    if not self._screening_allows_output(speaker_id):
                        raise ProviderError("Experimental screening withheld this audio", False)
                    await output.source.capture_frame(final)
                    if not self._screening_allows_output(speaker_id):
                        output.source.clear_queue()
                        raise ProviderError("Experimental screening withheld this audio", False)
            if not self._screening_allows_output(speaker_id):
                raise ProviderError("Experimental screening withheld this audio", False)
            await output.source.wait_for_playout()
        except BaseException:
            output.source.clear_queue()
            raise
        finally:
            output.tts_active = False

    def mute_grace_applies(self, speaker_id: str) -> bool:
        """Mute-only change that may let the running reader finish its phrase."""
        task = self.readers.get(speaker_id)
        return bool(self.store.settings.stt_mute_grace_seconds > 0 and self.state.room.mode == "live"
                    and task and not task.done()
                    and not (self.screening and self.screening.mode == "enforce"))

    async def mute_changed(self, speaker_id: str) -> bool:
        """Keep the reader (and translated outputs) through a mute toggle.

        Returns False when the full reconfigure path is required instead. The
        reader itself drains and closes the recognizer after the grace period;
        the forwarded-original output is still unpublished on mute.
        """
        if not self.mute_grace_applies(speaker_id):
            return False
        speaker = self._speaker(speaker_id)
        if speaker and speaker.muted:
            self._reset_screening(speaker_id)
            async with self.output_lock:
                for key, output in list(self.outputs.items()):
                    if output.speaker_id == speaker_id and output.language == speaker.language:
                        output.source.clear_queue()
                        self.outputs.pop(key)
                        try:
                            await self.room.local_participant.unpublish_track(output.publication.sid)
                        finally:
                            await output.source.aclose()
        self._permissions()
        return True

    async def reconfigure(self, speaker_id: str | None = None):
        if speaker_id:
            self._reset_screening(speaker_id)
            task = self.readers.pop(speaker_id, None)
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            async with self.output_lock:
                for key, output in list(self.outputs.items()):
                    if output.speaker_id == speaker_id:
                        output.source.clear_queue()
                        # Unpublish on mute as well: clearing the source queue
                        # alone cannot clear an already negotiated receiver's
                        # jitter buffer or codec concealment output.
                        self.outputs.pop(key)
                        try:
                            await self.room.local_participant.unpublish_track(output.publication.sid)
                        finally:
                            await output.source.aclose()
            # Restart existing subscribed original microphone with new language.
            remote = self.room.remote_participants.get(speaker_id)
            speaker = self._speaker(speaker_id)
            if remote and speaker and not speaker.muted:
                for pub in remote.track_publications.values():
                    if pub.track:
                        self._track_subscribed(pub.track, pub, remote)
        self._permissions()

    async def remove(self, speaker_id: str):
        # The service removes the participant from its roster before calling here.
        await self.reconfigure(speaker_id)
        if self.room:
            try:
                from livekit import api
                settings = self.store.settings
                url = (settings.livekit_internal_url or settings.livekit_url).replace("wss://", "https://").replace("ws://", "http://")
                async with api.LiveKitAPI(url, settings.livekit_api_key.get_secret_value(), settings.livekit_api_secret.get_secret_value()) as client:
                    await client.room.remove_participant(api.RoomParticipantIdentity(room=self.state.room.code, identity=speaker_id))
            except Exception:
                # Revocation at our API is immediate; the room server may be offline.
                pass

    async def aclose(self):
        self.closed = True
        for task in tuple(self.tasks):
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        for output in self.outputs.values():
            output.source.clear_queue()
            await output.source.aclose()
        self.outputs.clear()
        if self.room:
            try:
                await asyncio.wait_for(self.room.disconnect(), 5)
            except Exception:
                pass


class TransportManager:
    def __init__(self, store: Store, speech, pipeline, screening=None):
        self.store, self.speech, self.pipeline = store, speech, pipeline
        self.rooms: dict[str, RoomTransport] = {}
        self.lock = asyncio.Lock()
        self.screening = screening

    async def ensure_room(self, state: RoomState):
        async with self.lock:
            existing = self.rooms.get(state.room.code)
            if existing and not existing.closed and not existing.disconnected:
                return existing
            if existing:
                await existing.aclose()
            transport = RoomTransport(self.store, state, self.speech, self.pipeline, self.screening)
            await transport.connect()
            self.rooms[state.room.code] = transport
            return transport

    async def prepare_output(self, code, speaker_id, language):
        transport = self.rooms.get(code)
        if not transport:
            raise ProviderError("Interpreter is not connected; rejoin the conversation")
        await transport.prepare_output(speaker_id, language)

    async def speak(self, code, speaker_id, language, chunks, callback):
        transport = self.rooms.get(code)
        if not transport:
            raise ProviderError("Interpreter is not connected; rejoin the conversation")
        await transport.speak(speaker_id, language, chunks, callback)

    async def reconfigure(self, code: str, speaker_id: str | None = None):
        if transport := self.rooms.get(code):
            await transport.reconfigure(speaker_id)

    def mute_grace_applies(self, code: str, speaker_id: str) -> bool:
        transport = self.rooms.get(code)
        check = getattr(transport, "mute_grace_applies", None)
        return bool(callable(check) and check(speaker_id))

    async def mute_changed(self, code: str, speaker_id: str) -> bool:
        transport = self.rooms.get(code)
        return bool(transport and await transport.mute_changed(speaker_id))

    async def remove(self, code, speaker_id):
        if transport := self.rooms.get(code):
            await transport.remove(speaker_id)

    async def close_room(self, code):
        if transport := self.rooms.pop(code, None):
            await transport.aclose()

    async def aclose(self):
        for code in list(self.rooms):
            await self.close_room(code)
