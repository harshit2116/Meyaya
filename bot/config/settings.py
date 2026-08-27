"""Application settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly typed runtime settings for the bot."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    discord_token: str = Field(alias="DISCORD_TOKEN")
    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(alias="REDIS_URL")
    klipy_api_key: str = Field(default="", alias="KLIPY_API_KEY")
    klipy_rating: str = Field(default="g", alias="KLIPY_RATING")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.0-flash", alias="GEMINI_MODEL")
    gemini_live_model: str = Field(
        default="gemini-3.1-flash-live-preview", alias="GEMINI_LIVE_MODEL"
    )
    gemini_voice: str = Field(default="Kore", alias="GEMINI_VOICE")
    gemini_live_system_instruction: str = Field(
        default=(
            "You are Meyaya in a Discord voice chat. Speak naturally and keep replies concise. "
            "Avoid markdown, avoid reading URLs unless asked, avoid filler, and never narrate internal reasoning. "
            "Be playful and friendly, with lively humor that varies naturally."
        ),
        alias="GEMINI_LIVE_SYSTEM_INSTRUCTION",
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    command_prefix: str = Field(default="", alias="COMMAND_PREFIX")
    guild_id: int | None = Field(default=None, alias="GUILD_ID")
    monitor_channel_ids: list[int] = Field(default_factory=list, alias="MONITOR_CHANNEL_IDS")

    @field_validator("guild_id", mode="before")
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings object."""

    return Settings()
