# Running with 512 MB

The bot container has a 512 MiB limit in Compose. PostgreSQL and Redis run separately and are not included in that budget. On Azure, assign 512 MiB to the bot container and use separate database/cache resources.

Card rendering and profile analysis share one worker. Each image-work queue accepts at most four running/waiting requests, with a 10-second waiting timeout. Profile collection and celestial rendering also have bounded admission queues before downloading assets. Additional requests receive a busy response. Cached profile images are limited to 8 MiB; celestial cards to 4 MiB; ship avatars and cards to 4 MiB each. Discord retains 100 recent messages. Member caching remains enabled because server games and member lookups need it.

This configuration reduces memory pressure but does not guarantee a fixed memory ceiling under every workload. Guild member counts, active games, requests and voice sessions still consume memory. Container limits terminate an out-of-memory process; they do not prevent overload.

Run `python -m scripts.memory_smoke` locally for an offline import/render measurement. It does not connect to Discord, start voice, or model a populated server. Before production, test representative server traffic with the actual 512 MiB container limit, inspect `docker stats`, and leave headroom for bursts. Rebuild the image to apply these changes. Avoid multiple bot processes within one container.
