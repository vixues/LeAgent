"""Tests for configure_settings agent tool."""

from __future__ import annotations

from uuid import uuid4

import pytest

from leagent.services.settings_plan import reset_settings_plan_registry
from leagent.tools.base import ToolContext
from leagent.tools.integration.configure_settings import ConfigureSettingsTool


@pytest.fixture(autouse=True)
def _reset_plans() -> None:
    reset_settings_plan_registry()
    yield
    reset_settings_plan_registry()


def _ctx() -> ToolContext:
    return ToolContext(
        session_id=str(uuid4()),
        user_id="test-user",
    )


@pytest.mark.asyncio
async def test_inspect_then_apply_env(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEAGENT_HOME", str(tmp_path))
    # Ensure apply writes under tmp home
    from leagent.services import settings_configure as sc

    monkeypatch.setattr(sc, "env_path", lambda: tmp_path / ".env")

    tool = ConfigureSettingsTool()
    ctx = _ctx()
    insp = await tool.execute(
        {
            "action": "inspect",
            "changes": [{"kind": "env", "key": "WEB_SEARCH_PROVIDER", "value": "searxng"}],
        },
        ctx,
    )
    assert insp["ok"] is True
    plan_id = insp["plan_id"]
    assert insp["summary"][0]["preview"] == "searxng"

    applied = await tool.execute({"action": "apply", "plan_id": plan_id}, ctx)
    assert applied["ok"] is True
    assert applied["updated"] >= 1
    assert (tmp_path / ".env").is_file()

    # plan consumed — second apply fails
    again = await tool.execute({"action": "apply", "plan_id": plan_id}, ctx)
    assert again["ok"] is False


@pytest.mark.asyncio
async def test_apply_without_plan_id() -> None:
    tool = ConfigureSettingsTool()
    out = await tool.execute({"action": "apply"}, _ctx())
    assert out["ok"] is False
    assert "plan_id" in out["error"]


@pytest.mark.asyncio
async def test_apply_rejects_tampered_changes(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEAGENT_HOME", str(tmp_path))
    from leagent.services import settings_configure as sc

    monkeypatch.setattr(sc, "env_path", lambda: tmp_path / ".env")

    tool = ConfigureSettingsTool()
    ctx = _ctx()
    insp = await tool.execute(
        {
            "action": "inspect",
            "changes": [{"kind": "env", "key": "WEB_SEARCH_PROVIDER", "value": "bing"}],
        },
        ctx,
    )
    plan_id = insp["plan_id"]
    bad = await tool.execute(
        {
            "action": "apply",
            "plan_id": plan_id,
            "changes": [{"kind": "env", "key": "WEB_SEARCH_PROVIDER", "value": "searxng"}],
        },
        ctx,
    )
    assert bad["ok"] is False
    assert "match" in bad["error"]
