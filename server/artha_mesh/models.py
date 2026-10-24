from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

LanguageCode = Literal["hi", "ta", "bn", "en"]
VoiceMode = Literal["standard", "cloned"]

LANGUAGES = [
    {"code": "hi", "name": "Hindi", "native_name": "हिन्दी"},
    {"code": "ta", "name": "Tamil", "native_name": "தமிழ்"},
    {"code": "bn", "name": "Bengali", "native_name": "বাংলা"},
    {"code": "en", "name": "English", "native_name": "English"},
]
LANGUAGE_NAMES = {item["code"]: item["name"] for item in LANGUAGES}
BCP47 = {"hi": "hi-IN", "ta": "ta-IN", "bn": "bn-IN", "en": "en-IN"}


def now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CreateRoom(RequestModel):
    title: str = Field(default="A new conversation", min_length=1, max_length=100)


class JoinRoom(RequestModel):
    name: str = Field(min_length=1, max_length=60)
    language: LanguageCode
    voice_mode: VoiceMode = "standard"
    voice_profile_id: str | None = None
    consent: bool = False


class UpdateParticipant(RequestModel):
    language: LanguageCode | None = None
    voice_mode: VoiceMode | None = None
    voice_profile_id: str | None = None
    muted: bool | None = None


class LeaveRoom(RequestModel):
    participant_id: str


class SubmitText(RequestModel):
    text: str = Field(min_length=1, max_length=2000)

    @field_validator("text")
    @classmethod
    def no_control_characters(cls, value: str) -> str:
        if any(ord(c) < 32 and c not in "\n\t" for c in value):
            raise ValueError("Text contains unsupported control characters")
        return value


class DemoScenario(RequestModel):
    scenario: Literal["trade"] = "trade"


class ConfirmTurn(RequestModel):
    utterance_id: str


class Participant(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    language: LanguageCode
    voice_mode: VoiceMode = "standard"
    muted: bool = False
    is_agent: bool = False
    is_demo: bool = False
    joined_at: datetime = Field(default_factory=now)


class Room(BaseModel):
    id: str = Field(default_factory=new_id)
    code: str
    title: str
    created_at: datetime = Field(default_factory=now)
    mode: Literal["demo", "live"]
    participants: list[Participant] = Field(default_factory=list)


class Turn(BaseModel):
    id: str = Field(default_factory=new_id)
    speaker_id: str
    speaker_name: str
    source_language: LanguageCode
    text: str
    created_at: datetime = Field(default_factory=now)
    translations: dict[str, str] = Field(default_factory=dict)
    confirmed_by: list[str] = Field(default_factory=list)
    status: Literal["processing", "complete", "error"] = "processing"


class Metrics(BaseModel):
    turns: int = 0
    stt_ms: float = 0
    mt_ms: float = 0
    tts_ms: float = 0
    total_ms: float = 0
    p50_ms: float = 0
    p95_ms: float = 0
    measurement: Literal["server_pipeline"] = "server_pipeline"
    simulated: bool = False


class PerformanceSample(BaseModel):
    """A terminal language branch; contains no conversation text or identity."""

    id: str = Field(default_factory=new_id)
    utterance_id: str
    source_language: LanguageCode
    target_language: LanguageCode
    input_kind: Literal["audio", "text"]
    voice_mode: VoiceMode = "standard"
    status: Literal["complete", "error", "cancelled"] = "complete"
    measurement: Literal["server_first_pcm", "source_forwarded", "simulated"]
    queue_ms: float | None = None
    stt_ms: float | None = None
    mt_ms: float | None = None
    tts_first_pcm_ms: float | None = None
    total_ms: float | None = None
    created_at: datetime = Field(default_factory=now)
    error_stage: str | None = None


class Event(BaseModel):
    id: str = Field(default_factory=new_id)
    type: str
    timestamp: datetime = Field(default_factory=now)
    payload: dict


class VoiceProfile(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    created_at: datetime = Field(default_factory=now)
    mode: Literal["demo", "live"]
