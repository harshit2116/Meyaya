"""Lightweight public Wikimedia research fallback for source-backed fact checking."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
import html
import logging
import re
from urllib.parse import quote

import aiohttp

logger = logging.getLogger(__name__)

WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
USER_AGENT = "MeyayaBot/1.0 (+https://github.com/meyaya; Discord fact-check helper)"
MAX_SNIPPET_CHARS = 700

_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True, slots=True)
class WebSource:
    """One verified external search result used as fact-check evidence."""

    title: str
    url: str
    snippet: str


def _clean_html(raw: str, *, limit: int = MAX_SNIPPET_CHARS) -> str:
    text = html.unescape(_TAG_RE.sub(" ", raw))
    return " ".join(text.split()).strip()[:limit]


async def _fetch_wikipedia_summary(
    http_session: aiohttp.ClientSession,
    title: str,
) -> WebSource | None:
    slug = quote(title.replace(" ", "_"), safe="")
    url = WIKIPEDIA_SUMMARY_URL.format(title=slug)
    try:
        async with http_session.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=aiohttp.ClientTimeout(total=6),
        ) as response:
            if response.status != 200:
                return None
            payload = await response.json()
    except (aiohttp.ClientError, TimeoutError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    extract = _clean_html(str(payload.get("extract") or ""))
    page_url = (
        payload.get("content_urls", {}).get("desktop", {}).get("page")
        if isinstance(payload.get("content_urls"), dict)
        else None
    )
    canonical_url = (
        page_url
        if isinstance(page_url, str) and page_url.startswith("https://")
        else f"https://en.wikipedia.org/wiki/{slug}"
    )
    display_title = str(payload.get("title") or title).strip()
    if not display_title or not extract:
        return None
    return WebSource(
        title=f"{display_title} - Wikipedia"[:120],
        url=canonical_url,
        snippet=extract,
    )


async def _search_wikipedia(
    http_session: aiohttp.ClientSession,
    query: str,
    *,
    limit: int = 3,
) -> list[WebSource]:
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": str(limit),
        "format": "json",
        "utf8": "1",
    }
    try:
        async with http_session.get(
            WIKIPEDIA_API_URL,
            params=params,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=aiohttp.ClientTimeout(total=6),
        ) as response:
            if response.status != 200:
                return []
            payload = await response.json()
    except (aiohttp.ClientError, TimeoutError, ValueError):
        return []

    rows = payload.get("query", {}).get("search", []) if isinstance(payload, dict) else []
    titles_and_snippets: list[tuple[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()
        snippet = _clean_html(str(row.get("snippet") or ""))
        if title:
            titles_and_snippets.append((title, snippet))

    if not titles_and_snippets:
        return []

    summaries = await asyncio.gather(
        *(_fetch_wikipedia_summary(http_session, title) for title, _ in titles_and_snippets),
        return_exceptions=True,
    )
    sources: list[WebSource] = []
    for (title, fallback_snippet), summary in zip(titles_and_snippets, summaries, strict=True):
        if isinstance(summary, WebSource):
            sources.append(summary)
        elif fallback_snippet:
            slug = quote(title.replace(" ", "_"), safe="")
            sources.append(
                WebSource(
                    title=f"{title} - Wikipedia"[:120],
                    url=f"https://en.wikipedia.org/wiki/{slug}",
                    snippet=fallback_snippet,
                )
            )
    return sources


async def search_web_sources(
    http_session: aiohttp.ClientSession,
    queries: Sequence[str],
    *,
    max_sources: int = 6,
) -> list[WebSource]:
    """Fetch bounded, deduplicated public reference sources for fact-check synthesis."""

    cleaned_queries = [
        " ".join(query.split()).strip()[:140]
        for query in queries
        if isinstance(query, str) and query.strip()
    ]
    cleaned_queries = list(dict.fromkeys(cleaned_queries))[:3]
    if not cleaned_queries:
        return []

    batches = await asyncio.gather(
        *(_search_wikipedia(http_session, query, limit=3) for query in cleaned_queries),
        return_exceptions=True,
    )
    seen_urls: set[str] = set()
    sources: list[WebSource] = []
    for batch in batches:
        if not isinstance(batch, list):
            continue
        for source in batch:
            if source.url in seen_urls:
                continue
            seen_urls.add(source.url)
            sources.append(source)
            if len(sources) >= max_sources:
                return sources
    return sources
