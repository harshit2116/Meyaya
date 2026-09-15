# Moderation controls

The new deterministic rules are enabled by default per server. Members with Manage Server can
change them with `/moderation feature:probation enabled:false` (or `cross_spam` / `anti_invite`).
All three exempt bots and members with Manage Server. Moderation requires Message Content intent
and Manage Messages. Deleted messages get a short explanatory notice, rate-limited per member.
These rules delete the offending message; they do not automatically ban or timeout anyone.

- Probation is the first **72 hours since joining this server**, not account age. Text chat is
  allowed; messages containing links or attachments are deleted. No role assignment or timer job
  is required, so expiry works after restarts too. Rejoining starts a new probation period.
- Cross-channel spam means the same normalized text (at least 12 characters) or identical image
  bytes from the same member in **3 distinct channels within 60 seconds**. The third and later
  matching messages are removed. The first two are not retroactively deleted. Renaming a file
  does not bypass its hash; edited/re-encoded images can. At most 3 images of up to 8 MB per message
  are checked. Larger images and download failures are skipped. The short detection window is
  process-local and resets on a restart; settings persist in PostgreSQL.
- External Discord invite links are resolved against Discord. Invites to the current server are
  allowed for members past probation. Invalid/unresolvable links are not treated as proof of an
  external invite. URL shorteners and obfuscated links are not expanded.

## Lockdowns

- `/lockdown [channel]` and `/unlock [channel]`: Manage Channels required.
- `/raidlockdown` and `/raidunlock`: Manage Server required.

The bot needs Manage Roles to edit permission overwrites. A raid covers every server text channel
and newly created text channels while raid mode is active. It blocks ordinary sending, thread
messages/creation, and adding reactions through the saved channel overwrites. Discord administrators
always bypass these restrictions. This does not disable external webhooks or forum channels.

Snapshots are saved **before** permission edits and survive restarts. Explicit allow overwrites are
also handled, and the bot retains sending permissions. Single and raid locks overlap independently;
raid unlock keeps a separate single-channel lock. Unlock restores only fields changed by Meyaya,
preserves unrelated changes, and reports conflicting manual edits. Partial failures retain their
snapshots: correct bot permissions and retry the matching lock/unlock command. Do not delete the
lock tables or reset the database while locks are active. Run exactly one bot process per token.

## Argument timeline

Moderators with Manage Messages can reply to a starting message with `uwu argumenttimeline`, or use
`/argumenttimeline start:<message link> ending:<optional message link>`. The selected range must be
in the current channel and fit the existing 60-message/18,000-character bounds. The timeline uses
the model only for a chronological explanation and links solely to supplied evidence. It is not
a fact check or an automatic guilt/punishment decision. `/checkclaim` remains for single claims.

Removed commands: factcheck, forget, forgetall, resolvememory, voicediag, servers and status.
Stored memories and the web dashboard remain. synccommands is excluded from help and restricted
to Discord ID 715925710849572904 on both written and slash routes. Restart and sync to remove old
slash registrations; Discord may cache the old menu temporarily.
