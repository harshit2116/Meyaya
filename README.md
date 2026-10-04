# Meyaya

Meyaya is a Discord character bot built with Python. She supports social reactions, daily fun,
profiles, marriage, multiplayer games, court cases, Gemini chat and memory, English-only monitoring,
and live voice conversations.

## Deferred remote-dashboard integration

The optional remote-dashboard connection is currently inactive.
Its API, proxy, tunnel launcher and live-stream hooks are not active. The existing
dashboard, Meyaya Health and error-ID features remain available.

## Requirements

- Python 3.12
- PostgreSQL
- Redis
- A Discord bot token
- A Gemini API key for AI chat and voice
- A Klipy API key for reaction GIFs

## Quick Start

Hosting on HeavenCloud with 512 MB? Follow [the HeavenCloud setup](docs/heavencloud.md).

For the 0.5-core / 512MB RAM / 2GB storage plan, install production dependencies
with `python -m pip install --no-cache-dir --prefer-binary -r requirements.txt`,
then use `python start.py` as the startup command. Install only when dependencies
change, not on every restart. Keep PostgreSQL and Redis external, run one bot
process, and run the dashboard on your laptop. Do not upload local virtual
environments or development dependencies. Voice loads its SDK on first use;
the first voice join therefore has some extra startup work.

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

Server managers can run `/serversetup` for guided configuration and `/serverdashboard` for
remaining messages and server activity. Both also work with `uwu`. See [server setup](docs/server-setup.md).

## Main Features

- Social reactions with GIFs, counters, and response buttons
- Stable daily IQ, smartest, dumbest, and clown results
- Profiles combining Discord, social, mood, relationship, and marriage data
- Ship, fortune, rate, bestie score, most likely, and 8-ball commands
- Reddit-style mock posts: `uwu reddit <post>` or `/reddit post:<text>`.
  Uses the server name, requesting member's username/avatar and a short Gemini comment
  from Meyaya. `uwu reddit <post> | <comment>` (or the slash `comment` field) bypasses AI.
  If AI is unavailable, the card is sent without a comment. `rate` is entirely local.
- Duck animation: `uwu duck [@member]` or `/duck`. Defaults to the requester;
  overlays the member's avatar and name on the bundled duck-ejection GIF without AI.
  Rendering uses the shared image worker, 47 sampled frames preserving the full
  timeline, a bounded queue and a 10-second member cooldown. Template and source note:
  `bot/assets/duck/`; renderer: `bot/services/duck_card.py`.
- Reddit and duck share ship's bounded CDN avatar downloader/cache. Failed downloads
  retry on the next call and emit `party_avatar_unavailable` without leaking URLs.
  Both use the existing loading indicator after 0.5 seconds, removed on completion.
- Consent-based marriage, vows, anniversaries, and confirmed divorce
- Anonymous multiplayer games judged by Gemini
- Entertainment-only court cases with registered witnesses, fair follow-ups, and explained verdicts
- Google-grounded fact checks for one message or a selected argument range
- Reply-aware Gemini chat with personal memory and server lore
  - Public image cards retain the actual scores, selected members, card fields, and Reddit
    post/comment text. Replies use the summary attached to that specific result.
    Summaries are process-local, capped at 512 messages / 2,000 characters each, and expire
    after 24 hours. Restarting clears them; private/ephemeral responses are excluded.
  - Rapid messages from one member in one channel become one AI turn after 0.75 seconds
    of quiet, with a 2-second maximum collection window. A mention or reply to Meyaya
    starts the conversation; bare follow-ups within 2 seconds can join it. Commands,
    other members, and messages directed at other people stay separate.
    Messages arriving during generation wait for the previous reply and history write.
    Pending batches are capped at 6 messages / 6,000 characters and respect existing
    AI capacity and member cooldowns. Recent history is trimmed to the input budget.
- Jungkook RP and Alya RP replies with separate webhook names and avatars
- Mood, familiarity, affection, annoyance, nicknames, and natural actions
- Profile Studio image cards for profile checks, auras, palettes, duo styles, and calling cards
- Optional three-strike English-only monitoring with 10-minute timeouts
- Per-server command prefixes and a manager-only administration dashboard
- Gemini Live voice chat with DAVE receive support and diagnostics
- One compact pastel interface across commands, games, profiles, and errors

## Configuration

Copy `.env.example` to `.env`. Never commit `.env` or private identity/rule files.
Only the sanitized `personality.v1.json` and `gemini_persona.txt` inside `bot/private/` are public.

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

`CHAT_BATCH_DELAY_SECONDS` controls the quiet period (default `0.75`);
`CHAT_BATCH_MAX_WAIT_SECONDS` caps collection time (default `2`). Set the delay to `0`
for immediate dispatch while retaining ordered processing. For a new image command,
call `remember_command_result(ctx, **result_data)` from `bot/utils/command_context.py`
immediately before `ctx.send`. Supply only the public data shown on that result;
the response cache records it after a successful send without another model request.

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
# Chat channel settings

Server managers can use `uwu chatbind channel #chat` to limit Meyaya's conversational replies to one text channel, `uwu chatbind server` to allow chat across the server, or `uwu chatbind status` to see the setting. The same options are available through `/chatbind`. Automatic replies follow this setting; threads are excluded when bound to a channel. Other commands retain their usual access. The default is the entire server.
## Meyaya Health (hosted owner dashboard)

Use `uwu owner`, unlock the private dashboard, then open **Meyaya Health**. It combines gateway status, PostgreSQL/Redis check latency, observed Gemini text/Live outcomes, configured per-model attempt budgets, AI active/waiting slots, process RSS/container memory, scheduler lag, CPU throttling, guild count, and distinct request actors seen since startup.

The page refreshes every 30 seconds while visible. Dependency and quota checks are cached/coalesced; PostgreSQL uses the existing pool with read-only `SELECT 1`, Redis uses `PING`, and Gemini status uses real outcomes rather than quota-consuming probes. Unknown means no recent outcome, not an outage. Shared-model routes share budgets. Budgets are Meyaya's configured limits, not Google's live entitlement.

Unexpected command failures and unavailable AI chat replies include an `MY-XXXXXXXX` error ID. Search it in Health to view safe command/server/stage/timing/provider metadata and traceback locations. Latest 30 incidents are shown, 500 retained in memory; exact searches also check the existing rotating `logs/telemetry.jsonl` backups across restarts. No raw exception messages, SQL parameters, prompts, or credentials are included.

429/503/DB counters cover observed attempts in rolling minute buckets for up to 24 hours of the current process; they reset on restart. RAM is process RSS, not total container usage; throttling is throttled time/sample interval, not CPU utilization. Unsupported metrics display unavailable. No schema migration or new service is needed.

Implementation: `bot/logging/health.py`, `bot/services/owner_health.py`, `bot/utils/host_metrics.py`, `bot/services/model_quota.py`, `bot/utils/command_timing.py`, and `bot/web/`. All health/error API routes use the existing owner session protection. A standalone local dashboard has no hosted process telemetry.

# Local owner dashboard

Run `python dashboard.py` from the repository in your VS Code terminal. Use the same private `DATABASE_URL` as the hosted bot. This starts only the dashboard at `http://127.0.0.1:8080`, never a second Discord connection. No login/token is required in this local-only mode. Anyone using your laptop can access it while running; do not expose or tunnel it. Loopback, Host, Origin and cross-site protections remain enabled. Use `python dashboard.py --port 8081` if the port is busy. Stop with Ctrl+C.

It reads cloud request logs, memories, nicknames, quotas and blacklist records. Settings and blacklist changes affect the shared production database; the updated bot refreshes its caches every 60 seconds. No migration is run. Server IDs are shown from saved records (not a live membership list); live Discord names, voice/game status and in-process model telemetry are unavailable. The hosted dashboard remains authenticated and can stay disabled. Never share database credentials.
