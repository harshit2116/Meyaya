# Meyaya

Meyaya is a Discord character bot built with Python. She supports social reactions, daily fun,
profiles, marriage, multiplayer games, court cases, Gemini chat and memory, English-only monitoring,
and live voice conversations.

## Requirements

- Python 3.12
- PostgreSQL
- Redis
- A Discord bot token
- A Gemini API key for AI chat and voice
- A Klipy API key for reaction GIFs

## Quick Start

For persistent Redis and container deployment, see [the deployment guide](docs/deployment.md).
For server usage, daily chat limits, and the owner web dashboard, see [owner operations](docs/owner-dashboard.md).
See [moderation controls](docs/moderation.md) and [Docker deployment](docs/deployment.md) for the new rules and hosting setup.

```powershell
git clone <repository-url>
cd Meyaya
py -3.12 -m venv .venv-win
.\.venv-win\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Fill in `.env`, then prepare and start the bot:

```powershell
alembic upgrade head
python -m bot.main
```

## Command Styles

Every command is available in these forms:

- Slash: `/hug @member`
- Prefix: `uwu hug @member` or `Uwu hug @member`
- Mention: `@Meyaya hug @member`

Mention Meyaya without a command to talk to her through Gemini. Use `/help` for the complete,
interactive command list.

`uwu` is the default written prefix for every server. Members with Manage Server can change it
with `/prefix value:u` or `uwu prefix u`, and reset it with `/prefix value:reset`.
Owner operations are available in the web dashboard.

## Main Features

- Social reactions with GIFs, counters, and response buttons
- Stable daily IQ, smartest, dumbest, and clown results
- Profiles combining Discord, social, mood, relationship, and marriage data
- Ship, fortune, rate, bestie score, most likely, and 8-ball commands
- Consent-based marriage, vows, anniversaries, and confirmed divorce
- Anonymous multiplayer games judged by Gemini
- Entertainment-only court cases with registered witnesses, fair follow-ups, and explained verdicts
- Google-grounded fact checks for one message or a selected argument range
- Reply-aware Gemini chat with personal memory and server lore
- Jungkook RP and Alya RP replies with separate webhook names and avatars
- Mood, familiarity, affection, annoyance, nicknames, and natural actions
- Optional three-strike English-only monitoring with 10-minute timeouts
- Per-server command prefixes and a manager-only administration dashboard
- Gemini Live voice chat with DAVE receive support and diagnostics
- One compact pastel interface across commands, games, profiles, and errors

## Configuration

Copy `.env.example` to `.env`. Never commit `.env` or files inside `bot/private/`.

Important optional settings:

- `GUILD_ID` speeds up slash-command sync for one development server.
- `COURT_CHANNEL_ID` is an optional legacy fallback. Server managers can use `/setcourt` and
  `/removecourt`; the saved per-server setting takes priority.
- `GEMINI_VOICE` selects the live voice. The default is `Leda`.
- `LLM_PROVIDER=gemini` selects the text model provider (the default).
- `GEMINI_FAST_MODEL` handles moderation and lightweight fun text.
- `GEMINI_MODEL` handles normal chat and roleplay.
- `GEMINI_REASONING_MODEL` judges Court and multiplayer games.
- `GEMINI_GROUNDED_MODEL` handles source-backed fact checks.
- `JUNGKOOK_ROLEPLAY_AVATAR_URL` and `ALYA_ROLEPLAY_AVATAR_URL` set public image URLs for
  roleplay messages. Meyaya's avatar is the fallback.
- `/autoresponder mode:enable` enables occasional automatic replies per server; use `disable` to stop.
  Written commands work too: `uwu autoresponder enable`. Manage Server is required.
  It defaults to disabled and saves across restarts. It considers new messages in channels Meyaya
  can read and write, independently of English-only monitoring. Quiet servers get more opportunities
  (up to once per 5 minutes), moderate servers once per 15 minutes, and busy servers once per 45 minutes.
  There is a five-minute observation period after startup; no messages means no automatic replies.

Private persona, voice rules, roleplay prompts, and identity configuration belong in `bot/private/`,
which Git ignores. Roleplay also requires `Manage Webhooks` in the destination channel.

## Development Checks

Games now enforce explicit phases and keep submissions locked during judging retries.
Model metrics and game transitions are saved to rotating `logs/telemetry.jsonl` files.
See [game engines and diagnostics](docs/game-engines-and-telemetry.md) for lifecycle and log fields.

Meyaya's personality now lives in the private, versioned `bot/private/personality.v1.json`.
Memory, tool, identity and voice rules are separate. Each feature selects its own prompt profile;
game judging, court, language moderation and fact-checking have independent instructions.
See [prompt ownership](bot/prompts/README.md) for which file controls each behavior.

Text features use `LLMProvider` in `bot/services/llm.py`: `generate()` handles chat and
Meyaya directives, `generate_json()` returns a JSON object for domain validation,
`summarize()` returns a summary, and `grounded_generate()` returns text with sources.
`generate_text()` supplies unmodified model text. Unavailable text results return `None`;
unsupported or failed grounding raises `GroundingError`.

`ModelRouter` selects fast, balanced, reasoning, or grounded models from the active feature.
If a specialized non-grounded model is unavailable, it retries once through the balanced model.
Memory V2 stores a verified subject, relation, value, confidence, source, and lifecycle status.
Contradictory facts are withheld from prompts; the old memory-resolution command is no longer exposed.

To add another provider, implement `generate_text()` in an `LLMProvider` subclass and
register it in `bot/services/llm_factory.py`. Translate neutral `role`/`content` history
inside that adapter. Implement `grounded_generate()` if the provider supports search.
OpenAI is not yet implemented. Live voice remains a separate Gemini streaming integration.

```powershell
python -m pytest -q
python -m ruff check .
python -m black --check bot tests
alembic check
```

## Project Layout

- `bot/cogs/` - Discord commands and event listeners
- `bot/services/` - reusable feature logic
- `bot/repositories/` - database queries
- `bot/models/` - database table definitions
- `bot/views/` - Discord buttons, forms, and menus
- `bot/data/` - command definitions and prompt builders
- `alembic/` - database migrations

The application starts in `bot/main.py`, creates shared resources in `bot/app.py`, and loads every
command cog from there.
