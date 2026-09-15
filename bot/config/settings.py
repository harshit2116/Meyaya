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
    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(alias="REDIS_URL")
    redis_required: bool = Field(default=False, alias="REDIS_REQUIRED")
    redis_tls_verify: bool = Field(default=True, alias="REDIS_TLS_VERIFY")
    quota_exempt_guild_id: int = Field(default=1479860234183905443, alias="QUOTA_EXEMPT_GUILD_ID")
    dashboard_enabled: bool = Field(default=False, alias="DASHBOARD_ENABLED")
    dashboard_host: str = Field(default="127.0.0.1", alias="DASHBOARD_HOST")
    dashboard_port: int = Field(default=8080, ge=1, le=65535, alias="DASHBOARD_PORT")
    dashboard_token: str = Field(default="", alias="DASHBOARD_TOKEN")
    klipy_api_key: str = Field(default="", alias="KLIPY_API_KEY")
    klipy_rating: str = Field(default="g", alias="KLIPY_RATING")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    llm_provider: str = Field(default="gemini", alias="LLM_PROVIDER")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")
    gemini_fast_model: str = Field(default="gemini-2.5-flash-lite", alias="GEMINI_FAST_MODEL")
    gemini_reasoning_model: str = Field(default="gemini-2.5-pro", alias="GEMINI_REASONING_MODEL")
    gemini_grounded_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_GROUNDED_MODEL")
    gemini_live_model: str = Field(
        default="gemini-3.1-flash-live-preview", alias="GEMINI_LIVE_MODEL"
    )
    gemini_voice: str = Field(default="Leda", alias="GEMINI_VOICE")
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
