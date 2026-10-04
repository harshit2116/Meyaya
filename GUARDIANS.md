# Soul-bound guardians and guardian battles

`/guardian [member]` / `uwu guardian [@member]` shows the companion belonging to
the member's saved awakening. `/guardianbattle member:@Haru` /
`uwu guardianbattle @Haru` challenges their companion in the current channel.
Human trainers need saved `/awaken` identities. Meyaya herself is also a valid
opponent: `/guardianbattle @Meyaya` or `uwu guardianbattle @Meyaya` starts without
waiting for consent. Her moves resolve automatically after 1.2 seconds, while
the player chooses manually and can recall even during her turn. Other bots
remain unsupported. Meyaya's local NPC profile is never inserted into the database:
level 999, all five stats 250, Mythic weapon, 10,000 HP/MP. Her Astral Dragon has
30,000 HP, 10,000 MP, 500 ATK/DEF/SPD and bond 100. These fights are deliberately
unfair, not balanced competitive matches, and give no XP or rewards.
Players can challenge Meyaya concurrently, subject to normal bounded arena capacity.
`/guardian @Meyaya` also displays her dragon. Automatic
`/versus` remains separate. One member cannot occupy both arenas simultaneously.

## Binding and fantasy integration

Version 1 hashes the owner ID, UTC-normalized saved awakening timestamp and class
ID to choose one of four original companion species. There is no date/guild
dependency, Python process hash, Gemini call or equipment dependency. Existing
awakened members immediately get a companion; it remains the same after midnight,
restart, server changes and equipment changes. Owner `fantasyreset` removes the
source awakening and closes either participant's active arena. A newly generated
awakening gets a new binding seed; it may coincidentally select the same species.

Affinity and its colour come from the saved profile. Guardian HP/MP/ATK/DEF/SPD
derive from saved VIT/INT/STR/DEX, plus small explicit species modifiers. Bond is
a fixed LCK-derived binding strength, not a claim of earned progression. Class
appears on the card; Soul Interface Details links the companion and commands.
No new schema, migration, key or background service is required. The existing
saved fantasy table must be deployed. Do not change version-1 species order or
binding input format casually: that would reassign existing companions. Stats
can reflect future saved stat growth, without reassigning the species.

The old low-level daily guardian card data/renderer remain for compatibility,
but the public command is no longer registered in CelestialCog. Fortune, tarot,
fate and summon retain their existing behaviour.

## Manual moves

The opponent alone accepts/declines a 90-second challenge; the challenger can
cancel. A new channel message holds the arena. Trainers take alternating turns;
SPD plus a tiny seeded roll selects the first trainer. The image/embed update
after each valid choice. Outsiders, wrong-turn actions, old-turn buttons and
duplicate clicks cannot perform a move. Buttons acknowledge before rendering.

- **Strike:** free attack.
- **Affinity Pulse:** 14 MP, 1.3× attack and the existing bounded fantasy element
  matrix (advantage 1.10×, reverse 0.90×, neutral 1.00×).
- **Guard:** halve the next incoming hit and recover 8 MP, capped at max MP.
- **Blessing:** 18 MP, maximum two uses, species-specific below.
- **Recall / Forfeit:** concede on your turn.

| Guardian | Fantasy role | Blessing | Trade-off |
| --- | --- | --- | --- |
| Velvet Owl | Dream sentinel | Clear Sight: next two attacks +15% power | Lower defence |
| Comet Fox | Astral familiar | Starstep: 8% HP recovery, next attack +15% | No extra armour |
| Moss Dragon | Ancient ward | Root Ward: 8% HP recovery and Guard | Lower speed |
| Pearl Moth | Veil keeper | Moonveil: 18% HP recovery | Lower attack |

Owl strikes also have a 4% power edge. Fox critical chance is 12%, otherwise 8%;
crits multiply damage 1.25×. Damage is based on ATK against DEF with 0.90–1.10
variance, capped at 32% opposing max HP. Healing, MP and HP always cap correctly.
Healing is temporary, cannot revive a defeated guardian and is finite. Blessing
buttons show remaining uses and disable when unavailable. Moonveil requires
missing HP; tactical blessings may be used at full HP.

A fixed 60-second turn deadline cannot be prolonged by invalid clicks. Six
minutes overall or 24 total choices ends the arena by remaining HP percentage;
within 3 percentage points is a draw. Running out of a turn concedes to the other
trainer. No polling loop: each arena holds one cancellable scheduled timer.

HP/MP, wards, focus and blessing charges are match snapshots. Battles do not
write injuries, XP, rewards or rerolls to the saved fantasy profile. Guardian
battle results are **not** currently durable history rows; the bounded existing
command-result cache retains public result context for replies until restart/expiry.

## Visuals, limits and failure handling

Original illustrated Owl/Fox/Dragon/Moth assets are bundled in
`bot/assets/guardians/`; generation prompts are recorded in that folder's README.
The affinity colours remain in the card and arena rather than recolouring the
creature's natural coat. Four bounded, cached portraits are resized with
antialiasing; code-drawn silhouettes are only a missing-asset fallback.
The monster-battle arena uses opposing mirrored portraits, trainer labels, HP bars,
MP, turn indicator, move log and clear WON/LOST/DRAW labels. No Pokémon characters,
artwork, runtime remote image generation or GIF generation is used. Creature sprites are
RGBA with preserved transparency even when the defeated side is greyed out.

The guardian command remains image-only when rendering succeeds, without a
duplicate block of plain text above it. Rendering/upload failures use readable
text embeds. Existing single Pillow worker and bounded image queue handle all
cards. Each PNG has a 4 MB budget. No separate HTTP session or database session
held across battle turns. Same max 16 reservations / 64 Fantasy views / bounded
cooldowns as `/versus`. Guild removal, member departure, message deletion, owner
reset, timeout, exceptions and unload close the view and cancel its timer/task.
Restarted buttons explain expiry instead of replaying saved clicks.

## Files and verification

- `bot/services/fantasy_guardian.py`: stable binding and pure manual combat.
- `bot/services/guardian_render.py`: original creatures, guardian and arena PNGs.
- `bot/views/guardian_battle.py`: consent, move buttons, deadlines and delivery.
- `bot/cogs/fantasy.py`: public guardian commands and shared admission.
- `bot/cogs/celestial.py`: removes the old daily command registration.
- `bot/views/fantasy.py`: companion in Soul Interface Details.
- `bot/data/help_catalog.py`: canonical slash/prefix/help descriptions.
- `test_guardian_battle.py`, `pyproject.toml`: offline regression tests.

Run `python -m pytest -q` in the configured environment. Tests cover binding
stability, timezone normalization, original rendering, resource bounds, species
blessings, 1,000 complete battles, turn ownership, consent, expired/stale clicks,
delivery failure and cleanup. No live production database is changed by tests.
Restart/sync to update `/guardian` and add `/guardianbattle`. Live Discord checks
still needed: two trainers, mobile artwork, one-minute expiry, invalid clicks,
recall, restart and attachment delivery. No push/deployment is performed automatically.
