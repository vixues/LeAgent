"""Tests for web image search (Google CSE provider)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from leagent.tools.base import ToolContext
from leagent.tools.web.image_search.google_cse import search_google_cse
from leagent.tools.web.image_search_tool import WebImageSearchTool


@pytest.mark.asyncio
async def test_search_google_cse_parses_items(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "items": [
            {
                "title": "Cat",
                "link": "https://cdn.example.com/cat.png",
                "displayLink": "example.com",
                "image": {"thumbnailLink": "https://cdn.example.com/thumb.jpg"},
            },
            {"title": "bad", "link": "http://insecure/http-only.jpg"},
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=payload)

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    # polite_get uses client.request(), not get()
    mock_client.request = AsyncMock(return_value=mock_resp)

    monkeypatch.setattr(
        "leagent.tools.web.image_search.google_cse.httpx.AsyncClient",
        lambda **kwargs: mock_client,
    )

    hits = await search_google_cse(
        "cute cat",
        api_key="k",
        cx="cx",
        max_results=5,
    )
    assert len(hits) == 1
    assert hits[0].url == "https://cdn.example.com/cat.png"
    assert hits[0].thumbnail_url == "https://cdn.example.com/thumb.jpg"
    assert hits[0].source_host == "example.com"


@pytest.mark.asyncio
async def test_web_image_search_tool_requires_config(monkeypatch: pytest.MonkeyPatch) -> None:
    from leagent.config.settings import Settings

    s = Settings()
    s.image_search.api_key = ""
    s.image_search.cx = ""

    monkeypatch.setattr("leagent.config.settings.get_settings", lambda: s)

    tool = WebImageSearchTool()
    ctx = ToolContext(
        session_id="00000000-0000-4000-8000-000000000001",
        user_id="00000000-0000-4000-8000-000000000002",
    )
    out = await tool.execute({"query": "sky"}, ctx)
    assert out["count"] == 0
    assert out.get("image_search_configured") is False
    assert out.get("degraded") is True
    assert "IMAGE_SEARCH" in out.get("next_step", "")


@pytest.mark.asyncio
async def test_web_image_search_tool_meme_query(monkeypatch: pytest.MonkeyPatch) -> None:
    from leagent.config.settings import Settings

    s = Settings()
    s.image_search.api_key = "secret"
    s.image_search.cx = "cx123"

    monkeypatch.setattr("leagent.config.settings.get_settings", lambda: s)

    captured: dict[str, str] = {}

    async def fake_search(query: str, *, api_key: str, cx: str, max_results: int, endpoint: str):
        captured["query"] = query
        assert api_key == "secret"
        assert cx == "cx123"
        from leagent.tools.web.image_search.protocol import ImageHit

        return [ImageHit(url="https://x.example/i.webp", title="t")]

    monkeypatch.setattr(
        "leagent.tools.web.image_search_tool.search_google_cse",
        fake_search,
    )

    tool = WebImageSearchTool()
    ctx = ToolContext(session_id="00000000-0000-4000-8000-000000000001", user_id=None)
    out = await tool.execute({"query": "pepe", "intent": "meme", "max_results": 3}, ctx)
    assert "meme" in captured["query"].lower()
    assert out["count"] == 1
    assert out["results"][0]["url"] == "https://x.example/i.webp"
