"""Unit tests for daily empty-state greeting parsing and locale defaults."""

from __future__ import annotations

import json

import pytest

from leagent.services.chat import daily_greetings as dg


def test_normalize_greeting_locale() -> None:
    assert dg.normalize_greeting_locale("zh-CN") == "zh-CN"
    assert dg.normalize_greeting_locale("zh") == "zh-CN"
    assert dg.normalize_greeting_locale("en-US") == "en-US"
    assert dg.normalize_greeting_locale(None) == "en-US"


def test_default_greetings_len_10() -> None:
    assert len(dg.default_greetings("zh-CN")) == 10
    assert len(dg.default_greetings("en-US")) == 10


def test_default_pet_bubble_greetings_len_10() -> None:
    assert len(dg.default_pet_bubble_greetings("zh-CN")) == 10
    assert len(dg.default_pet_bubble_greetings("en-US")) == 10


@pytest.mark.parametrize(
    "raw",
    [
        json.dumps([f"line {i}" for i in range(10)]),
        "```json\n" + json.dumps([f"x{i}" for i in range(10)]) + "\n```",
        'noise before ' + json.dumps([f"row{i}" for i in range(10)]) + ' trailing',
    ],
)
def test_parse_greeting_json_accepts(raw: str) -> None:
    out = dg._parse_greeting_json(raw)
    assert out is not None
    assert len(out) == 10


def test_parse_greeting_json_rejects_short() -> None:
    assert dg._parse_greeting_json(json.dumps(["only", "two"])) is None


@pytest.mark.asyncio
async def test_get_daily_greetings_without_llm_uses_defaults() -> None:
    day, lines = await dg.get_daily_greetings_for_locale(None, "zh-CN")
    assert day == dg._utc_day()
    assert lines == dg.default_greetings("zh-CN")


@pytest.mark.asyncio
async def test_get_daily_pet_bubble_greetings_without_llm_uses_defaults() -> None:
    day, lines = await dg.get_daily_pet_bubble_greetings(None, "en-US")
    assert day == dg._utc_day()
    assert lines == dg.default_pet_bubble_greetings("en-US")


@pytest.mark.asyncio
async def test_get_daily_pet_bubble_greetings_caches_per_day() -> None:
    day1, lines1 = await dg.get_daily_pet_bubble_greetings(None, "zh-CN")
    day2, lines2 = await dg.get_daily_pet_bubble_greetings(None, "zh-CN")
    assert day1 == day2
    assert lines1 == lines2
