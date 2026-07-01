# Meyaya

Meyaya is a focused Discord social interaction bot built with `discord.py`, PostgreSQL, SQLAlchemy async, and Pillow.

## Scope

This project intentionally stays centered on:

- social interaction commands
- shared relationship counters
- lightweight user profiles
- daily server fun commands

## Development

1. Create and activate a Python 3.12 environment.
2. Install dependencies from `pyproject.toml`.
3. Copy `.env.example` to `.env` and fill in the values.
4. Run the bot with `python -m bot.main`.

The bot accepts both slash commands and written commands using the `uwu ` prefix, for example `uwu hug @user`, `uwu gif anime hug`, and `uwu help`.

Required environment values:

- DISCORD_TOKEN
- DATABASE_URL
- REDIS_URL
- GIPHY_API_KEY for GIF-backed interaction responses

## Project Layout

The source package lives in `bot/` and is organized around commands, services, repositories, and models.
