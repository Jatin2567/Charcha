from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from fastapi import HTTPException

from ..errors import ProviderError
from ..services.routing import recipients_for
from ..store import RoomState, Store
from .tokens import agent_identity, room_token


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

    def __init__(self, store: Store, state: RoomState, speech, pipeline):
        self.store, self.state, self.speech, self.pipeline = store, state, speech, pipeline
        self.room = None
        self.closed = False
        self.disconnected = False
        self.readers: dict[str, asyncio.Task] = {}
        self.outputs: dict[tuple[str, str], OutputTrack] = {}
        self.output_lock = asyncio.Lock()
        self.tasks: set[asyncio.Task] = set()
        self.permission_signature = None

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
        token = room_token(settings, self.state.room.code, identity, "Artha interpreter", agent=True,
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

        if self.closed or participant.identity.startswith("artha-agent-"):
            return
        member = next((p for p in self.state.room.participants if p.id == participant.identity), None)
        if not member or member.is_demo or track.kind != rtc.TrackKind.KIND_AUDIO:
            return
        if publication.source != rtc.TrackSource.SOURCE_MICROPHONE:
            return
        old = self.readers.pop(member.id, None)
        if old:
            old.cancel()
        self.readers[member.id] = self._task(self._read_audio(track, member.id))

    def _track_unsubscribed(self, track, publication, participant):
        task = self.readers.pop(participant.identity, None)
        if task:
            task.cancel()

    def _participant_disconnected(self, participant):
        task = self.readers.pop(participant.identity, None)
        if task:
            task.cancel()
        # A brief network disconnect may be recovered by LiveKit; do not revoke the
        # membership merely because a browser is reconnecting.

    def _reconnecting(self):
        self.state.broadcast("pipeline.error", {"message": "Audio network interrupted; reconnecting", "retryable": True})

    def _reconnected(self):
        self.disconnected = False
        self._permissions()
        for p in self.state.room.participants:
            self.state.broadcast("pipeline.status", {"speaker_id": p.id, "stage": "listening"})

    def _disconnected(self, *args):
        self.disconnected = True
        if not self.closed:
            self.state.broadcast("pipeline.error", {
                "message": "Interpreter disconnected. Leave and rejoin to reconnect audio", "retryable": True,
            })

    async def _read_audio(self, track, speaker_id: str):
        from livekit import rtc

        stream = rtc.AudioStream(
            track=track, sample_rate=16000, num_channels=1,
            capacity=self.store.settings.audio_queue_frames,
        )
        pcm_queue: asyncio.Queue = asyncio.Queue(maxsize=self.store.settings.audio_queue_frames)
        same_language_queue: asyncio.Queue = asyncio.Queue(maxsize=20)
        recognition_ready = asyncio.Event()
        overflow_reported = False

        async def receive():
            nonlocal overflow_reported
            async for event in stream:
                speaker = self._speaker(speaker_id)
                if not speaker:
                    return
                if speaker.muted:
                    continue
                data = bytes(event.frame.data)
                if recognition_ready.is_set():
                    if pcm_queue.full():
                        pcm_queue.get_nowait()
                        if not overflow_reported:
                            overflow_reported = True
                            self.state.broadcast("pipeline.error", {
                                "message": "Audio arrived faster than recognition; repeat the last phrase",
                                "retryable": True,
                            })
                    pcm_queue.put_nowait(data)
                if recipients_for(self.state.room.participants, speaker_id, speaker.language):
                    if same_language_queue.full():
                        same_language_queue.get_nowait()
                    same_language_queue.put_nowait((data, speaker.language))

        async def forward():
            resampler = rtc.AudioResampler(16000, self.store.settings.audio_sample_rate, num_channels=1)
            while True:
                data, language = await same_language_queue.get()
                self._permissions()
                output = await self._output(speaker_id, language, self.store.settings.audio_sample_rate)
                if output.tts_active:
                    continue
                for frame in resampler.push(rtc.AudioFrame(data, 16000, 1, len(data) // 2)):
                    await output.source.capture_frame(frame)

        async def audio():
            recognition_ready.set()
            while True:
                yield await pcm_queue.get()

        async def recognize():
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

                async def consume():
                    nonlocal retry
                    async for segment in self.speech.transcribe(audio(), speaker.language, processing):
                        retry = 0
                        current = self._speaker(speaker_id)
                        if current and not current.muted:
                            try:
                                await self.pipeline.submit(self.state, current, segment.text, segment.stt_ms, True)
                            except HTTPException as exc:
                                self.state.broadcast("pipeline.error", {"message": str(exc.detail), "retryable": True})

                async def eligibility_watch():
                    while self._recognition_eligible(speaker_id):
                        await asyncio.sleep(0.25)

                pending = []
                try:
                    self.state.broadcast("pipeline.status", {"speaker_id": speaker_id, "stage": "listening"})
                    def processing():
                        self.state.broadcast("pipeline.status", {"speaker_id": speaker_id, "stage": "transcribing"})

                    consuming = asyncio.create_task(consume())
                    watching = asyncio.create_task(eligibility_watch())
                    pending = [consuming, watching]
                    done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                    if watching in done:
                        # Mute, membership expiry or the last listener leaving closes
                        # even a completely idle provider socket within 250 ms.
                        retry = 0
                        continue
                    consuming.result()
                    # A normally closed upstream stream still requires reconnect.
                    raise ProviderError("Speech recognition stream ended; reconnecting")
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    recognition_ready.clear()
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

        tasks = [asyncio.create_task(receive()), asyncio.create_task(recognize()), asyncio.create_task(forward())]
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
            await stream.aclose()

    def _speaker(self, speaker_id):
        if not self.store.is_active(self.state.room.code, speaker_id):
            return None
        return next((p for p in self.state.room.participants if p.id == speaker_id), None)

    def _recognition_eligible(self, speaker_id: str) -> bool:
        speaker = self._speaker(speaker_id)
        if not speaker or speaker.muted:
            return False
        return any(p.id != speaker_id and not p.is_agent and not p.is_demo
                   and p.language != speaker.language
                   and self.store.is_active(self.state.room.code, p.id)
                   for p in self.state.room.participants)

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
                if participant.id in recipients_for(self.state.room.participants, output.speaker_id, output.language)
            ]
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
            source = rtc.AudioSource(sample_rate, 1, queue_size_ms=250)
            track = rtc.LocalAudioTrack.create_audio_track(f"translated:{speaker_id}:{language}", source)
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

    async def speak(self, speaker_id, language, chunks, on_first_audio):
        from livekit import rtc

        active = [p for p in self.state.room.participants
                  if self.store.is_active(self.state.room.code, p.id)]
        if not self._speaker(speaker_id) or not recipients_for(active, speaker_id, language):
            return
        rate = self.store.settings.audio_sample_rate
        output = await self._output(speaker_id, language, rate)
        if not self._speaker(speaker_id):
            return
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

        async def capture(data):
            nonlocal first
            self._permissions()
            frame = rtc.AudioFrame(data, rate, 1, len(data) // 2)
            frames = resampler.push(frame) if resampler else [frame]
            for converted in frames:
                await output.source.capture_frame(converted)
                if first:
                    first = False
                    on_first_audio()

        try:
            async for chunk in chunks:
                if not self._speaker(speaker_id):
                    return
                buffer.extend(chunk)
                while len(buffer) >= frame_bytes:
                    await capture(bytes(buffer[:frame_bytes]))
                    del buffer[:frame_bytes]
            if buffer:
                if len(buffer) % 2:
                    raise ProviderError("Synthesis returned malformed PCM audio")
                await capture(bytes(buffer))
            if resampler:
                for final in resampler.flush():
                    await output.source.capture_frame(final)
            await output.source.wait_for_playout()
        except BaseException:
            output.source.clear_queue()
            raise
        finally:
            output.tts_active = False

    async def reconfigure(self, speaker_id: str | None = None):
        if speaker_id:
            task = self.readers.pop(speaker_id, None)
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            async with self.output_lock:
                for key, output in list(self.outputs.items()):
                    if output.speaker_id == speaker_id:
                        self.outputs.pop(key)
                        output.source.clear_queue()
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
    def __init__(self, store: Store, speech, pipeline):
        self.store, self.speech, self.pipeline = store, speech, pipeline
        self.rooms: dict[str, RoomTransport] = {}
        self.lock = asyncio.Lock()

    async def ensure_room(self, state: RoomState):
        async with self.lock:
            existing = self.rooms.get(state.room.code)
            if existing and not existing.closed and not existing.disconnected:
                return existing
            if existing:
                await existing.aclose()
            transport = RoomTransport(self.store, state, self.speech, self.pipeline)
            await transport.connect()
            self.rooms[state.room.code] = transport
            return transport

    async def speak(self, code, speaker_id, language, chunks, callback):
        transport = self.rooms.get(code)
        if not transport:
            raise ProviderError("Interpreter is not connected; rejoin the conversation")
        await transport.speak(speaker_id, language, chunks, callback)

    async def reconfigure(self, code: str, speaker_id: str | None = None):
        if transport := self.rooms.get(code):
            await transport.reconfigure(speaker_id)

    async def remove(self, code, speaker_id):
        if transport := self.rooms.get(code):
            await transport.remove(speaker_id)

    async def close_room(self, code):
        if transport := self.rooms.pop(code, None):
            await transport.aclose()

    async def aclose(self):
        for code in list(self.rooms):
            await self.close_room(code)
