# Fantasy Versus — rules v2

Use `/versus member:@Haru` or `uwu versus @Haru`. Both human members must already
have permanent `/awaken` identities and belong to the same server. Only the
opponent can accept/decline; the challenger can cancel. Challenges expire after
90 seconds. Results offer participant-only Rematch, My Fantasy Profile and
Battle Details for 3 minutes. A rematch requires **another consent challenge**.

Exception: challenge Meyaya herself with `/versus member:@Meyaya` or
`uwu versus @Meyaya`. She accepts immediately, using a deterministic local
final-boss identity: level 999, all stats 250, Mythic weapon, 10,000 HP/MP.
Her ordinary class mechanics and minimum-move rules still apply, but she is
intentionally overpowered. No NPC profile database row or Gemini request is
needed. Your awakening is unchanged and there are no rewards. Start another
`/versus @Meyaya` for a boss rematch (the human-consent Rematch button is disabled).
Other bots cannot be challenged. Her guardian counterpart is documented in
[GUARDIANS.md](GUARDIANS.md).

## Deployment

Run `alembic upgrade head` with the existing environment/database configuration,
first on an isolated test database, then deploy migration `0030_fantasy_duels`.
Restart Meyaya to sync `/versus`. The migration adds `fantasy_duel_results` only.
No identities are reset. Downgrading it destroys duel history, not awakenings.
No migrations are automatically applied. Missing/unavailable history storage
shows a warning/error ID without preventing the completed battle from appearing.

Live checks still required: consent, outsiders, rapid clicks, mobile cards, Discord
attachment delivery, deleted messages, departed members, restart and PostgreSQL
history inserts. Offline mocks do not prove those live integrations. Run one bot
process per token: admission locks are local, not a multi-host Redis coordinator.

## Actual saved fields

Duels copy user ID, class, subclass, title, level, affinity, weapon family/name/rarity,
passive/signature identifiers/names, STR, DEX, INT, VIT, LCK and max HP/MP.
Temporary HP/MP start full. No identity mutations, XP, rewards, inventory,
economy or permanent injuries. Subclass/title are labels, not extra invented stats.
Level is displayed, not multiplied again: profiles currently have level 1 and no
progression. Alignment, flavour descriptions, weapon lore/trait and generation
version do not independently affect combat. Weapon trait is affinity flavour,
not a second executable ability. Guardian and summon remain separate commands.

## Combat formula

One `random.Random(seed)` per duel selects a cosmetic arena and all combat rolls.
Initiative = DEX + class bonus + uniform(-2, 2); shuffled ties avoid challenger
priority. Both fighters act while alive. Maximum six rounds.

Offence: physical STR; agile max(STR, DEX); magic INT;
hybrid 0.75 × max(STR, INT) + 0.25 × min(STR, INT).

```
raw = (18 + 1.10 × offence + 0.12 × DEX - 0.20 × defender VIT)
      × mode scale × class scale × weapon scale × (1 + 0.01 × rarity index)
      × uniform(0.90, 1.10) × element × mitigation × statuses × skill × crit
endurance = clamp(sqrt(defender max HP / 160), 0.8, 1.3)
damage = clamp(round(raw × 0.65 × endurance), 1, floor(defender max HP × 0.22))
```

Mode scales physical/agile/hybrid/magic = 1.00/1.18/1.24/1.42 compensate for
the actual saved resource distribution, without replacing HP/stat rolls.
Class scales: Mage 1.10, Cleric 0.95, Runeblade 1.10, Starcaller 1.18,
Dreamweaver 1.10, Fatebinder 1.18, Dragon Warden 1.05, Abyss Walker 1.08,
Moon Priestess 0.98; otherwise 1. Knight mitigation 6%, Paladin/Gravekeeper 4%,
Dragon Warden 4%. Endurance scaling offsets tank advantage with longer fights
while retaining saved VIT/HP differences. Damage pacing, not a hidden survival
floor or fake attacks, keeps valid saved profiles fighting for at least eight moves.

Crit = min(22%, 3.5% + 0.3% × LCK + weapon bonus + temporary 4%); damage ×1.30.
Dodge = min(20%, 2.5% + 0.25% × DEX + weapon bonus + temporary 5%). Precision
halves dodge; precise signatures multiply it by 0.3. Rarity Common→Mythic
contributes only 0–5% damage, never a guaranteed win.

Weapon damage/crit/dodge bonuses:

| Family | Damage scale | Crit addition | Dodge addition |
| --- | --- | --- | --- |
| sword | 1.00 | 1% | 0 |
| greatsword | 1.04 | 0 | 0 |
| spear | 1.01 | 1% | 0 |
| bow | 0.98 | 2% | 1% |
| daggers | 0.97 | 3% | 2% |
| katana | 1.00 | 2% | 1% |
| staff | 1.02 | 0 | 0 |
| spellbook | 1.00 | 1% | 0 |
| mace | 1.02 | 0 | 0 |
| axe | 1.03 | 1% | 0 |

Bonuses are added before chance caps. Signatures attempt on rounds 2 and 4,
maximum two uses, consuming 22 MP (first discounted cast 16). Insufficient MP
falls back to a weapon strike. Burst ×1.38, break/precise ×1.28,
heal/guard ×0.90, other signatures ×1.12. Support signatures also strike so
support classes cannot stall forever. Break halves existing shields. Fire/blood
signatures add burn/bleed: 1% max HP at each of two round ends. Shields absorb
before health; healing caps at max HP. DOT counts toward attacker damage and may
cause simultaneous KO. At round six, remaining HP percentage decides; within
3 percentage points is a draw. Surviving losers are labelled Outmatched, not KO.

## Explicit current class and passive mappings

Displayed ability names remain the existing saved catalog names; these are
v2 interpretations, not replacement awakening identities.

| Class ID | Mode | Passive | Signature | Initiative bonus |
| --- | --- | --- | --- | --- |
| knight | physical | shield | weaken | 0 |
| ranger | agile | evasion | precise | 1 |
| assassin | agile | crit | evasion | 2 |
| mage | magic | discount | burst | 0 |
| cleric | magic | shield | heal | 0 |
| berserker | physical | empower | break | 0 |
| paladin | hybrid | shield | guard | 0 |
| warlock | magic | refund | weaken | 0 |
| spellblade | hybrid | empower | burst | 0 |
| runeblade | hybrid | discount | weaken | 0 |
| voidblade | hybrid | evasion | break | 1 |
| starcaller | magic | precision | burst | 2 |
| dreamweaver | magic | resist | weaken | 0 |
| gravekeeper | hybrid | shield | guard | 0 |
| spirit_tamer | magic | evasion | guard | 0 |
| storm_herald | hybrid | empower | burst | 0 |
| fatebinder | magic | precision | precise | 1 |
| dragon_warden | physical | shield | weaken | 0 |
| moon_priestess | magic | renew | heal | 0 |
| chronomancer | magic | discount | weaken | 1 |
| abyss_walker | hybrid | resist | evasion | 1 |

Passives trigger once: shield adds 3% max HP; renew restores 3% at/below half HP;
discount saves 6 MP on first signature; refund returns 5 MP after first signature.
Empower adds 8% damage, resist adds 5% mitigation (total mitigation capped at 12%);
evasion/crit/precision modify bounded chances as above. Temporary statuses last
two round ends, at most three types; reapplication refreshes instead of stacking.
Weaken reduces damage by 10%. Signature heal restores 3% max HP, guard adds a
4% max HP ward capped at 15%. Unknown class/weapon mappings use neutral combat;
unknown or mismatched authored abilities get no invented effect and are identified
honestly in Battle Details.

## Element matrix

Each arrow is ×1.10 attacking damage, reverse ×0.90; same/unlisted pairs ×1.00.
No element auto-wins.

| Advantage attacker | Defender |
| --- | --- |
| fire | nature |
| nature | water |
| water | fire |
| storm | water |
| earth | storm |
| frost | blood |
| blood | earth |
| solar | frost |
| light | shadow |
| shadow | lunar |
| lunar | solar |
| celestial | void |
| void | arcane |
| arcane | celestial |

## Rendering, history and resource bounds

The consent message is acknowledged/disabled, then three new channel messages:
full-size standalone versus image with a large VS → one live battle
embed edited after **every individual move** → a new standalone result image
with clear WON/LOST labels (DRAW for ties) and participant result buttons. The
opening and result images remain available instead of being overwritten. At least eight
combined actions, maximum twelve within six rounds; misses count as genuine
actions. Maximum fourteen PNG renders (intro, twelve actions, final controls),
never a duel GIF. Intro holds 3 seconds, moves 1.5 seconds. Each side uses the member's cached
avatar/profile palette; fallback initials and arena colours. Original procedural
shards, glow and particles; eight cosmetic arenas. Defeated avatar greys out,
winner gets a gold outline, HP/MP bars reflect temporary battle state. Render or
upload failures fall back to text at that stage, not per-move message spam.

No Gemini, polling, new executors/HTTP sessions, member enumeration or per-turn
DB writes. Reuses bounded asset downloads and one Pillow worker. Maximum 16
reserved duels, 64 Fantasy views, 512 cooldown entries, 512 command summaries.
30-second command cooldown; 15-second admission/rematch cooldown. Accepted runs
have a 75-second deadline. Buttons acknowledge before slow work. Expiry, decline,
cancel, departure, deleted messages, guild removal, exceptions and unload release
reservations; unload cancels active work. Restarted/orphaned buttons explain expiry.

One idempotent history insert per completed duel: UUID, guild, participant IDs,
winner/null, seed, rules version, rounds, arena, initial combat snapshots, move count, compact
final HP/MP/damage/crit/dodge/skill stats, verdict/finisher and timestamp. No images
or chat transcripts stored. Two participant/time indexes. Seed reproduction
requires the corresponding rules implementation, not just the saved version number.

## Files changed / tests

- `bot/data/fantasy_combat.py`: catalog mappings, elements, arenas.
- `bot/services/fantasy_duel.py`: temporary snapshots and seeded engine.
- `bot/services/fantasy_duel_renderer.py`: bounded palette-coloured still cards.
- `bot/views/fantasy_duel.py`: consent and participant-only result controls.
- `bot/cogs/fantasy.py`: admission, assets, combat, delivery, cancellation.
- `bot/models/fantasy_duel.py`, `bot/repositories/fantasy_duels.py`: history.
- `alembic/versions/0030_fantasy_duels.py`, `alembic/env.py`: migration/discovery.
- `bot/utils/game_interactions.py`: orphaned-button handling.
- `bot/cogs/admin.py`: reset respects both duel participants.
- `bot/data/help_catalog.py`: shared command help/description.
- `test_fantasy_duel.py`, `pyproject.toml`: offline regression coverage.
- `scripts/simulate_fantasy_duels.py`: local reproducible balance report.
- `README.md`, `FANTASY_GUIDE.md`, this guide: operator documentation.

```powershell
python -m pytest -q
python scripts/simulate_fantasy_duels.py --samples 5000
python -m compileall -q bot scripts
git diff --check
```

Balance seed 20261005, 5,000 random class matchups (half-credit for draws): class
win rates 40.4–63.2%, 119 draws; rounds 5/6 = 2689/2311; moves 9/10/11/12 =
1615/1074/1095/1216. Another
1,000 matched rarity comparisons: Mythic vs Common 57.65% (not guaranteed).
Another 1,000 matched stat comparisons: +3 all stats with generated HP/MP wins
81.7%. These are offline samples, not a claim of perfect competitive balance.
