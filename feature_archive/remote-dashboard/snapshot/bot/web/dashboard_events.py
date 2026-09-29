"""Content-free, bounded event fan-out. Slow clients never delay Discord."""

import asyncio
from collections import deque
from datetime import UTC, datetime
import re
import math


class EventHub:
    TYPES = {
        "bot.connected",
        "bot.disconnected",
        "bot.ready",
        "bot.latency",
        "guild.joined",
        "guild.left",
        "command.started",
        "command.completed",
        "command.failed",
        "voice.joined",
        "voice.left",
        "voice.playback.started",
        "voice.playback.stopped",
        "game.started",
        "game.ended",
        "error",
        "database.health",
        "redis.health",
        "rate_limit.warning",
        "health.changed",
    }

    def __init__(self):
        self.history = deque(maxlen=100)
        self.clients = set()
        self.sequence = 0
        self.dropped = 0

    def publish(self, payload):
        name = payload.get("event", payload.get("type"))
        if name == "command_timing":
            name = "command.completed" if payload.get("status") == "success" else "command.failed"
        elif name == "command_error":
            name = "error"
        elif name in {"discord_rate_limit", "llm_attempt_failed"}:
            name = "rate_limit.warning"
        elif name == "game_transition":
            phase = payload.get("phase")
            previous = payload.get("previous")
            if phase == "COLLECTING" and previous == "LOBBY":
                name = "game.started"
            elif phase in {"RESULTS", "CLOSED"} and previous != "RESULTS":
                name = "game.ended"
        if name not in self.TYPES:
            return
        self.sequence += 1
        item = {"type": name, "sequence": self.sequence, "timestamp": datetime.now(UTC).isoformat()}
        for key in ("guild_id", "channel_id", "user_id"):
            value = payload.get(key)
            if isinstance(value, int) and value > 0:
                item[key] = str(value)  # Discord snowflakes exceed JS's integer precision.
        for key in ("command", "status", "error_id", "exception", "stage", "reason"):
            value = payload.get(key)
            if isinstance(value, str) and re.fullmatch(r"[\w .:/-]{1,100}", value):
                item[key] = value
        value = payload.get("total_ms", payload.get("duration_ms"))
        if isinstance(value, (int, float)) and math.isfinite(value):
            item["duration_ms"] = round(value, 2)
        self.history.append(item)
        for queue in tuple(self.clients):
            if queue.full():
                queue.get_nowait()
                self.dropped += 1
            queue.put_nowait(item)

    def subscribe(self):
        if len(self.clients) >= 4:
            raise ValueError("Client limit")
        queue = asyncio.Queue(maxsize=64)
        self.clients.add(queue)
        return queue


hub = EventHub()
