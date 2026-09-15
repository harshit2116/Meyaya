"""Activity-based limits for unsolicited replies."""


def reply_policy(messages_in_five_minutes: int) -> tuple[float, int]:
    """Return candidate probability and minimum seconds between replies."""
    if messages_in_five_minutes <= 5:
        return 0.35, 300
    if messages_in_five_minutes <= 20:
        return 0.10, 900
    return 0.01, 2700
