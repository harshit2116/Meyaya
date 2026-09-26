# Chat access and owner dashboard

Send `uwu owner` (or this server's configured prefix) to receive a private dashboard login link by DM. Only Discord user 715925710849572904 can use it. It is hidden from help and has no slash-command version. Links expire in 60 seconds, are usable once, and do not contain the permanent dashboard token. Enable DMs from the bot. Keep links private.

Local dashboard: http://127.0.0.1:8080 while Meyaya runs. For remote hosting, set `DASHBOARD_PUBLIC_URL=https://your-dashboard-host` behind a trusted HTTPS proxy. The command does not open ports or set up hosting. A localhost link only works on the bot computer (or through your tunnel).

## Server-specific blacklist

- `uwu chatblacklist @member block reason` restricts access.
- `uwu chatblacklist @member unblock reason` restores access.
- `uwu chatblacklist @member status` checks access.
- These commands require Manage Server. Slash commands are also available for blacklist management.
- Owner dashboard: **Chat blacklist** shows the latest 200 member decisions and supports blocking/restoring access by server and user ID.

Automatic restrictions use conservative text rules for direct sexual solicitations in mentions/replies, roleplay, and typed voice requests. Ordinary profanity, unrelated channel messages, quoted lines, and common reporting/educational wording do not trigger those rules. This is deliberately not a complete NSFW classifier; obfuscation, other languages, images, and spoken audio are not automatically classified. Do not treat a rule match as proof of misconduct. Review mistakes and restore access.

Restrictions apply only in the originating server and persist in PostgreSQL. Blocked members receive no normal chat/command response; their received microphone frames are dropped. Other members and servers remain unaffected. Decisions retain the reason category, latest actor/source, and date, not the offending message. An already-started voice response cannot reliably be attributed and recalled.

The restriction table must be migrated before startup (`python -m alembic upgrade head`). The bot does not start if it cannot load restrictions, rather than silently letting blocked users through. Use the owner dashboard for recovery if you block yourself.
