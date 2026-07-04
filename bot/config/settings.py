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
    giphy_rating: str = Field(default="g", alias="GIPHY_RATING")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.0-flash", alias="GEMINI_MODEL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    command_prefix: str = Field(default="", alias="COMMAND_PREFIX")
    guild_id: int | None = Field(default=None, alias="GUILD_ID")

    @field_validator("guild_id", mode="before")
    @classmethod
    def parse_blank_guild_id(cls, value: object) -> int | None:
        """Treat an empty GUILD_ID as unset."""

        if value in {None, ""}:
            return None
        return int(value)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings object."""

    return Settings()
