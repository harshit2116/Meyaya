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
