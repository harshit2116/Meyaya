"""Alembic environment configuration."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from bot.config.settings import get_settings
from bot.database.base import Base
from bot.models import daily, relationship, user
from bot.models import marriage  # noqa: F401  # noqa: F401

config = context.config
fileConfig(config.config_file_name) if config.config_file_name else None
target_metadata = Base.metadata


def get_url() -> str:
    """Resolve the database URL from the active bot settings."""

    return get_settings().database_url


def run_migrations_offline() -> None:
    """Run migrations without a live database connection."""

    context.configure(url=get_url(), target_metadata=target_metadata, literal_binds=True)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""

    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
