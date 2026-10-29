# Meyaya

[![CI](https://github.com/harshit2116/Meyaya/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/harshit2116/Meyaya/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white&labelColor=302D41)](https://www.python.org/)
[![discord.py 2.7.1+](https://img.shields.io/badge/discord.py-2.7.1%2B-5865F2?logo=discord&logoColor=white&labelColor=302D41)](https://github.com/Rapptz/discord.py)
[![Components V2](https://img.shields.io/badge/Components-V2-B69CFF?logo=discord&logoColor=white&labelColor=302D41)](https://docs.discord.com/developers/components/reference)

[![Google Gemini](https://img.shields.io/badge/AI-Google_Gemini-8E75B2?logo=googlegemini&logoColor=white&labelColor=302D41)](https://ai.google.dev/)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL-4169E1?logo=postgresql&logoColor=white&labelColor=302D41)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Cache-Redis-DC382D?logo=redis&logoColor=white&labelColor=302D41)](https://redis.io/)
[![Discord support](https://img.shields.io/badge/Discord-Support-F48FB1?logo=discord&logoColor=white&labelColor=302D41)](https://discord.gg/e9bK5ZbUZS)

[![GitHub stars](https://img.shields.io/github/stars/harshit2116/Meyaya?color=E8BD70&logo=github&labelColor=302D41)](https://github.com/harshit2116/Meyaya/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/harshit2116/Meyaya?color=90CAF9&logo=github&labelColor=302D41)](https://github.com/harshit2116/Meyaya/forks)
[![Open issues](https://img.shields.io/github/issues/harshit2116/Meyaya?color=CE93D8&logo=github&labelColor=302D41)](https://github.com/harshit2116/Meyaya/issues)
[![Last commit](https://img.shields.io/github/last-commit/harshit2116/Meyaya/main?color=A5D6A7&logo=git&logoColor=white&labelColor=302D41)](https://github.com/harshit2116/Meyaya/commits/main)

Meyaya is a Discord bot for chat, games, profiles, and voice conversations.

## What she does

- AI chat with reply context, saved memories, nicknames, and changing moods.
- Fantasy characters, guardians, weapons, dungeons, and Meyaya/Veyra boss fights.
- Social reactions, daily picks, compatibility scores, and consent-based marriage.
- Profile cards, avatar puzzles, solo adventures, and multiplayer games.
- Live voice conversations through Gemini.
- Server setup, moderation, and an optional administration dashboard.

The interface uses Discord Components V2 for cards, menus, and interactive games.

## Using Meyaya

Start with `/help` for commands and examples. Most commands also work with the
`uwu` prefix or a mention, such as `uwu hug @member` or `@Meyaya hug @member`.
Mention her without a command to chat.

Try `/awaken`, `/fantasyprofile`, `/guardian`, `/profilecheck`, or `/bossfight`.
Server managers can use `/serversetup` and change the prefix with `/prefix`.

## Voting

Use `/vote`, `uwu vote`, or `@Meyaya vote` for the top.gg link and your reward
balance. After voting, press **Check vote** or run `/vote` again to verify and
claim the reward. Each confirmed vote grants **20 personal AI text replies for 12 hours
from the vote**. These are available across servers after a server uses its shared
allowance. Unused replies expire; weekend votes still grant 20 replies. Direct
chat and requested AI text commands can use them. Automatic replies, combined
group replies, and voice do not spend personal credits. Disabled chat, blacklists,
channel restrictions, and AI resource limits still apply.

When a new vote reward is claimed, Meyaya attempts one thank-you DM with an
Elysia GIF from Klipy, the reward amount, and its expiry time. Rechecking an
already claimed vote does not send another DM. Closed DMs or delivery failures
leave the saved reward available and are noted in the claim response.

For deployment:

1. Apply `python -m alembic upgrade head` before starting the updated bot.
2. Get a **v1 project API token** from Meyaya's top.gg **Integrations & API**
   settings. Select read access only: `project.votes.read` and
   `project.information.read`. No write permissions are used.
3. Store it privately as `TOPGG_API_TOKEN` in the deployment environment.
   `TOPGG_PROJECT_ID=891928922138710016` identifies Meyaya's existing listing;
   verification rejects a token for another project. Set `TOPGG_ENABLED=true`
   and restart Meyaya. No webhook, domain, tunnel, or inbound HTTP listener is needed.
4. Cast a real vote and use `/vote` or **Check vote**. Confirm 20 bonus replies,
   then repeat the check to verify it does not refill the balance. Slash commands
   and button responses show your balance privately; prefix commands reply publicly.

All Top.gg requests are authenticated HTTPS GETs. Verification first confirms the
token's listing, then checks the requesting member's Discord ID. Votes are
deduplicated using the original vote timestamp and member ID, so rechecks never
reset the reward or extend its 12-hour lifetime. Requests have bounded timeouts,
a short cache, a local rate cap, and provider rate-limit backoff. Provider failures
leave saved rewards intact. Failed or silent AI generations refund their reserved
reply. Shared quota resets leave personal rewards unchanged.

Rewards default to disabled until configured. `/vote` still provides the voting
link and clearly states when rewards are inactive. Vote receipts contain only
the deterministic receipt ID, Discord user ID, timestamps, and allowance counters.
