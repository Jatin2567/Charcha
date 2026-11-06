from __future__ import annotations

import asyncio
import time

from fastapi import HTTPException

from ..models import JoinRoom, Participant, UpdateParticipant
from ..providers.demo import SAMPLES
from ..store import RoomState, Store, account_deadline, account_history_key
from ..transport.tokens import agent_identity, room_token
from .readiness import conference_readiness


class RoomService:
    def __init__(self, store: Store, pipeline, transport, voices, usage=None, history=None):
        self.store, self.pipeline, self.transport, self.voices = store, pipeline, transport, voices
        self.usage = usage
        self.history = history
        self.locks: dict[str, asyncio.Lock] = {}

    def save_performance(self, state, *, interrupted=False):
        if self.history:
            occupied = any(not p.is_agent and not p.is_demo and self.store.is_active(state.room.code, p.id)
                           for p in state.room.participants)
            self.history.enqueue(state, "interrupted" if interrupted and occupied else "active" if occupied else "completed")

    async def prune_expired(self):
        current = time.time()
        expired_members = [(session.room_code, session.participant_id)
                           for session in self.store.sessions.values() if session.expires_at <= current]
        expired_room_members = {
            code: [p.id for p in state.room.participants if not p.is_demo and not p.is_agent]
            for code, state in self.store.rooms.items() if state.expires_at <= current
        }
        previous = dict(self.store.rooms)
        expired_rooms = self.store.prune()
        for code in expired_rooms:
            await self.pipeline.close_room(code)
            if self.store.settings.mode in {"live", "transport"}:
                for participant_id in expired_room_members.get(code, []):
                    await self.transport.remove(code, participant_id)
            await self.transport.close_room(code)
            self.save_performance(previous[code])
            self.locks.pop(code, None)
        for code, participant_id in expired_members:
            state = self.store.rooms.get(code)
            if state:
                await self.pipeline.cancel_speaker(code, participant_id)
                state.room.participants = [p for p in state.room.participants if p.id != participant_id]
                state.voice_profiles.pop(participant_id, None)
                for subject, entry in list(state.admissions.items()):
                    if entry.get("participant_id") == participant_id:
                        del state.admissions[subject]
                state.broadcast("participant.left", {"participant_id": participant_id})
                await self.transport.remove(code, participant_id)
                if not any(not p.is_demo and not p.is_agent for p in state.room.participants):
                    if state.demo_task:
                        state.demo_task.cancel()
                    await self.pipeline.close_room(code)
                    await self.transport.close_room(code)
                    state.room.participants = []
                    state.demo_started = False
                self.save_performance(state)

    async def join(self, code: str, request: JoinRoom, token: str | None = None):
        state = self.store.room(code)
        if self.store.settings.mode in {"live", "transport"}:
            # Joining the SFU is free; missing translation providers must not
            # prevent an original-audio conference or a muted setup session.
            missing = self.store.settings.missing_transport_config()
            if missing:
                raise HTTPException(503, "Audio setup incomplete. Configure: " + ", ".join(missing))
        if self.store.settings.mode in {"live", "transport"} and not request.consent:
            raise HTTPException(422, "Consent to process your conversation audio is required")
        if state.room.screening_switchable and not request.screening_consent:
            raise HTTPException(422, "Review the host-controlled VoiceShield notice on the join page before entering")
        if request.voice_mode == "cloned":
            # Enrollment belongs to an existing member. Do not transfer biometric
            # references across memberships through a public invitation endpoint.
            raise HTTPException(422, "Join with a standard voice, then enroll your own voice in this session")
        async with self.locks.setdefault(code, asyncio.Lock()):
            humans = [p for p in state.room.participants if not p.is_agent and not p.is_demo]
            if self.store.settings.max_participants and len(humans) >= self.store.settings.max_participants:
                raise HTTPException(409, "This conversation is full")
            participant = Participant(name=request.name, language=request.language, muted=True)
            if self.store.settings.mode in {"live", "transport"}:
                # Connect first, so a failed agent cannot yield a success-looking room.
                await self.transport.ensure_room(state)
            state.room.participants.append(participant)
            session_token = self.store.issue_session(state, participant.id)
            livekit = None
            if self.store.settings.mode in {"live", "transport"}:
                try:
                    livekit = {
                        "url": self.store.settings.livekit_url,
                        "token": room_token(self.store.settings, code, participant.id, participant.name,
                                            ttl_seconds=min(60, min(state.expires_at, account_deadline.get()) - time.time())),
                        "agent_identity": agent_identity(state.room.id),
                    }
                    await self.transport.reconfigure(code)
                except BaseException:
                    self.store.forget_session(session_token)
                    state.room.participants.remove(participant)
                    raise
            if principal := account_history_key.get():
                state.performance_owners[participant.id] = principal
            self.save_performance(state)
            state.broadcast("participant.joined", {"participant": participant.model_dump(mode="json")})
            return {"room": state.room, "participant": participant,
                    "session_token": session_token, "livekit": livekit}

    def connection(self, code: str, token: str):
        """Refresh a connection credential without extending or replacing a membership."""
        session = self.store.authenticate(token, code)
        state = self.store.room(code)
        participant = next(p for p in state.room.participants if p.id == session.participant_id)
        livekit = None
        if self.store.settings.mode in {"live", "transport"}:
            remaining = int(min(session.expires_at, state.expires_at, account_deadline.get()) - time.time())
            if remaining < 1:
                raise HTTPException(401, "Membership expired; rejoin the conversation")
            livekit = {
                "url": self.store.settings.livekit_url,
                "token": room_token(self.store.settings, code, participant.id, participant.name,
                                    ttl_seconds=min(60, remaining)),
                "agent_identity": agent_identity(state.room.id),
            }
        return {"room": state.room, "participant": participant,
                "session_token": token, "livekit": livekit}

    async def leave(self, code: str, participant_id: str, token: str):
        session = self.store.authenticate(token, code)
        if session.participant_id != participant_id:
            raise HTTPException(403, "You can leave only your own membership")
        state = self.store.room(code)
        await self.pipeline.cancel_speaker(code, participant_id)
        state.room.participants = [p for p in state.room.participants if p.id != participant_id]
        state.voice_profiles.pop(participant_id, None)
        self.store.forget_session(token)
        state.broadcast("participant.left", {"participant_id": participant_id})
        await self.transport.remove(code, participant_id)
        humans = [p for p in state.room.participants if not p.is_demo and not p.is_agent]
        if not humans:
            if state.demo_task:
                state.demo_task.cancel()
            await self.pipeline.close_room(code)
            await self.transport.close_room(code)
            # Demo presenters belong to that demonstration, not a permanent room.
            state.room.participants = []
            state.demo_started = False
        self.save_performance(state)

    async def update(self, code: str, request: UpdateParticipant, token: str):
        session = self.store.authenticate(token, code)
        state = self.store.room(code)
        participant = next(p for p in state.room.participants if p.id == session.participant_id)
        language_changed = request.language is not None and request.language != participant.language
        voice_changed = request.voice_mode is not None and request.voice_mode != participant.voice_mode
        profile_changed = request.voice_profile_id is not None and request.voice_profile_id != state.voice_profiles.get(participant.id)
        mute_changed = request.muted is not None and request.muted != participant.muted
        starts_source = ((request.muted is False and participant.muted)
                         or (request.muted is not True and not participant.muted
                             and (language_changed or voice_changed or profile_changed)))
        if (starts_source and self.usage is not None
                and state.room.mode == "live" and (self.store.settings.usage_require_flow_approval or state.room.voice_required)):
            candidate = participant.model_copy(update={"muted": True,
                "language": request.language or participant.language,
                "voice_mode": request.voice_mode or participant.voice_mode})
            readiness = conference_readiness(self.store, state, candidate, self.transport, self.usage)
            if not readiness.microphone.can_unmute:
                raise HTTPException(409, {"code": readiness.microphone.reason_code, "message": readiness.microphone.detail})
        selected = request.voice_mode or participant.voice_mode
        if state.host_funded and not state.room.voice_required and selected == "cloned":
            raise HTTPException(409, "This meeting uses standard voices.")
        if state.room.voice_required and request.voice_mode == "standard":
            raise HTTPException(409, "This meeting uses your enrolled voice. Complete voice setup to speak.")
        if state.room.mode == "transport" and selected == "cloned":
            raise HTTPException(409, "Voice cloning is disabled during the original-audio transport test")
        profile_id = request.voice_profile_id or state.voice_profiles.get(participant.id)
        if selected == "cloned":
            self.voices.require_owned(profile_id, token)
        if language_changed or voice_changed or profile_changed:
            await self.pipeline.cancel_speaker(code, participant.id)
        if request.language is not None:
            participant.language = request.language
        if request.voice_mode is not None:
            participant.voice_mode = request.voice_mode
        if selected == "cloned" and profile_id:
            state.voice_profiles[participant.id] = profile_id
        elif selected == "standard":
            state.voice_profiles.pop(participant.id, None)
        if request.muted is not None:
            participant.muted = request.muted
        mute_only = mute_changed and not (language_changed or voice_changed or profile_changed)
        grace = getattr(self.transport, "mute_grace_applies", None)
        if mute_only and callable(grace) and grace(code, participant.id) is True:
            # Mute stops new audio; the phrase already spoken still finishes and
            # is delivered. The reader closes the recognizer after a short grace.
            await self.transport.mute_changed(code, participant.id)
        elif language_changed or voice_changed or profile_changed or mute_changed:
            if request.muted is True:
                await self.pipeline.cancel_speaker(code, participant.id)
            await self.transport.reconfigure(code, participant.id)
        state.broadcast("participant.updated", {"participant": participant.model_dump(mode="json")})
        return participant

    def conference_readiness(self, code: str, token: str):
        session = self.store.authenticate(token, code)
        state = self.store.room(code)
        member = next(row for row in state.room.participants if row.id == session.participant_id)
        return conference_readiness(self.store, state, member, self.transport, self.usage)

    async def start_demo(self, code: str):
        if self.store.settings.mode != "demo":
            raise HTTPException(409, "Scripted demonstration is available only in demo mode")
        state = self.store.room(code)
        if state.demo_task and not state.demo_task.done():
            raise HTTPException(409, "The demonstration is already running")
        if not state.demo_started:
            presenters = [
                Participant(id="demo-asha", name="Asha · demo", language="hi", is_demo=True),
                Participant(id="demo-kavya", name="Kavya · demo", language="ta", is_demo=True),
                Participant(id="demo-ritam", name="Ritam · demo", language="bn", is_demo=True),
            ]
            state.room.participants.extend(presenters)
            state.demo_started = True
            for participant in presenters:
                state.broadcast("participant.joined", {"participant": participant.model_dump(mode="json")})
        state.demo_task = asyncio.create_task(self._run_demo(state))

    async def _run_demo(self, state: RoomState):
        try:
            script = [("demo-asha", 1), ("demo-kavya", 2), ("demo-ritam", 5),
                      ("demo-asha", 3), ("demo-kavya", 4), ("demo-ritam", 6)]
            for speaker_id, sample_index in script:
                speaker = next((p for p in state.room.participants if p.id == speaker_id), None)
                if not speaker:
                    return
                state.broadcast("pipeline.status", {"speaker_id": speaker.id, "stage": "listening"})
                await asyncio.sleep(0.8)
                await self.pipeline.submit(state, speaker, SAMPLES[sample_index][speaker.language])
                queue = self.pipeline.queues.get((state.room.code, speaker_id))
                if queue:
                    await queue.join()
                await asyncio.sleep(1.8)
            state.broadcast("demo.complete", {})
        except asyncio.CancelledError:
            raise
        except Exception:
            state.broadcast("pipeline.error", {"message": "Demonstration stopped; start it again", "retryable": True})

    async def delete_voice(self, profile_id: str, token: str):
        session = self.store.authenticate(token)
        self.voices.require_owned(profile_id, token)
        state = self.store.room(session.room_code)
        participant = next(p for p in state.room.participants if p.id == session.participant_id)
        if state.voice_profiles.get(participant.id) == profile_id:
            await self.pipeline.cancel_speaker(session.room_code, participant.id)
            state.voice_profiles.pop(participant.id, None)
            participant.voice_mode = "standard"
            if state.room.voice_required:
                participant.muted = True
            await self.transport.reconfigure(session.room_code, participant.id)
            state.broadcast("participant.updated", {"participant": participant.model_dump(mode="json")})
        self.store.voices.pop(profile_id)
