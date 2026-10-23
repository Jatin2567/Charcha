from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        extra="ignore", populate_by_name=True,
    )

    mode: Literal["demo", "live"] = Field(default="demo", validation_alias="ARTHA_MODE")
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173", "http://127.0.0.1:5173"
    ]
    livekit_url: str = ""
    livekit_internal_url: str = ""
    livekit_api_key: SecretStr = SecretStr("")
    livekit_api_secret: SecretStr = SecretStr("")
    gnani_api_key: SecretStr = SecretStr("")
    evon_base_url: str = ""
    evon_api_key: SecretStr = SecretStr("")
    evon_model: str = ""
    gnani_stt_url: str = "wss://api.vachana.ai/stt/v3/stream"
    gnani_tts_url: str = "wss://api.vachana.ai/api/v1/tts"
    gnani_embedding_url: str = "https://api.vachana.ai/api/v1/tts/voice-clone/embeddings"
    timbre_model: str = "timbre-v2.5"
    timbre_voice: str = "Nalini"
    voice_clone_model: str = "vachana-vc-v1"
    room_ttl_seconds: int = Field(default=14400, ge=60, le=86400)
    session_ttl_seconds: int = Field(default=14400, ge=60, le=86400)
    max_participants: int = Field(default=8, ge=2, le=32)
    max_rooms: int = Field(default=100, ge=1, le=10000)
    max_pending_turns: int = Field(default=8, ge=1, le=32)
    max_turns_per_room: int = Field(default=1000, ge=10, le=10000)
    provider_timeout_seconds: float = Field(default=45, ge=1, le=120)
    event_queue_size: int = Field(default=128, ge=4, le=1024)
    audio_queue_frames: int = Field(default=100, ge=10, le=500)
    audio_sample_rate: int = 24000

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value):
        if isinstance(value, str):
            return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
        return value

    def missing_live_config(self) -> list[str]:
        required = {
            "LIVEKIT_URL": self.livekit_url,
            "LIVEKIT_API_KEY": self.livekit_api_key.get_secret_value(),
            "LIVEKIT_API_SECRET": self.livekit_api_secret.get_secret_value(),
            "GNANI_API_KEY": self.gnani_api_key.get_secret_value(),
            "EVON_BASE_URL": self.evon_base_url,
            "EVON_MODEL": self.evon_model,
        }
        return [name for name, value in required.items() if not value]
