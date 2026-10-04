"""Alembic environment configuration."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from bot.config.settings import get_settings
from bot.database.base import Base
from bot.database.urls import postgres_url

# Import all models so Alembic can detect them
from bot.models import court, daily, guild_settings, marriage, relationship, user  # noqa: F401
from bot.models import memory, meyaya_state, server_lore  # noqa: F401
from bot.models import usage  # noqa: F401
from bot.models import request_log  # noqa: F401
from bot.models import moderation  # noqa: F401
from bot.models import character_catalog  # noqa: F401
from bot.models import chat_blacklist  # noqa: F401
from bot.models import ai_budget  # noqa: F401
from bot.models import fantasy_profile  # noqa: F401
from bot.models import fantasy_duel  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """Return a synchronous database URL for Alembic."""

    url, _ = postgres_url(get_settings().database_url, asynchronous=False)
    return url.render_as_string(hide_password=False)


def run_migrations_offline() -> None:
    """Run migrations without a live database connection."""

    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""

    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
