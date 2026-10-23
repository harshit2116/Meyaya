"""Bounded, dated unfinished topics stored in the existing member memory system."""
from datetime import UTC, datetime, timedelta
import json

FOLLOWUP_PREFIX = "UNFINISHED_TOPIC "
FOLLOWUP_COOLDOWN = 7 * 86400


def normalize_followup(value: str, *, now=None) -> str | None:
    now = now or datetime.now(UTC)
    try:
        data = json.loads(value)
        if not isinstance(data, dict) or set(data) - {"topic", "state", "revisit_on"}:
            return None
        topic = data.get("topic")
        if not isinstance(topic, str) or not 3 <= len(topic.strip()) <= 350:
            return None
        state = data.get("state", "open")
        if state not in {"open", "resolved", "dismissed"}:
            return None
        revisit = datetime.fromisoformat(data["revisit_on"]).date()
        if not now.date() - timedelta(days=30) <= revisit <= now.date() + timedelta(days=90):
            return None
        return json.dumps({"topic": topic.strip(), "state": state,
                           "revisit_on": revisit.isoformat()}, ensure_ascii=False)
    except (ValueError, TypeError, KeyError):
        return None


def eligible_followup(record, *, now=None) -> dict | None:
    now = now or datetime.now(UTC)
    normalized = normalize_followup(record.value, now=now)
    if normalized is None:
        return None
    data = json.loads(normalized)
    if data["state"] != "open" or data["revisit_on"] > now.date().isoformat():
        return None
    return {"id": record.id, "relation": record.relation, **data}
