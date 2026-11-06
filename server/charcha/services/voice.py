from __future__ import annotations

import array
import asyncio
import io
import math
import sys
import wave

from fastapi import HTTPException

from ..models import VoiceProfile
from ..store import Store, StoredVoice, token_digest
from .usage import provider_room

MAX_REFERENCE_BYTES = 10 * 1024 * 1024
WAV_MIME_TYPES = {"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"}


def validate_reference(data: bytes, content_type: str) -> float:
    """Validate decoded duration, sample format and a conservative silence floor.

    This only rejects empty/silent input. It does not certify speech quality or identity.
    """
    if content_type.split(";")[0].lower() not in WAV_MIME_TYPES:
        raise HTTPException(415, "Please provide a PCM WAV reference recording")
    if len(data) > MAX_REFERENCE_BYTES:
        raise HTTPException(413, "Reference recording must be no larger than 10 MiB")
    try:
        with wave.open(io.BytesIO(data), "rb") as clip:
            if clip.getsampwidth() != 2 or clip.getnchannels() not in (1, 2):
                raise HTTPException(422, "Use a 16-bit mono or stereo PCM WAV recording")
            if clip.getframerate() not in (8000, 16000, 22050, 24000, 44100, 48000):
                raise HTTPException(422, "Unsupported recording sample rate")
            duration = clip.getnframes() / clip.getframerate()
            if not 5 <= duration <= 30:
                raise HTTPException(422, "Speak clearly for 5–30 seconds for voice enrollment")
            expected_bytes = clip.getnframes() * clip.getnchannels() * 2
            samples_raw = clip.readframes(clip.getnframes())
            if len(samples_raw) != expected_bytes:
                raise HTTPException(422, "Reference recording is truncated")
            samples = array.array("h", samples_raw)
            if sys.byteorder != "little":
                samples.byteswap()
            rms = math.sqrt(sum(sample * sample for sample in samples) / max(1, len(samples)))
            if rms < 80:
                raise HTTPException(422, "Reference is silent or too quiet; record spoken audio")
            return duration
    except (wave.Error, EOFError, ValueError, ZeroDivisionError):
        raise HTTPException(422, "Recording is not a valid PCM WAV file") from None


class VoiceService:
    def __init__(self, store: Store, speech):
        self.store = store
        self.speech = speech
        self.enrolling: dict[str, asyncio.Task] = {}

    async def enroll(self, clip: bytes, mime: str, name: str, consent: bool, token: str) -> VoiceProfile:
        session = self.store.authenticate(token)
        if self.store.settings.mode == "transport":
            raise HTTPException(409, "Voice cloning is disabled during the original-audio transport test")
        if not consent:
            raise HTTPException(422, "Explicit consent to clone your own voice is required")
        if not name.strip() or len(name) > 60:
            raise HTTPException(422, "Voice name must contain 1–60 characters")
        state = self.store.room(session.room_code)
        if state.room.voice_required:
            existing = self.store.voices.get(state.voice_profiles.get(session.participant_id, ""))
            if existing and existing.owner_digest == token_digest(token):
                return existing.profile
            # Retransmitted setup requests share the same provider attempt.
            key = token_digest(token)
            if key not in self.enrolling:
                self.enrolling[key] = asyncio.create_task(self._enroll(clip, mime, name, token))
                def finished(task):
                    if self.enrolling.get(key) is task:
                        self.enrolling.pop(key, None)
                    if not task.cancelled():
                        task.exception()
                self.enrolling[key].add_done_callback(finished)
            task = self.enrolling[key]
            try:
                return await asyncio.shield(task)
            finally:
                if task.done() and self.enrolling.get(key) is task:
                    del self.enrolling[key]
        return await self._enroll(clip, mime, name, token)

    async def _enroll(self, clip, mime, name, token):
        session = self.store.authenticate(token)
        self.store.rate_limit("voice", token_digest(token), 3)
        owned = [v for v in self.store.voices.values() if v.owner_digest == token_digest(token)]
        if len(owned) >= 3:
            raise HTTPException(409, "Delete a reference before enrolling another voice")
        validate_reference(clip, mime)
        with provider_room(session.room_code):
            embedding = await self.speech.enroll(clip) if self.store.settings.mode == "live" else None
        # Session may have been revoked while upstream enrollment was running.
        self.store.authenticate(token)
        profile = VoiceProfile(name=name.strip(), mode=self.store.settings.mode)
        self.store.voices[profile.id] = StoredVoice(profile, token_digest(token), embedding)
        state = self.store.room(session.room_code)
        if state.room.voice_required:
            member = next(p for p in state.room.participants if p.id == session.participant_id)
            state.voice_profiles[member.id] = profile.id
            member.voice_mode = "cloned"
            state.broadcast("participant.updated", {"participant": member.model_dump(mode="json")})
        return profile

    async def aclose(self):
        tasks = list(self.enrolling.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.enrolling.clear()

    def require_owned(self, profile_id: str | None, token: str) -> StoredVoice:
        voice = self.store.voices.get(profile_id or "")
        if not voice or voice.owner_digest != token_digest(token):
            raise HTTPException(403, "Enroll your own voice in this session first")
        return voice
