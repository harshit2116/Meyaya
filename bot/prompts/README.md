# Prompt ownership

- `bot/private/personality.v1.json` is the single active Meyaya personality config.
  `schema_version` describes its structure; increment `revision` when changing its tone.
  Keep traits, humor, speaking style and temperament here, not tool or memory instructions.
- `bot/private/prompt_rules/v1/` holds private identity context, conversation rules,
  memory rules, lore rules, tool instructions and voice rules in separate text files.
- `rules.py` defines safe public defaults and the capabilities of each prompt profile.
- `social_games.py`, `court.py`, `monitor.py` and `fact_check.py` contain independent,
  versioned feature instructions. They do not load Meyaya's personality.
- `composer.py` combines personality, contextual data, and only the selected feature's rules.

Chat includes memory, lore, tool and relationship instructions. Flavor text, proactive replies
and voice cannot request writes or tools. Proactive replies may read contextual memory;
voice adds speech-specific rules. Operational rules take precedence over character tone.
Python still validates and executes actions, game decisions, and moderation outcomes.

Restart after editing private prompts, which are cached. Git ignores the private configuration;
copy it separately when deploying. The previous `gemini_persona.txt` and
`gemini_voice_rules.txt` remain available for reference but are no longer loaded. The module
`bot/data/gemini_persona.py` only re-exports the new builders for compatibility.

Roleplay characters keep their separate private prompts and do not inherit Meyaya's chat tools.
