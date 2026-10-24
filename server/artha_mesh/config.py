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
    # Application safeguards count reserved attempts/units, not vendor billing.
    usage_db_path: Path = Path(__file__).resolve().parents[1] / "data" / "usage.sqlite3"
    usage_require_flow_approval: bool = True
    # Public usage summaries must not expose manually entered financial evidence.
    # Enable only for an operator-controlled local API, never public deployment.
    usage_show_private_balance: bool = False
    # Optional human-reported reference only; never used to estimate vendor charges.
    usage_reported_request_rate_inr: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    usage_stt_inr_per_hour: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    usage_tts_inr_per_10000_characters: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    usage_stt_seconds_per_day: int = Field(default=600, ge=0, le=864000)
    usage_stt_connections_per_day: int = Field(default=30, ge=0, le=100000)
    usage_mt_requests_per_day: int = Field(default=100, ge=0, le=1000000)
    usage_mt_characters_per_day: int = Field(default=30000, ge=0, le=100000000)
    usage_tts_requests_per_day: int = Field(default=100, ge=0, le=1000000)
    usage_tts_characters_per_day: int = Field(default=30000, ge=0, le=100000000)
    usage_voice_enrollments_per_day: int = Field(default=3, ge=0, le=100000)
    usage_max_concurrent_stt: int = Field(default=3, ge=1, le=32)
    usage_max_concurrent_operations: int = Field(default=2, ge=1, le=32)
    usage_max_queued_operations: int = Field(default=16, ge=0, le=256)
    usage_provider_admission_timeout_seconds: float = Field(default=5, ge=0.01, le=30)
    usage_stt_max_retries: int = Field(default=3, ge=0, le=10)
    usage_max_live_room_seconds: int = Field(default=900, ge=60, le=86400)

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
