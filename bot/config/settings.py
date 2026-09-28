"""Application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from bot.data.voices import canonical_voice_name


class Settings(BaseSettings):
    """Strongly typed runtime settings for the bot."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    discord_token: str = Field(alias="DISCORD_TOKEN")
    discord_message_cache_size: int = Field(default=100, ge=1, le=1000, alias="DISCORD_MESSAGE_CACHE_SIZE")
    discord_chunk_on_startup: bool = Field(default=True, alias="DISCORD_CHUNK_ON_STARTUP")
    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(alias="REDIS_URL")
    redis_required: bool = Field(default=False, alias="REDIS_REQUIRED")
    redis_tls_verify: bool = Field(default=True, alias="REDIS_TLS_VERIFY")
    quota_exempt_guild_id: int = Field(default=1479860234183905443, alias="QUOTA_EXEMPT_GUILD_ID")
    dashboard_enabled: bool = Field(default=False, alias="DASHBOARD_ENABLED")
    dashboard_host: str = Field(default="127.0.0.1", alias="DASHBOARD_HOST")
    dashboard_port: int = Field(default=8080, ge=1, le=65535, alias="DASHBOARD_PORT")
    dashboard_public_url: str = Field(default="", alias="DASHBOARD_PUBLIC_URL")
    dashboard_trusted_proxies: str = Field(default="", alias="DASHBOARD_TRUSTED_PROXIES")
    dashboard_token: str = Field(default="", alias="DASHBOARD_TOKEN")
    klipy_api_key: str = Field(default="", alias="KLIPY_API_KEY")
    klipy_rating: str = Field(default="g", alias="KLIPY_RATING")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    llm_provider: str = Field(default="gemini", alias="LLM_PROVIDER")
    ai_enabled: bool = Field(default=True, alias="AI_ENABLED")
    ai_max_concurrent: int = Field(default=2, ge=1, le=10, alias="AI_MAX_CONCURRENT")
    ai_queue_size: int = Field(default=4, ge=0, le=20, alias="AI_QUEUE_SIZE")
    ai_queue_wait_seconds: float = Field(default=6, ge=0, le=15, alias="AI_QUEUE_WAIT_SECONDS")
    gemini_quota_namespace: str = Field(default="meyaya", min_length=1, max_length=80, alias="GEMINI_QUOTA_NAMESPACE")
    gemini_pacing_wait_seconds: float = Field(default=6, ge=0, le=15, alias="GEMINI_PACING_WAIT_SECONDS")
    # Conservative project-specific defaults from the owner's observed limits.
    # Override with the actual limits shown in AI Studio, especially on paid tiers.
    gemini_model_limits: dict[str, dict[str, int]] = Field(default_factory=lambda: {
        "gemini-3.5-flash-lite": {"rpm": 15, "rpd": 500},
        "gemini-3.5-flash": {"rpm": 5, "rpd": 20},
        "gemini-2.5-flash": {"rpm": 5, "rpd": 20},
    }, alias="GEMINI_MODEL_LIMITS")
    ai_user_cooldown_seconds: int = Field(default=5, ge=0, le=300, alias="AI_USER_COOLDOWN_SECONDS")
    ai_max_input_chars: int = Field(default=32000, ge=1000, le=100000, alias="AI_MAX_INPUT_CHARS")
    ai_max_output_tokens: int = Field(default=2048, ge=100, le=8192, alias="AI_MAX_OUTPUT_TOKENS")
    voice_max_sessions: int = Field(default=1, ge=1, le=5, alias="VOICE_MAX_SESSIONS")
    voice_session_minutes: int = Field(default=10, ge=1, le=60, alias="VOICE_SESSION_MINUTES")
    gemini_fallback_model: str = Field(default="", alias="GEMINI_FALLBACK_MODEL")
    gemini_model: str = Field(default="gemini-3.5-flash-lite", alias="GEMINI_MODEL")
    gemini_fast_model: str = Field(default="gemini-3.5-flash-lite", alias="GEMINI_FAST_MODEL")
    gemini_reasoning_model: str = Field(default="gemini-3.5-flash", alias="GEMINI_REASONING_MODEL")
    gemini_grounded_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_GROUNDED_MODEL")
    gemini_live_model: str = Field(
        default="gemini-3.1-flash-live-preview", alias="GEMINI_LIVE_MODEL"
    )
    gemini_voice: str = Field(default="Leda", alias="GEMINI_VOICE")
    ffmpeg_executable: str = Field(default="ffmpeg", alias="FFMPEG_EXECUTABLE")
    jungkook_roleplay_avatar_url: str = Field(default="", alias="JUNGKOOK_ROLEPLAY_AVATAR_URL")
    alya_roleplay_avatar_url: str = Field(default="", alias="ALYA_ROLEPLAY_AVATAR_URL")
    gemini_live_system_instruction: str = Field(
        default=(
            "You are Meyaya in a Discord voice chat. Speak naturally and keep replies concise. "
            "Avoid markdown, avoid reading URLs unless asked, avoid filler, and never narrate internal reasoning. "
            "Be playful and friendly, with lively humor that varies naturally."
        ),
        alias="GEMINI_LIVE_SYSTEM_INSTRUCTION",
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    guild_id: int | None = Field(default=None, alias="GUILD_ID")
    court_channel_id: int | None = Field(default=None, alias="COURT_CHANNEL_ID")
    monitor_channel_ids: list[int] = Field(default_factory=list, alias="MONITOR_CHANNEL_IDS")

    @field_validator("guild_id", "court_channel_id", mode="before")
    @classmethod
    def parse_blank_guild_id(cls, value: object) -> int | None:
        """Treat an empty GUILD_ID as unset."""

        if value in {None, ""}:
            return None
        return int(value)

    @field_validator("gemini_model_limits")
    @classmethod
    def validate_model_limits(cls, value):
        if len(value) > 20:
            raise ValueError("GEMINI_MODEL_LIMITS supports at most 20 models")
        for model, limits in value.items():
            if not model or len(model) > 120 or set(limits) != {"rpm", "rpd"}:
                raise ValueError("Each model needs rpm and rpd limits")
            if not 1 <= limits['rpm'] <= 10000 or not 0 <= limits['rpd'] <= 10000000:
                raise ValueError("rpm must be positive; rpd=0 disables the local daily cap")
        return value

    @field_validator("monitor_channel_ids", mode="before")
    @classmethod
    def parse_monitor_channel_ids(cls, value: object) -> list[int]:
        """Allow comma-separated MONITOR_CHANNEL_IDS in .env files."""

        if value is None:
            return []
        if isinstance(value, str) and value.strip() == "":
            return []
        if isinstance(value, list):
            return [int(v) for v in value]
        if isinstance(value, str):
            return [int(part.strip()) for part in value.split(",") if part.strip()]
        raise ValueError("MONITOR_CHANNEL_IDS must be a list or comma-separated string")

    @field_validator("gemini_voice")
    @classmethod
    def validate_gemini_voice(cls, value: str) -> str:
        """Reject unsupported voice names before opening a Live session."""

        canonical = canonical_voice_name(value)
        if canonical is None:
            raise ValueError("GEMINI_VOICE must be a supported Gemini prebuilt voice")
        return canonical


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings object."""

    return Settings()
