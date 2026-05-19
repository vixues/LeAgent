"""Tool execution rate limiting."""

from __future__ import annotations

import os

import pytest

from leagent.tools.rate_limit import SlidingWindowRateLimiter, tool_rate_limit_from_env


def test_sliding_window_enforces_cap() -> None:
    lim = SlidingWindowRateLimiter(max_calls=2, window_sec=60.0)
    assert lim.allow("u1")
    assert lim.allow("u1")
    assert not lim.allow("u1")
    assert lim.allow("u2")


def test_env_disabled_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LEAGENT_TOOL_RATE_LIMIT_PER_MINUTE", raising=False)
    lim, _ = tool_rate_limit_from_env()
    assert lim is None


def test_env_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEAGENT_TOOL_RATE_LIMIT_PER_MINUTE", "100")
    lim, win = tool_rate_limit_from_env()
    assert lim is not None
    assert win == 60
    os.environ.pop("LEAGENT_TOOL_RATE_LIMIT_PER_MINUTE", None)
