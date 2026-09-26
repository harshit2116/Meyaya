# Your Meyaya nickname

Use these commands in a server. They affect only your own Meyaya nickname in that server, not your Discord nickname or relationship scores.

- `uwu nickname` or `uwu nickname status`: show your nickname and preference.
- `uwu nickname keep`: keep the current nickname.
- `uwu nickname refresh` (or `reroll`): request a different nickname based on your current display name, even if you are new. This also enables nicknames again.
- `uwu nickname reject`: remove the nickname and disable automatic assignment.
- `uwu nickname on`: re-enable automatic assignment as Meyaya gets to know you.

These are also available through `/nickname`. Preferences persist in PostgreSQL. There is a 15-second command cooldown. Run `alembic upgrade head` before restarting after this update.
