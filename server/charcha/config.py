from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from .voice_catalog import LEGACY_DEFAULT_TIMBRE_VOICE


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        extra="ignore", populate_by_name=True,
    )

    mode: Literal["demo", "transport", "live"] = Field(default="demo", validation_alias=AliasChoices("CHARCHA_MODE", "ARTHA_MODE"))
    charcha_public_origin: str = Field(default="http://localhost:5180", validation_alias=AliasChoices("CHARCHA_PUBLIC_ORIGIN", "ARTHA_PUBLIC_ORIGIN", "artha_public_origin"))
    charcha_auth_domain: str = Field(default="", validation_alias=AliasChoices("CHARCHA_AUTH_DOMAIN", "ARTHA_AUTH_DOMAIN", "artha_auth_domain"))
    charcha_identity_provider: Literal["auth0", "keycloak"] = "auth0"
    charcha_oidc_issuer: str = ""
    charcha_auth_client_id: str = Field(default="", validation_alias=AliasChoices("CHARCHA_AUTH_CLIENT_ID", "ARTHA_AUTH_CLIENT_ID", "artha_auth_client_id"))
    charcha_auth_client_secret: SecretStr = Field(default=SecretStr(""), validation_alias=AliasChoices("CHARCHA_AUTH_CLIENT_SECRET", "ARTHA_AUTH_CLIENT_SECRET", "artha_auth_client_secret"))
    charcha_admin_connection: str = Field(default="Username-Password-Authentication", validation_alias=AliasChoices("CHARCHA_ADMIN_CONNECTION", "ARTHA_ADMIN_CONNECTION", "artha_admin_connection"))
    charcha_admin_subject: str = Field(default="", validation_alias=AliasChoices("CHARCHA_ADMIN_SUBJECT", "ARTHA_ADMIN_SUBJECT", "artha_admin_subject"))
    charcha_meeting_host_email: str = Field(default="", validation_alias=AliasChoices("CHARCHA_MEETING_HOST_EMAIL", "ARTHA_MEETING_HOST_EMAIL", "artha_meeting_host_email"))
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
    evon_modal_key: SecretStr = SecretStr("")
    evon_modal_secret: SecretStr = SecretStr("")
    evon_model: str = ""
    # Operator-reviewed additional public HTTPS origins for reviewer-owned Evon.
    # Modal-owned subdomains are supported without expanding this allowlist.
    reviewer_gpu_allowed_origins: Annotated[list[str], NoDecode] = []
    gnani_stt_url: str = "wss://api.vachana.ai/stt/v3/stream"
    # Unset preserves the provider-selected legacy default; opt in explicitly.
    gnani_stt_model: Literal["prisma-v2.5", "prisma-v3.0"] | None = None
    gnani_tts_url: str = "wss://api.vachana.ai/api/v1/tts"
    gnani_embedding_url: str = "https://api.vachana.ai/api/v1/tts/voice-clone/embeddings"
    timbre_model: str = "timbre-v2.5"
    timbre_voice: str = LEGACY_DEFAULT_TIMBRE_VOICE
    # Optional language-specific stock voices, from the selected model's catalog.
    timbre_voice_hi: str = ""
    timbre_voice_ta: str = ""
    timbre_voice_bn: str = ""
    timbre_voice_en: str = ""
    timbre_voice_te: str = ""
    timbre_voice_kn: str = ""
    timbre_voice_ml: str = ""
    timbre_voice_mr: str = ""
    timbre_voice_gu: str = ""
    timbre_voice_pa: str = ""
    voice_clone_model: str = "vachana-vc-v1"
    voice_cloning_required: bool = False
    evon_serverless: bool = False
    room_ttl_seconds: int = Field(default=14400, ge=60, le=86400)
    session_ttl_seconds: int = Field(default=14400, ge=60, le=86400)
    max_participants: int = Field(default=8, ge=0)
    max_rooms: int = Field(default=100, ge=1, le=10000)
    # Speak each translated clause as soon as the model emits it (live mode).
    evon_stream_clauses: bool = True
    evon_clause_min_chars: int = Field(default=24, ge=8, le=120)
    evon_clause_max_chars: int = Field(default=180, ge=40, le=600)
    max_pending_turns: int = Field(default=8, ge=1, le=32)
    translation_lookahead: int = Field(default=2, ge=1, le=2)
    translation_queue_max_age_seconds: float = Field(default=4, ge=0.1, le=30)
    max_turns_per_room: int = Field(default=1000, ge=10, le=10000)
    provider_timeout_seconds: float = Field(default=45, ge=1, le=120)
    event_queue_size: int = Field(default=128, ge=4, le=1024)
    audio_queue_frames: int = Field(default=100, ge=10, le=500)
    audio_sample_rate: int = 24000
    # Local experiments are opt-in. Monitor reports scores without blocking speech.
    local_audio_lab_enabled: bool = False
    audio_screening_mode: Literal["off", "monitor", "enforce"] = "off"
    audio_screening_on_demand: bool = False
    # Retain the deployment default; local CPU tuning must be measured per host.
    audio_screening_cpu_threads: int = Field(default=1, ge=1, le=4)
    audio_screening_model_path: Path = Path(__file__).resolve().parents[1] / "models" / "aasist" / "model.onnx"
    # Application safeguards count reserved attempts/units, not vendor billing.
    usage_db_path: Path = Path(__file__).resolve().parents[1] / "data" / "usage.sqlite3"
    usage_require_flow_approval: bool = True
    usage_require_room_scope: bool = False
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
    # Operator grant expiry cap (seconds) for scripts/provider_flow.py approvals.
    usage_approval_max_seconds: int = Field(default=300, ge=1, le=86400)
    # After a mute, keep the recognizer open this long and feed silence so the
    # final phrase is finalised and translated instead of being cut off.
    stt_mute_grace_seconds: float = Field(default=2.5, ge=0, le=10, allow_inf_nan=False)
    # A recognizer connection that lived this long before closing is "healthy":
    # its close resets the retry counter instead of consuming the retry budget.
    stt_healthy_seconds: float = Field(default=10, ge=0, le=600, allow_inf_nan=False)
    # Gnani closes after 60 s without speech unless told otherwise (5-900).
    gnani_stt_idle_timeout_sec: int = Field(default=900, ge=5, le=900)
    usage_max_live_room_seconds: int = Field(default=900, ge=60, le=86400)

    @field_validator("cors_origins", "reviewer_gpu_allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, value):
        if isinstance(value, str):
            return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("gnani_stt_model", mode="before")
    @classmethod
    def blank_stt_model_is_unselected(cls, value):
        # Empty optional .env entries preserve the existing provider default.
        return None if isinstance(value, str) and not value.strip() else value

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

    def missing_transport_config(self) -> list[str]:
        """Local raw-audio tests need an SFU, never speech-provider credentials."""
        return [name for name in self.missing_live_config() if name.startswith("LIVEKIT_")]
