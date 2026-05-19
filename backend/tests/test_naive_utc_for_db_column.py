"""Regression: naive UTC for TIMESTAMP WITHOUT TIME ZONE (asyncpg binding)."""

from __future__ import annotations

from datetime import datetime, timezone

from leagent.services.database.models.base import naive_utc_for_db_column


def test_none_passthrough() -> None:
    assert naive_utc_for_db_column(None) is None


def test_naive_unchanged() -> None:
    n = datetime(2026, 5, 2, 17, 3, 29, 374000)
    assert naive_utc_for_db_column(n) is n


def test_aware_utc_strips_tz() -> None:
    aware = datetime(2026, 5, 2, 17, 3, 29, 374000, tzinfo=timezone.utc)
    out = naive_utc_for_db_column(aware)
    assert out.tzinfo is None
    assert out == datetime(2026, 5, 2, 17, 3, 29, 374000)


def test_aware_non_utc_converts_to_utc_wall() -> None:
    # UTC+8 2026-05-03 01:00 -> UTC 2026-05-02 17:00
    from zoneinfo import ZoneInfo

    china = ZoneInfo("Asia/Shanghai")
    local = datetime(2026, 5, 3, 1, 0, 0, tzinfo=china)
    out = naive_utc_for_db_column(local)
    assert out.tzinfo is None
    assert out == datetime(2026, 5, 2, 17, 0, 0)
