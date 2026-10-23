from __future__ import annotations

import asyncio
import time

from fastapi import HTTPException

from ..models import JoinRoom, Participant, UpdateParticipant
from ..providers.demo import SAMPLES
from ..store import RoomState, Store
from ..transport.tokens import agent_identity, room_token


class RoomService:
    def __init__(self, store: Store, pipeline, transport, voices):
        self.store, self.pipeline, self.transport, self.voices = store, pipeline, transport, voices
        self.locks: dict[str, asyncio.Lock] = {}

    async def prune_expired(self):
        current = time.time()
        expired_members = [(session.room_code, session.participant_id)
                           for session in self.store.sessions.values() if session.expires_at <= current]
        expired_rooms = self.store.prune()
        for code in expired_rooms:
            await self.pipeline.close_room(code)
            await self.transport.close_room(code)
            self.locks.pop(code, None)
        for code, participant_id in expired_members:
            state = self.store.rooms.get(code)
            if state:
                await self.pipeline.cancel_speaker(code, participant_id)
                state.room.participants = [p for p in state.room.participants if p.id != participant_id]
                state.voice_profiles.pop(participant_id, None)
                state.broadcast("participant.left", {"participant_id": participant_id})
                await self.transport.remove(code, participant_id)
                if not any(not p.is_demo and not p.is_agent for p in state.room.participants):
                    if state.demo_task:
                        state.demo_task.cancel()
                    await self.pipeline.close_room(code)
                    await self.transport.close_room(code)
                    state.room.participants = []
                    state.demo_started = False

    async def join(self, code: str, request: JoinRoom, token: str | None = None):
        state = self.store.room(code)
        if self.store.settings.mode == "live":
            missing = self.store.settings.missing_live_config()
            if missing:
                raise HTTPException(503, "Live setup incomplete. Configure: " + ", ".join(missing))
        if self.store.settings.mode == "live" and not request.consent:
            raise HTTPException(422, "Consent to process your conversation audio is required")
        if request.voice_mode == "cloned":
            # Enrollment belongs to an existing member. Do not transfer biometric
            # references across memberships through a public invitation endpoint.
            raise HTTPException(422, "Join with a standard voice, then enroll your own voice in this session")
        async with self.locks.setdefault(code, asyncio.Lock()):
            humans = [p for p in state.room.participants if not p.is_agent and not p.is_demo]
            if len(humans) >= self.store.settings.max_participants:
                raise HTTPException(409, "This conversation is full")
            participant = Participant(name=request.name, language=request.language, muted=True)
            if self.store.settings.mode == "live":
                # Connect first, so a failed agent cannot yield a success-looking room.
                await self.transport.ensure_room(state)
            state.room.participants.append(participant)
            session_token = self.store.issue_session(state, participant.id)
            livekit = None
            if self.store.settings.mode == "live":
                livekit = {
                    "url": self.store.settings.livekit_url,
                    "token": room_token(self.store.settings, code, participant.id, participant.name),
                    "agent_identity": agent_identity(state.room.id),
                }
                await self.transport.reconfigure(code)
            state.broadcast("participant.joined", {"participant": participant.model_dump(mode="json")})
            return {"room": state.room, "participant": participant,
                    "session_token": session_token, "livekit": livekit}

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

    async def update(self, code: str, request: UpdateParticipant, token: str):
        session = self.store.authenticate(token, code)
        state = self.store.room(code)
        participant = next(p for p in state.room.participants if p.id == session.participant_id)
        selected = request.voice_mode or participant.voice_mode
        profile_id = request.voice_profile_id or state.voice_profiles.get(participant.id)
        if selected == "cloned":
            self.voices.require_owned(profile_id, token)
        if request.language is not None or request.voice_mode is not None or request.voice_profile_id is not None:
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
        if (request.language is not None or request.voice_mode is not None
                or request.voice_profile_id is not None or request.muted is not None):
            if request.muted is True:
                await self.pipeline.cancel_speaker(code, participant.id)
            await self.transport.reconfigure(code, participant.id)
        else:
            await self.transport.reconfigure(code)
        state.broadcast("participant.updated", {"participant": participant.model_dump(mode="json")})
        return participant

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
            await self.transport.reconfigure(session.room_code, participant.id)
            state.broadcast("participant.updated", {"participant": participant.model_dump(mode="json")})
        self.store.voices.pop(profile_id)
