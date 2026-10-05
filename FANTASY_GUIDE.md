# Meyaya - fantasy awakenings and rebirth

For consent-based `/versus` duels using these saved identities, see
[FANTASY_DUELS.md](FANTASY_DUELS.md). Migration `0030_fantasy_duels` adds result
history only; combat never changes stored HP/MP, XP or awakening data.

`/guardian [member]` now opens the awakening's soul-bound companion, not a daily
draw. The Details tab names the companion; `/guardianbattle member:@member`
starts manual guardian combat. See [GUARDIANS.md](GUARDIANS.md).

## Commands and experience

Patron configuration and copy live in `bot/data/fantasy_alignment.py`. The existing
`fantasy_profiles.alignment` field stores `meyaya`, `veyra` or `unclaimed`; no new
alignment migration or server setting is needed. Old moral-alignment strings are
treated as unclaimed without rewriting rows until the owner chooses. Only the
alignment, patron title and character comment change when an oath is sealed.
Classes, weapon IDs, affinity, saved stat rolls and awakening timestamp stay intact.
`choose_alignment` uses a short row-locked transaction with timestamp validation;
the art and final avatar are uploaded only after commit. Rebirth clears alignment.

- `/awaken`, `uwu awaken`: a first-use confirmation with **Awaken** and **Not yet**.
  Confirming commits the identity before the visual reveal begins. The sequence is
  animated affinity sigil → bound weapon → alignment choice → final identity.
  Each discovery waits for the owner's button press; earlier discoveries remain
  visible. The weapon step includes a locally illustrated, looping acquisition
  GIF matching its saved weapon family, affinity and rarity. It uses the bounded
  image worker, is cached for this reveal, and falls back to text if rendering or
  uploading fails. No API calls or rerolls are involved.
  **Previous discovery** goes back. The third step shows the supplied Origin vs
  Erasure artwork and two choices: **Meyaya - Bloom of Origin** or **Veyra - Enemy
  of All**. The owner must choose before the complete class/stats/abilities reveal.
  The oath is saved before rendering and locked until rebirth. Discord has no
  pink button style: Meyaya uses a standard primary button with a flower; Veyra
  uses danger/red. There are no timed stage changes.
  The reveal expires after five minutes without a button interaction; the saved
  identity is never lost and the owner's `/fantasyprofile` resumes an unclaimed
  reveal anytime, even after a restart. Looking up another member never lets
  the viewer choose that member's patron.
  Reusing the command offers **View Character**, never another roll.
- `/rebirth`, `uwu rebirth`: self-only, 90-second confirmation to replace the
  current global build. Confirming immediately rolls and saves a fresh level-1
  identity, weapon, stats and guardian, then opens the paced reveal. There is no
  undo. The rebirth count survives rerolls; the 24-hour cooldown is stored in
  PostgreSQL and survives restarts/server changes. Cancelling, timing out or a
  failed transaction costs nothing. Active battles/awakening views block rebirth.
  Stale confirmations are rejected under a row lock. Existing duel history remains.
  A new life clears the oath and lets the owner choose either patron again.
- `/fantasyprofile [member]`, `uwu fantasyprofile [member]`: read the caller's or
  another member's saved character. Looking someone up never awakens them.
  Prefix-only lore names `Veyra` or `Veryra` open Veyra's image-only authored card;
  `Meyaya` opens Meyaya's card. Names are case-insensitive. To view a real member
  named Veyra, mention that member instead. These lore cards never create player
  rows or start a battle. Slash commands retain the ordinary member picker.
- The final public profile has Character, Weapon, Abilities and Details tabs.
  Only its initiating viewer can operate those buttons. Anyone else can open their
  own public profile view. Views expire after 180 seconds and disable their controls.

Both combat modes use these saved identities and skills; there are still no XP
awards, quests, inventory purchases or levelling rewards. Rebirth does not grant
extra stat points or rare-drop bonuses. Weapons now have 30 recognisable native
designs (three per family): their catalogue suffix determines the silhouette,
saved weapon ID determines engraving, and affinity/rarity colour the inlays and
gemstones. The same weapon always looks the same, including after restarts.

Deployment: apply migration `0031_fantasy_rebirth` with `alembic upgrade head`
using the normal migration environment before restarting/syncing `/rebirth`.
The migration adds `rebirth_count` (existing profiles start at zero) and nullable
`last_rebirth_at`. It does not reroll existing identities. No production migration
is automatically applied by this implementation.

### Owner-only reset

Only Ayaya (`715925710849572904`), matching Meyaya's existing private-owner check,
can run `uwu fantasyreset @member confirm` (a raw Discord user ID also works).
This is a hidden **prefix-only** command, not a slash command. Mention prefixes
and other server prefixes are rejected. It can also be used in DMs with `uwu`.
Without the final `confirm` argument it only shows the deletion warning.
There is no command cooldown or rebirth waiting period for this owner-only reset.
Because it deletes the complete row, its rebirth count and player cooldown also
reset; it is an administrative override, not an extra player reroll path.

The reset transaction deletes only the selected user's global fantasy row.
It closes that user's pending awakening and existing profile interfaces in this
bot process, waiting for a local in-flight confirmation first. The next `/awaken`
can create a new identity. There is no reset-all option. Old identity values are
not retained by this command; recovering them requires a database backup.

## Architecture and file map

| File | Responsibility |
| --- | --- |
| `bot/data/fantasy.py` | Authored classes, subclasses, weapon families, affinities, themes, rarity and balance constants |
| `bot/models/fantasy_profile.py` | Global SQLAlchemy row, actual generated values and original base-stat snapshot |
| `bot/repositories/fantasy_profiles.py` | Lookup and PostgreSQL atomic insert-or-return-existing |
| `bot/services/fantasy_generation.py` | Controlled first-time local generation and HP/MP formula |
| `bot/services/fantasy_profile.py` | Short database transaction; no rendering/network work inside it |
| `bot/services/fantasy_render.py` | Local 900 × 1000 PNG character crest and 560 × 280 ritual GIF |
| `bot/cogs/fantasy.py` | Commands, reveal delivery, bounded work and graceful fallbacks |
| `bot/views/fantasy.py` | Owned confirmation, cancellation, timeout and read-only profile tabs |
| `alembic/versions/0029_fantasy_profiles.py` | New migration following `0028_dashboard_usage` |
| `test_fantasy_awaken.py` | Generation, ORM persistence, SQL, migration, UI and failure regressions |

Integration changes: `alembic/env.py` imports the model; `bot/app.py` loads the cog;
`bot/data/help_catalog.py` registers both commands under Fantasy / Profile;
`pyproject.toml` includes the tracked regression file; `README.md` links this guide.

## Exact first-awakening rules

1. Uniform selection among 21 classes, then uniform selection among that class's
   three compatible subclasses. Pools and each class's five stat weights and
   HP/MP modifiers live in `bot/data/fantasy.py`.
2. Each class has three supported affinities: first/second/third weights **6:3:1**
   (60%, 30%, 10%). There are 14 reusable affinity themes.
3. Every character starts with **75 total stat points**. STR, DEX, INT, VIT and LCK
   each begin at 6. Allocate the remaining 45 points individually using the class's
   stat weights, excluding a stat once it reaches 24. Thus every initial stat is
   between 6 and 24, independent of weapon rarity.
4. **Max HP = 60 + 6 × VIT + class HP modifier.**
   **Max MP = 30 + 5 × INT + class MP modifier.** Initial HP/MP are full.
5. Level 1; XP 0. Original base stats are saved separately from the live stat fields.
6. Choose a compatible weapon family uniformly from the class's allowed families.
   Combine an affinity prefix and a curated family suffix; save name, family, type,
   rarity, lore and resonance trait.
7. Rarity chances: **Common 40%, Uncommon 30%, Rare 18%, Epic 9%, Legendary 2.7%,
   Mythic 0.3%**. Rarity adds presentation/flavour, not starter stat superiority.
8. Passive and signature names come from the class; stored descriptions incorporate
   subclass training and affinity. Choose an authored title pattern, alignment and
   small Meyaya reaction locally. Save the UTC awakening timestamp and version 1.

Production randomness uses `SystemRandom`, not a seed derived from the user ID.
Tests can supply a seeded generator, but the runtime never reconstructs characters
from a seed. Balance changes apply to future awakenings only; existing stored
values, skill descriptions, title and weapon do not regenerate.

## Permanence, transactions and concurrency

`fantasy_profiles.user_id` is the sole primary key, with no guild dependency or
foreign key requiring another member table to be populated. Original identity
follows the Discord account. Future per-server progression belongs in another table.

The service starts a transaction, checks for an existing row, and returns it
unchanged if present. If absent, it generates the complete snapshot and executes
PostgreSQL `INSERT … ON CONFLICT (user_id) DO NOTHING RETURNING …`.
Only one competing insertion wins, including separate processes. Losing callers
read the winning row in a subsequent READ COMMITTED statement. Initial awakening
never uses `DO UPDATE` or seed regeneration. Confirmed rebirth is a separate
row-locked transaction: it checks the original awakening timestamp and stored
cooldown again before replacing the snapshot and incrementing its count.
The service exits/commits its
transaction before a caller receives the character or begins its reveal.

Use PostgreSQL's normal **READ COMMITTED** isolation, as the existing application
does. A custom stricter isolation mode may produce a serialization failure;
the user can safely retry rather than receive a reroll.

Generation or insertion failure rolls back. Rendering or Discord delivery failure
after commit leaves the identity intact. `/fantasyprofile` and repeated `/awaken`
recover the same row. Backups of PostgreSQL remain essential: an actual deleted
row/database cannot be recovered from the local random generator.

## Presentation and resource limits

The portrait PNG uses the current Discord avatar within three ornate circular
crest rings, a class seal, rarity tint, affinity glyph, subtle gradient,
constellation marks and Meyaya flower motifs. Its primary hierarchy is name/title,
avatar, class/subclass, affinity and HP/MP. The embed holds stats, weapon and arts;
tabs expose skill descriptions, weapon lore, alignment and original potential.

The initial sigil animation has 24 restrained frames and lasts about two seconds;
it is not a continuously animated final card. A static final PNG is clearer on
mobile, cheap to render and easy to share. Text is fitted/ellipsized rather than
overflowing. Failed/corrupt avatar downloads use an initial crest, not a broken card.

- Existing single shared Pillow worker; no new executor or image preload.
- Feature render admission: at most three running/waiting callers, one admitted
  job at a time. Shared worker admission also remains bounded.
- Existing shared HTTP session and bounded profile-asset cache for avatar fetching.
- Portrait inputs: at most 6 MiB and 4 million pixels; final PNG cap 4 MiB.
- At most 64 live interfaces; timeout/unload/failure releases them.
- `/awaken`: 15-second per-user cooldown; `/fantasyprofile`: 8 seconds.
- Database operations have a 10-second deadline.
- Existing 0.5-second delayed loading utility is used for commands and confirmation;
  cleanup occurs after final delivery or on failure/cancellation.
- No finished-profile image cache: a future progression update cannot be hidden by
  a stale cached card. Reopened views fetch the saved row and current avatar.
- No Gemini requests and no generated artwork. Reveal summaries use the existing
  bounded command-output cache so chat replies can identify the actual result.

## Example final interface

The exact values below are an illustrative local test result, not a promised roll.

```text
✦ SOUL INTERFACE
Ayaya · Bearer of the Hollow Crown
◇ Void · Level 1

[portrait card: Ayaya / VOIDBLADE / Astral Duelist]
[Void affinity · HP 154/154 · MP 115/115]

Potential: STR / DEX / INT / VIT / LCK - stored initial values
Bound weapon: Hollow Secrets · Common · Twin Daggers
Awakened arts: Starless Step / Moon Sever

Meyaya ✦ “Your soul came with its own dramatic entrance. Naturally.”

[✦ Character] [Weapon] [Abilities] [Details]
```

## Enable, verify and troubleshoot

Use the correct Python virtual environment and existing database configuration:

```powershell
alembic upgrade head
python -m compileall -q bot
python -m pytest -q
git diff --check
```

Apply/test the migration on an isolated database before production. No migration
is automatically applied by these new commands. Migration downgrade drops the
identity table and loses these characters: do not downgrade casually.

The standalone test module works offline using actual ORM persistence against
SQLite plus PostgreSQL SQL compilation, offline migration checks, generation and
mocked Discord delivery. These checks do not prove PostgreSQL's cross-process
locking. An optional PostgreSQL concurrency test uses **only** an explicitly set
`MEYAYA_FANTASY_TEST_DATABASE_URL`, pointing to a disposable empty database. It
refuses an existing `fantasy_profiles` table, creates that table, races 12 sessions,
and drops its own table afterwards. Never point this test at the bot's normal DB.

If the register is unavailable, check database connectivity/migration state using
the returned error ID. Rendering/upload failures should still show a clean text
interface. A component delivery error advises checking `/fantasyprofile`; it
does not claim that an unsuccessful/ambiguous transaction definitely saved a row.

Final live checks require Discord: confirm/cancel, outsider button use, timeout,
repeated awakening, another member lookup, mobile appearance, attachment delivery
and the deployed database migration. No deployment or push is part of this change.
