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
4. Apply database migrations with `alembic upgrade head`.
5. Run the bot with `python -m bot.main`.

The bot accepts both slash commands and written commands using the `uwu ` prefix, for example `uwu hug @user`, `uwu ship @user @user`, `uwu gif anime hug`, and `uwu help`.

Required environment values:

- DISCORD_TOKEN
- DATABASE_URL
- REDIS_URL
- KLIPY_API_KEY for GIF-backed interaction responses

Optional voice/live environment values:

- GEMINI_API_KEY for Gemini chat and Live voice sessions
- GEMINI_LIVE_MODEL default `gemini-3.1-flash-live-preview`
- GEMINI_VOICE default `Leda` (examples: `Leda`, `Kore`, `Aoede`)
- GEMINI_LIVE_SYSTEM_INSTRUCTION adds optional VC behavior on top of Meyaya's shared persona

Commands can be invoked as `/command`, `uwu command` (case-insensitive), or `@Meyaya command`.

## Main Commands

- `/ship` and `uwu ship @user @user` show a cute ship embed with both profile pictures, an anime love GIF, and a stable love percentage.
- `/iq`, `/dumb`, `/smart`, and `/clown` show daily fun embeds with themed GIFs.
- `/hug`, `/kiss`, `/pat`, and other interaction commands update relationship counters and can include back buttons.
- Mention the bot in chat to use Gemini-powered chat with short-term Redis context and permanent Postgres memories.

## The Meyaya System

Meyaya has a personality-state layer that is separate from permanent memory:

- Per-server state tracks her current mood, energy, irritation, and the recent reason for her mood.
- Per-member state tracks familiarity, affection, annoyance, and a persistent nickname that Meyaya
  develops after getting to know someone.
- Talking to Meyaya gradually increases familiarity with a cooldown to prevent spam farming.
- Social commands directed at Meyaya change her mood and her opinion of the member. Affectionate
  interactions such as hugs improve affection, while slaps and bonks increase annoyance.
- Mood and annoyance decay from timestamps without a background worker, gradually returning her
  toward a normal baseline.
- Effective state is injected into both Gemini text and Gemini Live voice prompts. Gemini is told
  to express it subtly rather than exposing scores or internal instructions.
- During a direct Gemini conversation, Meyaya may request a harmless self-action intent. The
  code validates it, applies a per-member cooldown, and chooses `cheer`, `pat`, `hug`, `wave`, or
  `highfive` from relationship strength. Gemini cannot invoke marriage, moderation, admin, or
  voice-control commands through this path.
- Explicit natural-language requests can route to the existing social interaction commands with
  the speaking member as actor. The target must be mentioned in the current message, only one
  allowlisted command can run, and marriage always uses the normal consent proposal. Divorce,
  moderation, administration, mass targeting, and voice control are excluded.
- Natural-language daily requests also route through the existing stable daily commands. Meyaya can
  show the speaker's or a mentioned member's daily IQ and identify today's dumbest or smartest
  eligible server member without inventing the result in Gemini text.
- Profiles show Meyaya's current mood, her bond with the member, their nickname, and up to three
  earned titles based on relationship state and interaction history.

Permanent facts and server memories remain owned by the separate Memory System.

## Server lore

Meyaya keeps public server lore separate from personal facts. Gemini can mark a recurring inside
joke or notable shared incident with a hidden lore directive. Matching lore is reinforced instead
of duplicated, prioritized by how established and recent it is, and supplied to both text and live
voice conversations. Private, sensitive, cruel, or one-off material is explicitly excluded.

## Rare proactive behavior

Meyaya can occasionally join conversations in channels approved with `monitor_add`. Proactive
replies require recent activity from multiple members, use a low random chance, and have separate
guild and channel cooldowns persisted in Redis. Gemini can still choose `NO_REPLY` when joining
would feel forced. Commands, non-English messages, startup bursts, DMs, and unmonitored channels
are excluded. The behavior can be tuned with `PROACTIVE_ENABLED`, `PROACTIVE_CHANCE`,
`PROACTIVE_GUILD_COOLDOWN_MINUTES`, and `PROACTIVE_CHANNEL_COOLDOWN_MINUTES`.
It is disabled by default and must be explicitly enabled in `.env`.

Direct Gemini conversation history is isolated per member and per channel. Ambient messages from
monitored channels are stored in a separate observation namespace and are never fed into direct
mention conversations. Successful natural-language commands show only the command result instead
of an additional Gemini acknowledgement.

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
