# Meyaya

Meyaya is a Discord character bot built with Python. She supports social reactions, daily fun,
profiles, marriage, multiplayer games, court cases, Gemini chat and memory, English-only monitoring,
and live voice conversations.

Meyaya stays Do Not Disturb and rotates her activity every five minutes, starting
with Playing immediately. The cycle includes Watching and the custom status
“The Girl at the end of every story”. Set `PRESENCE_STREAM_URL` to a valid Twitch
or YouTube HTTPS link in the deployed environment to include Streaming, then
restart the bot. Edit `bot/cogs/presence.py` to change the texts. Presence updates
are logged as `presence_updated`; reconnects reapply the current activity.
The `Meyaya` custom-status emoji is best-effort and may be omitted by Discord.

## Fantasy awakenings and rebirth

`/awaken` (or `uwu awaken`) opens a confirmation ritual and reveals a saved,
global fantasy identity. `/fantasyprofile [member]` opens its Soul Interface with
Character, Weapon, Abilities and Details tabs.
Affinity and weapon reveals lead to a Meyaya/Veyra oath choice, then the complete
identity card. Alignment adds patron titles, commentary, visual themes and small
`/versus` combat resonances; it is locked until rebirth. It also grants celestial
Origin or ominous Erasure guardian forms. Expired/unclaimed reveals resume through
the owner's `/fantasyprofile`. Existing core classes, weapons and stats stay intact.
These commands use local generation and

`/rebirth` / `uwu rebirth` offers a self-only confirmation to reroll the entire
build, weapon and guardian, with a persistent 24-hour cooldown and rebirth count.

## Command help and parameter names

`/help` and `uwu help` immediately list every public command, grouped by category.
The optional category menu shows descriptions; `/help command:<name>` or
`uwu help <name>` shows exact syntax and examples. No command picker or paging
hides the command list.

`bot/data/help_catalog.py` is the source of public command descriptions, reused
for slash descriptions, prefix help, category help, autocomplete and command knowledge.
Keep descriptions within Discord's 100-character limit.

## Bad Apple!! Unicode animation

**Currently disabled:** the bot does not load this cog, and its slash commands,
prefix commands, help entries and aliases have been removed. Implementation files,
preprocessing tools and cached media are retained for future use. The instructions
below document the retained implementation and apply only if it is re-enabled.

`/badapple` (or `uwu badapple`, shortcut `uwu ba`) plays every preprocessed frame
in order by editing one plain code-block message. `/badapplestop` (`uwu bas`)
cancels it; only its starter or a member with Manage Messages in that channel can
stop it. One animation is allowed across the entire bot process. Both commands
load through the existing cog loader and normal startup command sync. No audio
is played. Missing media does not prevent the bot or the cog from loading.

Supply the **complete local video yourself**. Keep it outside the repository, or
place it in the ignored `artifacts/badapple/source/` directory. The bot does not
download media. On your development machine, install FFmpeg (including ffprobe)
and the project's existing Python dependencies, then run from the repository root:

```powershell
python -m scripts.preprocess_badapple "artifacts/badapple/source/bad-apple.mp4" --output "artifacts/badapple/frames.jsonl.gz" --width 48 --fps 1 --threshold 128
```

The filename is your choice. If FFmpeg is not on PATH, append
`--ffmpeg "path/to/ffmpeg" --ffprobe "path/to/ffprobe"`. Conversion uses the existing
Pillow dependency and FFmpeg executable; it needs no Discord token, database,
Redis, or settings file. Run it locally, not on the constrained production host.
It decodes through EOF, validates duration coverage, and writes a deterministic
gzip JSON-lines cache atomically. Use `--overwrite` to replace a cache.

`--width` and `--height` set Braille columns and rows; omitted height is calculated
from the source display aspect ratio. Each character contains 2×4 dots. Layout
assumes monospace characters are approximately half as wide as they are tall;
Discord clients and font fallback can vary. Custom dimensions letterbox the
image. White pixels become dots. Sampling and playback FPS accept 0.1–6;
playback defaults to **1 FPS**. Playback never exceeds the cache's sampling FPS.
Higher targets are experimental and may be limited by Discord's message-edit API.
Sampling intentionally reduces the source frame rate; playback skips none of
the resulting frames. Rotated sources must first be normalized. A stalled or
failed decoder aborts conversion; `--timeout` defaults to 600 seconds.

Copy only the generated cache to the host's `artifacts/badapple/frames.jsonl.gz`,
relative to the bot's working directory. For container deployments, mount the
file at that location or set `BADAPPLE_CACHE_PATH` to its mounted path. Generated
media is excluded from Git and is not bundled into the image. Optional settings:

| Variable | Default | Purpose |
| --- | --- | --- |
| `BADAPPLE_CACHE_PATH` | `artifacts/badapple/frames.jsonl.gz` | Readable local cache path |
| `BADAPPLE_FPS` | `1` | Target edit FPS, 0.1–6 |

Restart normally with `python -m bot.main`, then invoke `/badapple` in a test server
channel where Meyaya can view and send messages (Send Messages in Threads for a
thread). The acknowledgement reports source duration, frame count and minimum
playback time. For example, a **220-second source at 1 sampled FPS produces about
220 frames** and needs at least 220 seconds at 1 target FPS. Actual values come
from your supplied file; no full Bad Apple source is included or assumed.

Discord does not promise a fixed message-edit rate. Its
[rate-limit documentation](https://discord.com/developers/docs/topics/rate-limits)
requires respecting server limits. Edits are sequential and use discord.py's
rate-limit waits/retries. Playback shows achieved FPS alongside the requested
target. After a slow edit, pacing backs off toward one update per second and
waits before the next update; the requested target is an upper bound. A slower
requested rate remains slower. Slow edits extend the timeline; there are no catch-up
bursts, skipped cached frames, or application retry loops. An exposed HTTP error,
rate-limit exception, or a 120-second edit timeout terminates playback and
releases its slot. Completion reports target and achieved FPS. On deletion,
permission loss, or API failure the last visible frame may remain without a final
status; cancellation status is best-effort with a three-second deadline. Updates
use bot authentication, so they do not depend on the initial interaction token
remaining valid. A bot restart ends playback; there is no persistent worker.
Slow edits log `badapple_slow_edit` at most once every 30 seconds, including
edit duration and the reduced pace. Edit duration includes library rate-limit
waits, network latency and event-loop delays; this log alone does not identify
which caused the delay. Adaptive pacing cannot guarantee stall-free live playback.

Runtime cache loading runs off the event loop and retains one bounded copy:
at most 4 million art characters (about 8 MB of Unicode storage), 7,200 frames,
and 16 MB of compressed/decompressed cache data. Inputs are limited to one hour.
Oversized caches are rejected with instructions to reduce resolution or sampling
FPS. No frame storage uses PostgreSQL or Redis. Art is limited to 1,800 characters
to leave room inside Discord's 2,000-character message limit.

Run the synthetic-media, mocked-playback, and command-registration tests with:

```powershell
python -m pytest tests/test_badapple.py tests/test_help_catalog.py -q
```

FFmpeg integration tests use PATH, or `TEST_FFMPEG` and `TEST_FFPROBE` executable
paths, and are explicitly skipped if the tools are absent. Fixtures are generated
in pytest's temporary directory. On machines with an inaccessible default temp
directory, create `artifacts/badapple` and add
`--basetemp artifacts/badapple/pytest-run` (pytest replaces that test-only directory).
Before declaring live playback verified, preprocess your complete source and test
beginning-to-end playback, achieved FPS, stop permissions, and message deletion in
a real Discord test channel. Mocked tests do not establish smooth live playback.

## Requirements

- Python 3.12
- PostgreSQL
- Redis
- A Discord bot token
- A Gemini API key for AI chat and voice
- A Klipy API key for reaction GIFs

## Quick Start

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

Server managers can run `/serversetup` for guided configuration and `/serverdashboard` for
remaining messages and server activity. Both also work with `uwu`.

## Main Features

- Social reactions with GIFs, counters, and response buttons
- Stable daily IQ, smartest, dumbest, and clown results
- Profiles combining Discord, social, mood, relationship, and marriage data
- Ship, fortune, rate, bestie score, most likely, and 8-ball commands
- Reddit-style mock posts: `uwu reddit <post>` or `/reddit post:<text>`.
  Uses the server name, requesting member's username/avatar and a short Gemini comment
  from Meyaya. `uwu reddit <post> | <comment>` (or the slash `comment` field) bypasses AI.
  User, channel and role mentions in posts/comments render as readable cached names,
  not raw Discord markup. Unresolved references use neutral unknown labels.
  If AI is unavailable, the card is sent without a comment. `rate` is entirely local.
- Caught CCTV card: `uwu caught [@member]` or `/caught`. Defaults to yourself.
  Three illustrated locations with matching harmless incidents, avatar, timestamp
  and evidence/status labels. Supersampled local PNG rendering, no Gemini requests,
  shared avatar cache/worker, bounded queue and a 10-second member cooldown.
- Avatar sliding puzzle: `uwu scramble [@member]` or `/scramble`. Defaults to yourself.
  Click highlighted numbered tiles to move them into the blank; match the reference
  picture and the numbered order. Only the requester controls the board. Includes
  a move counter, a native Discord relative countdown, full-picture victory/reveal, and a
  fixed five-minute deadline. One active puzzle per user, at most 20 globally;
  sessions are temporary and end on restart. Expired/restarted game buttons explain
  that a fresh run is needed, rather than silently ignoring the interaction.
  No Gemini calls. Implementation:
  `bot/services/scramble.py` and `bot/views/scramble.py`.
- Duck animation: `uwu duck [@member]` or `/duck`. Defaults to the requester;
  overlays the member's avatar and name on the bundled duck-ejection GIF without AI.
  Rendering uses the shared image worker, all 94 source frames preserving the full
  timeline, a bounded queue and a 10-second member cooldown. Template and source note:
  `bot/assets/duck/`; renderer: `bot/services/duck_card.py`.
- Reddit and duck share ship's bounded CDN avatar downloader/cache. Failed downloads
  retry on the next call and emit `party_avatar_unavailable` without leaking URLs.
  All prefix, hybrid and standalone slash commands use the shared loading indicator
  after 1 second if still running; fast results skip it. Cleanup follows delivery.
  AI conversation listeners do not display this indicator.
- Consent-based marriage, vows, anniversaries, and confirmed divorce
- Anonymous multiplayer games judged by Gemini
- Local single-player games: `/escape`, `/detective`, and `/personalitytest`
  (also available with `uwu`). Escape has three five-scene adventures, branching
  routes, inventory-gated choices and an eight-minute in-game resource. Detective
  has four cases with four selectable evidence leads, shuffled fictional suspects,
  and an accusation stage after at least two leads. Personality Test draws six
  of twelve questions, shuffles answers, and shows the three-trait mix including
  blended results on ties. Games have owner-only controls, an End game button,
  and replay in the same message. Idle games and replay buttons expire after three
  minutes. One active solo run per user/server, up to 64 active runs and 128 retained
  views per process. Sessions end on restart; no database or Gemini calls.
  Content: `bot/data/solo_games.py`; rules: `bot/services/solo_games.py`;
  Discord controls: `bot/cogs/solo_games.py`.
- Entertainment-only court cases with registered witnesses, fair follow-ups, and explained verdicts
- Google-grounded fact checks for one message or a selected argument range
- Reply-aware Gemini chat with personal memory and server lore
  - Reply context reuses Discord's message cache before fetching over HTTP. Mention-
    prefixed commands and explicit courtesy closings exit before reply resolution,
    avoiding unnecessary network calls and duplicate command-context parsing.
  - Pure closings such as "thanks" or "goodnight" do not trigger another AI reply.
    Questions, corrections and attachments are preserved. Ambiguous acknowledgements
    such as "okay" still reach the model when they might answer an offer/question.
    Chat can return `NO_REPLY` without sending a message or executing hidden directives.
  - Recall answers use only the available facts, history and quoted results. Missing
    context prompts an honest request for a reminder, not an invented memory or an
    unsupported outage claim. Actual AI-generation failures receive a separate
    service-unavailable message with an error ID.
  - Conversation context separates the speaker, referenced members, quoted author,
    command invoker, and card target by Discord ID. Explicit mentions and bounded
    cached-name matches help resolve references; duplicate or unknown names prompt
    clarification rather than an invented identity. No member-list API fetch is needed.
  - Newer conversational corrections supersede earlier interpretations of the topic
    or intended person. Speaker-labelled prompts remain in short-term history, so
    corrections carry into later turns. They do not change verified family identity,
    historical card results, or grant permission to edit permanent memories.
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
