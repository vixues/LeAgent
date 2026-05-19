"""Tests for polite HTTP + robots helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from leagent.tools.web import robots_policy as rp


@pytest.mark.asyncio
async def test_assert_fetch_allowed_404_robots_fail_open(monkeypatch: pytest.MonkeyPatch) -> None:
    from leagent.config.settings import Settings, WebFetchSettings, get_settings

    get_settings.cache_clear()
    s = Settings().model_copy(update={"web_fetch": WebFetchSettings(enabled=True, check_robots_txt=True)})
    monkeypatch.setattr("leagent.config.settings.get_settings", lambda: s)
    rp._cache.clear()

    async def boom(_client: httpx.AsyncClient, url: str, **kwargs: object) -> None:
        req = MagicMock()
        resp = MagicMock()
        resp.status_code = 404
        raise httpx.HTTPStatusError("nope", request=req, response=resp)

    monkeypatch.setattr("leagent.tools.web.robots_policy.polite_get", boom)

    client = MagicMock()
    await rp.assert_fetch_allowed(client, "https://example.com/page")
