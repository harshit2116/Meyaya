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

The bot accepts both slash commands and written commands using the `uwu ` prefix, for example `uwu hug @user`, `uwu ship @user @user`, `uwu gif anime hug`, and `uwu help`.

Required environment values:

- DISCORD_TOKEN
- DATABASE_URL
- REDIS_URL
- KLIPY_API_KEY for GIF-backed interaction responses

Optional voice/live environment values:

- GEMINI_API_KEY for Gemini chat and Live voice sessions
- GEMINI_LIVE_MODEL default `gemini-3.1-flash-live-preview`
- GEMINI_VOICE default `Kore` (examples: `Kore`, `Leda`, `Aoede`)
- GEMINI_LIVE_SYSTEM_INSTRUCTION to tune conversational behavior in VC

## Main Commands

- `/ship` and `uwu ship @user @user` show a cute ship embed with both profile pictures, an anime love GIF, and a stable love percentage.
- `/iq`, `/dumb`, `/smart`, and `/clown` show daily fun embeds with themed GIFs.
- `/hug`, `/kiss`, `/pat`, and other interaction commands update relationship counters and can include back buttons.
- Mention the bot in chat to use Gemini-powered chat with short-term Redis context and permanent Postgres memories.

## Live Voice Chat (Gemini Live)

This bot includes VC commands:

- `/join` joins your current voice channel and starts a persistent Gemini Live audio session
- `/leave` disconnects and shuts down the live session cleanly
- `/voice` shows or updates runtime voice selection for new sessions
- `/voicecheck` asks the active Gemini Live session to speak a fixed phrase, isolating
  output/playback from microphone receive.
- `/voicediag` displays live DAVE, receive, Gemini, and playback counters for the
  active guild session.

Implementation notes:

- Discord receive/playback uses `discord.py` + `discord-ext-voice-recv`
- Incoming Discord PCM is converted to Gemini Live input format (16-bit PCM, 16kHz mono)
- Gemini native audio output (24kHz PCM) is converted to Discord playback PCM (48kHz stereo)
- Uses automatic/hybrid VAD and interruption-aware playback clearing for barge-in behavior
- Emits explicit DAVE/PCM/Gemini pipeline diagnostics so a failed layer can be identified
  without treating a successful VC connection as proof of inbound audio.

Operational requirements:

- Ensure your bot has Voice permissions (connect, speak)
- Ensure voice dependencies are installed (`PyNaCl`, `davey`, and the DAVE-capable
  `discord-ext-voice-recv` revision declared in `pyproject.toml`). Discord requires
  DAVE end-to-end encryption for voice calls, so the older PyPI receiver release
  cannot decode incoming users' audio and will fail with `OpusError: corrupted stream`.
- Ensure ffmpeg/libopus are available in your runtime environment if your platform requires them

After pulling dependency changes, reinstall the project in the virtual environment
that starts the bot with `python -m pip install --upgrade --force-reinstall -e .`.
Confirm the result with `python -m discord --version`; it should report discord.py
2.7.1 or newer and the `davey` package.

## Project Layout

The source package lives in `bot/` and keeps runtime responsibilities separated:

- `bot/main.py` starts the application.
- `bot/app.py` builds the Discord bot and owns process lifecycle resources.
- `bot/cogs/` contains Discord slash and text command adapters.
- `bot/services/` contains business logic that can be tested without Discord objects.
- `bot/repositories/` contains database access.
- `bot/models/` contains SQLAlchemy table definitions.
- `bot/utils/` contains reusable Discord presentation helpers.
- `bot/views/` contains reusable Discord UI views.
- `bot/data/` contains command definitions and other static runtime data.
- `alembic/` contains database migrations.
- `tests/` contains automated tests.
