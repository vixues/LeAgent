"""Tests for settings_configure service."""

from __future__ import annotations

import os

import pytest

from leagent.services.settings_configure import (
    SettingsConfigureError,
    apply_env_changes,
    inspect_changes,
    mask_secret,
    validate_env_updates,
)


def test_mask_secret() -> None:
    assert mask_secret("sk-abcdefghijklmnop") == "****mnop"
    assert mask_secret("", unset=True) == "(unset)"
    assert mask_secret("ab") == "****"


def test_validate_rejects_unknown_key() -> None:
    with pytest.raises(SettingsConfigureError, match="Unsupported"):
        validate_env_updates({"NOT_ALLOWED": "x"})


def test_validate_rejects_bad_deepseek() -> None:
    with pytest.raises(SettingsConfigureError, match="DEEPSEEK"):
        validate_env_updates({"DEEPSEEK_API_KEY": "not-a-key"})


def test_inspect_env_redacts_secret() -> None:
    insp = inspect_changes(
        [{"kind": "env", "key": "DEEPSEEK_API_KEY", "value": "sk-abcdefghijklmnop"}]
    )
    assert insp.ok
    assert len(insp.summary) == 1
    assert "sk-abc" not in insp.summary[0].preview
    assert insp.summary[0].preview.endswith("mnop")


def test_inspect_mcp_requires_command() -> None:
    insp = inspect_changes([{"kind": "mcp", "name": "fs", "transport": "stdio"}])
    assert not insp.ok
    assert any("command" in e for e in insp.errors)


def test_inspect_channel() -> None:
    insp = inspect_changes(
        [
            {
                "kind": "channel",
                "name": "dingtalk",
                "enabled": True,
                "config": {
                    "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=secrettoken"
                },
            }
        ]
    )
    assert insp.ok
    assert insp.summary[0].kind == "channel"
    assert "secrettoken" not in insp.summary[0].preview


@pytest.mark.asyncio
async def test_apply_env_changes(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    monkeypatch.delenv("WEB_SEARCH_PROVIDER", raising=False)
    result = await apply_env_changes(
        {"WEB_SEARCH_PROVIDER": "bing"},
        path=env_file,
    )
    assert result.ok
    assert result.updated == 1
    assert os.environ.get("WEB_SEARCH_PROVIDER") == "bing"
    assert "WEB_SEARCH_PROVIDER" in env_file.read_text(encoding="utf-8")
