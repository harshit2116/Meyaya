"""Neutral argument and single-message fact checking with grounded citations."""

from __future__ import annotations

from bot.prompts.fact_check import build_fact_check_instruction

from dataclasses import dataclass
import json

from bot.services.llm import LLMProvider, GroundedCitation

MAX_ARGUMENT_MESSAGES = 60
MAX_ARGUMENT_CHARACTERS = 18_000
MAX_MESSAGE_CHARACTERS = 1_200
MAX_PUBLIC_SOURCES = 10


@dataclass(frozen=True, slots=True)
class FactCheckMessage:
    """A Discord message represented as untrusted evidence."""

    message_id: int
    author_id: int
    author_label: str
    content: str
    jump_url: str


@dataclass(frozen=True, slots=True)
class FactCheckResult:
    """A display-ready report with source markers and message count."""

    report: str
    message_count: int
    source_count: int


class FactCheckService:
    """Ask Gemini to research factual claims without judging the participants."""

    def __init__(self, llm: LLMProvider | None) -> None:
        self.llm = llm

    async def analyze(
        self,
        messages: list[FactCheckMessage],
        *,
        single_message: bool,
    ) -> FactCheckResult | None:
        if self.llm is None or not messages:
            return None

        evidence = [
            {
                "message_id": message.message_id,
                "author_id": str(message.author_id),
                "author": message.author_label,
                "message_url": message.jump_url,
                "content": message.content[:MAX_MESSAGE_CHARACTERS],
            }
            for message in messages
        ]
        mode = "one Discord message" if single_message else "a Discord argument"
        system = build_fact_check_instruction(mode)
        grounded = await self.llm.grounded_generate(
            system,
            "Fact-check this JSON evidence:\n" + json.dumps(evidence, ensure_ascii=False),
            max_output_tokens=1800,
            timeout_seconds=45,
        )
        if grounded is None:
            return None
        rendered, source_count = render_grounded_sources(grounded.text, grounded.citations)
        return FactCheckResult(
            report=rendered,
            message_count=len(messages),
            source_count=source_count,
        )


def render_grounded_sources(
    text: str,
    citations: tuple[GroundedCitation, ...],
) -> tuple[str, int]:
    """Insert numbered citation markers and append a deduplicated source list."""

    source_number: dict[str, int] = {}
    source_details: list[tuple[str, str]] = []
    insertions: dict[int, set[int]] = {}
    for citation in citations:
        if citation.url not in source_number:
            if len(source_details) >= MAX_PUBLIC_SOURCES:
                continue
            source_number[citation.url] = len(source_details) + 1
            source_details.append((citation.title, citation.url))
        number = source_number[citation.url]
        position = min(len(text), max(0, citation.end_index))
        insertions.setdefault(position, set()).add(number)

    rendered = text
    for position in sorted(insertions, reverse=True):
        markers = "".join(f"[{number}]" for number in sorted(insertions[position]))
        rendered = rendered[:position] + markers + rendered[position:]

    if source_details:
        source_lines = ["\n\n## Sources"]
        for number, (title, url) in enumerate(source_details, start=1):
            safe_title = " ".join(title.replace("[", "").replace("]", "").split())
            source_lines.append(f"[{number}] [{safe_title}]({url})")
        rendered += "\n".join(source_lines)
    else:
        rendered += (
            "\n\nNo web sources were returned. Treat the report as analysis only, not a verified "
            "fact check."
        )
    return rendered, len(source_details)
