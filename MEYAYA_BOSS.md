# Meyaya: Soul Interface Authority

Use `/versus member:@Meyaya` or `uwu versus @Meyaya`. Only the logged-in
`bot.user.id` selects this path, never a matching nickname. The player needs an
awakening; Meyaya never queries/creates a player row. PvP keeps `DuelEngine`,
human consent and existing v5 rules. No migration or reward economy is added.

## One continuous encounter

Challenge → auto-accept → intro GIF/dialogue → analysis → one class rewrite →
opening card → edited live battle → victory dialogue/GIF → final card.
The intro GIF remains visible for five seconds after sending. Intro/analysis and
at most three in-battle remarks reuse the cinematic message. The complete victory
dialogue and GIF are sent together as a NEW message; the final result card is
also new. The live battle still edits its existing message.
No phases, resets, forced victory, permanent stat changes or Gemini requests.
Large ordinary Discord Markdown headers keep dialogue prominent. Although
discord.py 2.7.1 supports LayoutView, existing embeds/views remain more compatible
with the project's attachment-edit and fallback paths.

Intro: `https://klipy.com/gifs/honkai-impact-22`.
Meyaya victory: `https://klipy.com/gifs/elysia-honkai-impact-3rd-3`.
`KlipyService.exact_gif` uses the documented `/gifs/items?slugs=...` API with the
existing session, bounded TTL cache and per-key request lock. Each GIF resolves
once per encounter. No scraping, downloads, frame decoding, random substitutes
or hardcoded CDN links. GIF failure continues without media; rejected media
embeds retry without the GIF. Requires the existing working `KLIPY_API_KEY`.
Live resolution and Discord playback still need deployment verification.

## Identity

Recorded class: **Soulweaver**. Lore: **The Girl at the End of Every Story**.
Weapon: **Everbloom - Crown of the Last Wish**, Mythic Spellcrown.
Passive: **Spell Memory**. Signature: **Prism Cascade**.
Authority: **Soul Interface**. Affinity: **Arcane · Bloom · Ego**.
At encounter creation, Meyaya gets ten times the challenger's maximum HP and MP.
Each core stat is twice the challenger's, with a minimum of 30. This is an
intentionally overpowered encounter, not the previous balanced boss. Only the
in-memory battle snapshot changes; saved profiles remain untouched. These
implementation values are never public profile/battle information.

## Adaptation

Select once using authored CombatRule mechanics, in this priority order:
support → tank → agile → physical/magic/hybrid. No class-name substring guessing.

| Pattern | Form | Bounded counter |
| --- | --- | --- |
| Physical | Glassblade Seraph | 10% resistance; one 6% ward; two-turn evasion |
| Magic | Prism Oracle | 10% resistance; Cascade costs 16 instead of 22 MP |
| Tank/guard | Bloom Executioner | 35% shield reduction; 2% max-HP pressure; 25% anti-heal |
| Agile | Mirror Huntress | Dodge chance multiplied by 0.4; +2 initiative |
| Support/heal | Ego Sovereign | 25% anti-heal; 2% pressure; Cascade dispels one resist status |
| Hybrid | Star-Petal Arcanist | 6% resistance; +2 initiative |

Knight/Paladin/Gravekeeper/Dragon Warden/Spirit Tamer → tank;
Cleric/Moon Priestess → support; Ranger/Assassin → agile; Berserker → physical;
Mage/Warlock/Starcaller/Dreamweaver/Fatebinder/Chronomancer → magic;
other authored hybrid classes → hybrid. Unmapped mechanics default to hybrid.

Memory observes repeated weapon/signature and element labels. Each label triggers
once on its second observation. Three adaptations maximum add 4% each, capped
at 12% memory resistance; total baseline+memory resistance never exceeds 22%.
The first successfully cast signature is learned. One later reflection spends
18 MP and translates its label into one normalized capped attack. No executable
skill copying, chains, recursion or permanent learning.

Cascade occurs on boss actions two/four when affordable. The existing element
registry chooses rays countering the player's affinity (Arcane if no known edge).
Five integer rays sum
to one bounded total, each interacting with remaining shields/HP. Offensive
damage is capped at 32% of player max HP. Criticals and dodges are real. Two
Cascades and one reflection have finite MP costs. Meyaya never heals/revives.
The first three combined moves retain opening pacing; afterward KOs decide the
fight. Twenty rounds and the existing 75-second deadline are safety ceilings.

## Masking / performance / safety

HP/MP bars shrink with internal ratios but text always says UNKNOWN / `??? / ???`.
No exact values/percentages in profile tabs, rendered cards, result embeds,
Battle Details or AI-visible command summaries. Boss history snapshots are
masked too; player damage-dealt totals are omitted in boss history. Reproduction
uses the seed, player snapshot and boss rules version 2, not a numeric boss row.

The dedicated fantasy profile is image-only, without extra text or tab buttons.
`bot/assets/duels/meyaya-profile.png` is the latest supplied Divine Presence
artwork, displayed unchanged with no avatar overlay or download. Veyra's Hostile
Presence card is `veyra-profile.png`. `uwu fantasyprofile Veyra` (also `Veryra`,
case-insensitive) opens that authored lore profile without a member/database row.
`uwu fantasyprofile Meyaya` opens Meyaya's card; mentioning the real bot also
works. Slash `/fantasyprofile` retains its existing optional member picker.
Ordinary members and member mentions still use saved fantasy identities.
The illustrated challenge
template is `meyaya-challenge.png`; challenger names, titles, class, palette and
portraits are composed locally, never copied from its example labels.

Local pink/lilac/cyan petals, glass shards, scanlines, fractured borders and
Everbloom's halo distinguish the boss. Existing one-worker Pillow service and
render gate are reused. No workers, loops, image arrays, per-turn DB writes or
battle GIF generation. Requested Klipy GIFs are media embeds, not rendered art.

Existing timeout, guild/member/message removal, command-finally and unload
cleanup release player reservations. The bot is not globally reserved. Deleting
the tracked cinematic or active battle message interrupts safely. The guardian
battle remains a separate intentionally overpowered NPC mode; this redesign is
for `/versus` only.

## Verification

`python -m scripts.simulate_meyaya_boss`: 2,100 builds (100 per authored class),
seed 20261005. Current boss win rate 100%; no player wins or draws;
7-15 combined actions. She is deliberately overwhelming. There is still no
forced-win flag or immortality: an artificial extreme-offence build can defeat
her. These are sampled outcomes, not guaranteed percentages.

`test_meyaya_boss.py` covers all archetypes, caps, deterministic outcomes,
reflection, five rays, player victory, masking, changing bars, profile tabs,
GIF cache/failure, cinematic reuse, serialization and failure cleanup. Run the
entire suite with `python -m pytest -q`.

Live checks: both exact GIFs, mobile readability, profile tabs, completed match,
Battle Details, deletion/cancellation, saved history and a normal PvP duel.
