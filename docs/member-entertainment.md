# Entertainment command structure

All commands support slash, the server prefix (default uwu), and a bot mention.

## Social / AI - five commands

- roast [member]: a gentle contextual roast.
- compliment [member]: sincere or funny praise.
- rank @first @second [third] [fourth] [fifth]: 2-5 distinct members. The system selects the category and displays it above the model's ranking.
- impersonate [member]: one playful imitation through a webhook using their current name/avatar. Requires Manage Webhooks; cannot ping members.
- legacy [member]: a fictional server legacy.

Only these five commands in this entertainment stack call the model. They share the server AI allowance and have per-member cooldowns. Context is restricted to this server's relationship state and a few target-authored messages in the current channel; private memories are not loaded. Existing chat, moderation, court and other unrelated features retain their own provider behavior.

## Fortune / Tarot - three commands

- fortune [member] [question]: daily verdict, luck, lucky number/color/theme, omen and advice. Optional questions get a seeded playful oracle answer, not semantic analysis.
- tarot [member]: three distinct major arcana, past/present/future, with upright or reversed interpretations.
- fate [member]: archetype, path, strength and possible chapter.

## Fantasy / Profile - two commands

- summon [member]: class, rarity, role, affinity, stats, passive and shadow drawback.
- guardian [member]: companion type, affinity, bond, blessing and weakness.

All five draws are system-driven, with local image rendering and structured accessible text. Omitting a member selects yourself. Results use server + member + command + UTC date + rules version. The cache is bounded in memory; no collection database or durable dyno filesystem is required.

## Single Player - three commands

- escape: branching choices and outcome scores.
- detective: limited clues, three suspects and an evidence-backed reveal.
- personalitytest: six questions scored into playful archetypes.

No model calls. Only the player can interact; duplicate clicks are rejected. One game per member per server; three minutes of inactivity expires a session. A restart closes in-memory games.

## Removed and merged

matchup is removed. omen/luck are fields in fortune; future is part of fate; rarity/shadow are fields in summon. No prophecy or destiny aliases are registered. Other pre-existing bot commands are not removed by this 13-command rework.

## Implementation

- bot/data/cards/: versioned tarot, fortunes, archetypes, classes and guardians JSON.
- bot/services/celestial.py: seeded selection, immutable results and provenance metadata.
- bot/services/card_renderer.py: Pillow presentation only.
- bot/cogs/celestial.py: command arguments, bounded image cache and delivery.
- bot/cogs/member_fun.py: social-only model generation.
- bot/cogs/solo_games.py: local game state and scoring.

After restart, the owner should run synccommands to update Discord's registered slash command list.
