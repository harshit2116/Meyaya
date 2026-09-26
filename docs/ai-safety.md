# Chat access and resource protection

The original server chat allowance remains unchanged: 40 messages per UTC day by default, with the configured main-server exemption. There is no additional member daily quota, server attempt quota, or global daily attempt quota.

Members have a 5-second cooldown between user-attributed text operations (`AI_USER_COOLDOWN_SECONDS=5`). Retries and fallback are part of that same operation, not new cooldown events. Automated tasks without a member do not consume another member's cooldown.

Resource protections remain separate from message quotas:

- `AI_MAX_CONCURRENT=2`: maximum simultaneous text operations globally. No separate per-server concurrency limit.
- `AI_ENABLED=true`: set false and restart to pause text generation and new voice sessions.
- `AI_MAX_INPUT_CHARS=32000` and `AI_MAX_OUTPUT_TOKENS=2048`: bound request size.
- `VOICE_MAX_SESSIONS=1` and `VOICE_SESSION_MINUTES=10`: bound simultaneous voice sessions and session length. No daily voice-minute allowance.
- Images use one render worker, at most four queued/running jobs, a ten-second queue timeout, and bounded avatar bytes/pixels.

Cooldowns and concurrency are process-local. Run one bot process/replica. These protections are not an exact monetary billing cap or a guarantee of 512 MiB operation; use provider billing alerts and test deployment load.

Text fallback tries one distinct alternate model. `GEMINI_FALLBACK_MODEL` overrides the routing default. If both providers fail, the bot returns a normal unavailable response without exposing upstream exceptions. Grounded requests still require source-backed results.

The dashboard shows the member cooldown and active text/voice operations. The old `ai_budget` migration/table is retained for migration compatibility but is no longer read or updated by the runtime.

Refresh your own server-local Meyaya nickname with `uwu nickname refresh` or `/nickname action:refresh`. `reroll` is an alias. Relationship values remain unchanged; the nickname command keeps its existing 15-second cooldown.
