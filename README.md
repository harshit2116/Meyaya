# Meyaya

Meyaya is a Discord character bot built with Python. She supports social reactions, daily fun,
profiles, marriage, multiplayer games, court cases, Gemini chat and memory, English-only monitoring,
and live voice conversations.

Meyaya uses a fixed Do Not Disturb presence with the custom status
“The Girl at the end of every story”. Edit `bot/cogs/presence.py` to change it.
The `Meyaya` emoji is sent best-effort; Discord may omit custom-status emoji for
bot accounts. The former 15-minute presence rotation is disabled.

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
