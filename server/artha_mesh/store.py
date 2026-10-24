"""Bounded, ephemeral session state. Run one worker; no voice clips touch disk."""
from __future__ import annotations

import asyncio
import hashlib
import secrets
import time
from collections import deque
from dataclasses import dataclass, field

from fastapi import HTTPException

from .config import Settings
from .models import Event, Metrics, PerformanceSample, Room, Turn, VoiceProfile

MAX_PERFORMANCE_SAMPLES = 1000


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass
class Session:
    room_code: str
    participant_id: str
    expires_at: float


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

    def create_room(self, title: str) -> RoomState:
        if len(self.rooms) >= self.settings.max_rooms:
            raise HTTPException(503, "Conversation capacity reached; please try later")
        code = secrets.token_hex(6)
        room = Room(code=code, title=title, mode=self.settings.mode)
        state = RoomState(
            room=room,
            expires_at=time.time() + self.settings.room_ttl_seconds,
            metrics=Metrics(simulated=self.settings.mode == "demo"),
        )
        self.rooms[code] = state
        return state

    def issue_session(self, state: RoomState, participant_id: str) -> str:
        token = secrets.token_urlsafe(32)
        self.sessions[token_digest(token)] = Session(
            room_code=state.room.code,
            participant_id=participant_id,
            expires_at=min(state.expires_at, time.time() + self.settings.session_ttl_seconds),
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
