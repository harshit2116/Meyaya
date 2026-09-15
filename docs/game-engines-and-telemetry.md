# Game engines and diagnostics

The successful lifecycle is `LOBBY -> COLLECTING -> LOCKED -> JUDGING -> RESULTS -> CLOSED`.
`bot/services/game_engine.py` validates allowed transitions. The social engine serves Showdown,
Excuse, and Survive using distinct scenarios and judging rubrics. Court uses the same transition
contract with one optional `JUDGING -> CLARIFYING -> LOCKED -> JUDGING` round.

Python owns participant eligibility, deadlines, evidence collection, phase changes, result
validation and execution. The model receives a submission snapshot and produces only a ranking,
verdict or clarification proposal. A clarification is accepted only once and only in JUDGING.

- Failed judging returns to LOCKED. Answers cannot be changed before retrying.
- Cancellation and expiry close the game. Stale timeout callbacks cannot close a newer phase.
- Completed results enter RESULTS before publication and CLOSED after the publication attempt.
  A Discord delivery failure does not erase the accepted result.
- Social operations use per-session locks. Court reads acquire database row locks until commit
  and callbacks retain their existing per-case process lock.
- Social sessions remain in memory and do not survive a process restart. Court data persists,
  but restoring interactive views or recovering an interrupted JUDGING phase after restart is
  not implemented. Restart recovery is separate from the transition contract.
- Older Court PENDING, COMPLETED and DECLINED values are normalized on read. No new database
  columns or migrations are needed for these phase names.

## Logs

Structured events are written to the console and `logs/telemetry.jsonl`, rotated at 5 MB with
three backups. This directory is excluded from Git. If file logging is unavailable, console
logging continues.

- `llm_request`: unique request ID, requested and returned model, provider, operation, feature,
  guild/channel IDs, elapsed milliseconds, status, token counts, failed attempt count, and fallback reason.
- `llm_attempt_failed`: request ID, reason and attempt number where available.
- `llm_fallback`: invalid JSON, invalid game judgments or unavailable judgments at the caller.
- `llm_route`: selected fast, balanced, reasoning, or grounded tier and concrete model.
- `llm_route_fallback`: specialized model failure followed by one balanced-model retry.
- `game_transition`: previous and next phase, feature, guild/channel and session/case ID.
- `voice_connect`, `voice_reconnect`, `voice_usage`: connection latency/status, reconnect reason,
  and usage as reported by the streaming API. Voice usage events are reported snapshots; do not
  assume they are increments or sum them without understanding provider semantics.

Unknown token counts are null, not zero. Request latency includes retries and backoff. A successful
request can still show failed attempts when a retry or grounding endpoint fallback recovered it.
Structured telemetry contains no prompts, answers, case evidence, API keys or webhook URLs.

Example PowerShell inspection:

```powershell
Get-Content logs/telemetry.jsonl -Tail 30
Get-Content logs/telemetry.jsonl | ConvertFrom-Json | Where-Object status -eq 'unavailable'
```
