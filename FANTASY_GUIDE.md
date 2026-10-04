# Meyaya — permanent fantasy awakenings

## Commands and experience

- `/awaken`, `uwu awaken`: a first-use confirmation with **Awaken** and **Not yet**.
  Confirming commits the identity before the visual reveal begins. The sequence is
  Searching your soul → animated affinity sigil → bound weapon → Soul Interface.
  Reusing the command offers **View Character**, never another roll.
- `/fantasyprofile [member]`, `uwu fantasyprofile [member]`: read the caller's or
  another member's saved character. Looking someone up never awakens them.
- The final public profile has Character, Weapon, Abilities and Details tabs.
  Only its initiating viewer can operate those buttons. Anyone else can open their
  own public profile view. Views expire after 180 seconds and disable their controls.

This establishes identities, not a playable combat/progression system. Skills and
weapon traits describe future abilities; there are no damage rolls, quests, XP
awards, inventory, levelling, purchases, user rerolls or administrative resets yet.

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
read the winning row in a subsequent READ COMMITTED statement. There is **no**
`DO UPDATE`, delete/reset path or seed regeneration. The service exits/commits its
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

Potential: STR / DEX / INT / VIT / LCK — stored initial values
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
