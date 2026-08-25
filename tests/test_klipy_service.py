"""Tests for the Klipy GIF provider integration."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from bot.services.klipy import FALLBACK_GIF_URL, FALLBACK_GIF_URLS, KlipyService


class FakeResponse:
    """Minimal aiohttp-like response stub for tests."""

    def __init__(self, payload: dict, *, status: int = 200):
        self.payload = payload
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")


class FakeSession:
    """Minimal session object with an async context manager on get()."""

    def __init__(self, payload: dict, *, status: int = 200):
        self.payload = payload
        self.status = status

    def get(self, *args, **kwargs):
        return FakeResponse(self.payload, status=self.status)


@pytest.mark.asyncio
async def test_search_gifs_accepts_results_payload_shape() -> None:
    """The service should handle Klipy responses that place GIFs under results instead of data."""

    service = KlipyService(
        api_key="test-key",
        rating="g",
        http_session=FakeSession({
            "results": [{
                "images": {
                    "original": {"url": "https://example.com/reaction.gif"},
                }
            }],
        }),
        cache=None,
    )

    result = await service._search_gifs("anime bonk")

    assert result.url == "https://example.com/reaction.gif"


@pytest.mark.asyncio
async def test_random_gif_uses_fallback_when_api_fails() -> None:
    """A failed or empty Klipy response should still return a usable fallback GIF."""

    service = KlipyService(
        api_key="test-key",
        rating="g",
        http_session=FakeSession({"error": "forbidden"}, status=403),
        cache=None,
    )

    result = await service.random_gif("anime bonk")

    assert result.url in FALLBACK_GIF_URLS
    assert result.url != FALLBACK_GIF_URL or result.url in FALLBACK_GIF_URLS
