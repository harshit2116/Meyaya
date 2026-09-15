# Owner operations

The token-protected web dashboard shows servers, daily and seven-day usage, configuration and
retained bot-request logs. The old servers and status Discord commands have been removed.

All servers receive 40 AI messages per UTC day. Chat, roleplay, member entertainment and automatic replies share this
allowance. Server 1479860234183905443 is exempt. Non-chat commands, game judging, moderation,
fact checking and voice remain outside this allowance. It is not a full API-spending cap.
PostgreSQL reserves slots atomically; failures and NO_REPLY outputs return their slots. Successful
generation consumes a slot even if Discord delivery subsequently fails. A crash during generation
may retain a reserved slot until the daily reset. If the usage database is unavailable, chat stops
rather than bypassing the cap. Main-server usage is still counted for the dashboard.

## Web dashboard

### Per-server request review

Request logging is enabled by default for all servers, independently of whether the web listener
is enabled. Each server card has a **View requests** button. Owner-token authentication protects
both the viewer and API. Browse 50 requests at a time, refresh, or load older requests. Records
contain the supplied text, author name and ID, channel ID, capture time, and a Discord message link.
Slash commands record explicit option values and link to the channel, because there is no original
user message to jump to. Records are submissions, not evidence of successful execution or violations.

Direct mentions/replies and written commands are recorded; slash commands are recorded once per
interaction. DMs, ordinary channel conversations, automatic-reply candidates, buttons, modal forms,
voice audio, attachments, resolved context-menu content, model system prompts and prior conversation
history are excluded. No history is backfilled. Very long requests are visibly truncated to 8000
characters. HTML and scripts in requests display as plain text, never execute in the dashboard.

Records expire after seven days. Expired records are never returned by the API; hourly maintenance
deletes them while the bot is running and retries after database outages. If the database is down,
some requests may be missing. Existing database backups have their own retention and must be
managed separately. Include this actual scope and retention in the usage agreement you publish.
There is no server opt-in switch. Locking the dashboard clears loaded requests from the page.

Set these values in private `.env` or host configuration:

```text
DASHBOARD_ENABLED=true
DASHBOARD_HOST=127.0.0.1
DASHBOARD_PORT=8080
DASHBOARD_TOKEN=<a long randomly generated secret>
```

Generate a token with `python -c "import secrets; print(secrets.token_urlsafe(32))"` and keep it
private. Restart Meyaya and open http://127.0.0.1:8080. The token grants owner access to all server
settings. It is held only in the browser tab's memory, never placed in URLs or browser storage.
Use Lock or reload to clear it. Change the configured token and restart to revoke it.

The dashboard edits prefix, automatic replies and daily chat limits (0-10000). Main-server exemption
always wins. Changes save to PostgreSQL and update the live bot cache immediately. Current state
refreshes on demand, avoiding polling while you are editing. Usage history is aggregate counts only.

For remote deployment keep it private through an SSH tunnel, or use a trusted HTTPS reverse proxy.
Do not expose the bearer-token login over plain HTTP. The default localhost binding deliberately
does not expose an administrative port to the internet. Docker deployments need an explicit port
mapping and DASHBOARD_HOST=0.0.0.0 inside the container, with the host port bound to localhost.
Keep the dashboard and Discord bot in the same process when deploying to Azure, since the dashboard
reads Meyaya's live in-memory state. Route dashboard traffic securely to that process.

## Slash commands

Startup now always synchronizes globally, even when GUILD_ID is set for development. It also
updates the development server copy. After restarting, the application owner can use
`uwu synccommands` to repeat the sync when slash commands themselves are missing.
Check that the bot invitation includes `applications.commands`, Discord's integration permissions
allow the command/channel, and the bot can send messages there. Refresh Discord's command menu.
Global propagation and permission settings cannot be verified without the live Discord application.
