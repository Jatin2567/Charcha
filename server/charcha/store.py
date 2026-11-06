"""Bounded, ephemeral session state. Run one worker; no voice clips touch disk."""
from __future__ import annotations

import asyncio
import hashlib
import secrets
import time
from contextvars import ContextVar
from collections import deque
from dataclasses import dataclass, field

from fastapi import HTTPException

from .config import Settings
from .models import Event, Metrics, PerformanceSample, Room, Turn, VoiceProfile

MAX_PERFORMANCE_SAMPLES = 1000
account_deadline: ContextVar[float] = ContextVar("account_deadline", default=float("inf"))
account_session: ContextVar[str | None] = ContextVar("account_session", default=None)
account_history_key: ContextVar[str | None] = ContextVar("account_history_key", default=None)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass
class Session:
    room_code: str
    participant_id: str
    expires_at: float
    account_session: str | None = None


@dataclass
class StoredVoice:
    profile: VoiceProfile
    owner_digest: str
    embedding: dict | None


@dataclass(eq=False)
class Consumer:
    queue: asyncio.Queue
    overflow: asyncio.Event = field(default_factory=asyncio.Event)
    owner_digest: str = ""


@dataclass
class RoomState:
    room: Room
    expires_at: float
    owner: str = ""
    host_funded: bool = False
    performance_owners: dict[str, str] = field(default_factory=dict)
    admissions: dict = field(default_factory=dict)
    turns: list[Turn] = field(default_factory=list)
    metrics: Metrics = field(default_factory=Metrics)
    latencies: deque[float] = field(default_factory=lambda: deque(maxlen=MAX_PERFORMANCE_SAMPLES))
    performance_samples: deque[PerformanceSample] = field(
        default_factory=lambda: deque(maxlen=MAX_PERFORMANCE_SAMPLES)
    )
    consumers: set[Consumer] = field(default_factory=set)
    voice_profiles: dict[str, str] = field(default_factory=dict)
    demo_task: asyncio.Task | None = None
    demo_started: bool = False
    screening_latest: dict[str, dict] = field(default_factory=dict)
    screening_samples: deque[dict] = field(default_factory=lambda: deque(maxlen=MAX_PERFORMANCE_SAMPLES))

    def broadcast(self, event_type: str, payload: dict) -> None:
        event = Event(type=event_type, payload=payload).model_dump(mode="json")
        for consumer in tuple(self.consumers):
            try:
                consumer.queue.put_nowait(event)
            except asyncio.QueueFull:
                # Disconnect slow clients; reconnect obtains an authoritative snapshot.
                consumer.overflow.set()
                self.consumers.discard(consumer)


class Store:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.rooms: dict[str, RoomState] = {}
        self.sessions: dict[str, Session] = {}
        self.memberships: dict[tuple[str, str], str] = {}
        self.voices: dict[str, StoredVoice] = {}
        self.rate_buckets: dict[tuple[str, str], list[float]] = {}

    def room(self, code: str) -> RoomState:
        state = self.rooms.get(code.lower())
        if not state or state.expires_at <= time.time():
            raise HTTPException(404, "Conversation not found or expired")
        return state

    def create_room(self, title: str, audio_mode: str | None = None, *, host_funded: bool = False) -> RoomState:
        if len(self.rooms) >= self.settings.max_rooms:
            raise HTTPException(503, "Conversation capacity reached; please try later")
        code = secrets.token_hex(6)
        mode = self.settings.mode
        if audio_mode == "interpreted" and mode != "live":
            raise HTTPException(409, "Live interpretation has not been enabled for this workspace")
        if audio_mode == "original" and mode == "live":
            mode = "transport"
        switchable = self.settings.audio_screening_on_demand and self.settings.mode != "demo"
        room = Room(code=code, title=title, mode=mode, screening_switchable=switchable,
                    voice_required=mode == "live" and self.settings.voice_cloning_required,
                    engine_on_demand=mode == "live" and self.settings.evon_serverless,
                    screening_mode=self.settings.audio_screening_mode if mode != "demo" else "off")
        duration = self.settings.room_ttl_seconds
        if mode == "live" and not host_funded:
            duration = min(duration, self.settings.usage_max_live_room_seconds)
        state = RoomState(
            room=room,
            expires_at=time.time() + duration,
            host_funded=host_funded and mode == "live",
            metrics=Metrics(simulated=self.settings.mode == "demo"),
        )
        self.rooms[code] = state
        return state

    def issue_session(self, state: RoomState, participant_id: str) -> str:
        token = secrets.token_urlsafe(32)
        self.sessions[token_digest(token)] = Session(
            room_code=state.room.code,
            participant_id=participant_id,
            account_session=account_session.get(),
            expires_at=min(state.expires_at, account_deadline.get(), time.time() + self.settings.session_ttl_seconds),
        )
        self.memberships[(state.room.code, participant_id)] = token_digest(token)
        return token

    def is_active(self, code: str, participant_id: str) -> bool:
        state = self.rooms.get(code)
        digest = self.memberships.get((code, participant_id))
        session = self.sessions.get(digest or "")
        current = time.time()
        return bool(state and state.expires_at > current and session and session.expires_at > current)

    def authenticate(self, token: str, code: str | None = None) -> Session:
        session = self.sessions.get(token_digest(token)) if token else None
        if not session or session.expires_at <= time.time():
            raise HTTPException(401, "Membership expired; rejoin the conversation")
        if code and session.room_code != code.lower():
            raise HTTPException(403, "This membership belongs to another conversation")
        if session.account_session != account_session.get():
            raise HTTPException(403, "This membership belongs to another sign-in")
        state = self.room(session.room_code)
        if not any(p.id == session.participant_id and not p.is_demo for p in state.room.participants):
            raise HTTPException(401, "You have left this conversation")
        return session

    def rate_limit(self, scope: str, identity: str, limit: int, window: float = 60) -> None:
        cutoff = time.monotonic() - window
        key = (scope, identity)
        bucket = [stamp for stamp in self.rate_buckets.get(key, []) if stamp > cutoff]
        if len(bucket) >= limit:
            raise HTTPException(429, "Too many requests; please wait a moment")
        bucket.append(time.monotonic())
        self.rate_buckets[key] = bucket

    def forget_session(self, token: str) -> None:
        digest = token_digest(token)
        session = self.sessions.pop(digest, None)
        if session:
            self.memberships.pop((session.room_code, session.participant_id), None)
        for profile_id, voice in list(self.voices.items()):
            if voice.owner_digest == digest:
                self.voices.pop(profile_id, None)

    def prune(self) -> list[str]:
        current = time.time()
        expired = [code for code, state in self.rooms.items() if state.expires_at <= current]
        for code in expired:
            state = self.rooms.pop(code)
            if state.demo_task:
                state.demo_task.cancel()
            for consumer in state.consumers:
                consumer.overflow.set()
        expired_sessions = [
            digest for digest, session in self.sessions.items()
            if session.expires_at <= current or session.room_code not in self.rooms
        ]
        for digest in expired_sessions:
            session = self.sessions.pop(digest)
            self.memberships.pop((session.room_code, session.participant_id), None)
        for profile_id, voice in list(self.voices.items()):
            if voice.owner_digest not in self.sessions:
                self.voices.pop(profile_id, None)
        cutoff = time.monotonic() - 60
        self.rate_buckets = {
            key: fresh for key, values in self.rate_buckets.items()
            if (fresh := [stamp for stamp in values if stamp > cutoff])
        }
        return expired
