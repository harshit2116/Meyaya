"""Activity-based limits for unsolicited replies."""

import re


_CLOSINGS = {
    "thanks", "thank you", "thank you meyaya", "thanks meyaya", "ty", "tysm",
    "thanks a lot", "thank you so much", "okay", "ok", "alright", "got it",
    "understood", "cool", "okay thanks", "ok thanks", "all good", "that's all",
    "thats all", "that's it", "thats it", "bye", "goodbye", "good night",
    "goodnight", "gn", "see you", "see you later", "talk later", "cya",
}


def is_conversation_closing(text: str, *, previous_text: str | None = None, has_attachments=False) -> bool:
    """Only silence an entire acknowledgement, never a request containing one."""
    if has_attachments or "?" in text:
        return False
    normalized = " ".join(re.sub(r"[^\w' ]", " ", text.casefold()).split())
    if normalized not in _CLOSINGS:
        return False
    # 'Okay' can answer Meyaya's question/offer rather than end the exchange.
    if normalized in {"okay", "ok", "alright", "cool", "got it", "understood"} and (
        previous_text is None or "?" in previous_text
    ):
        return False
    return True


def reply_policy(messages_in_five_minutes: int) -> tuple[float, int]:
    """Return candidate probability and minimum seconds between replies."""
    if messages_in_five_minutes <= 5:
        return 0.35, 300
    if messages_in_five_minutes <= 20:
        return 0.10, 900
    return 0.01, 2700
