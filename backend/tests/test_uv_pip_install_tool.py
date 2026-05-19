"""Tests for :class:`~leagent.tools.code.uv_pip_install.UvPipInstallTool`."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_uv_pip_install_disabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from leagent.config import settings as settings_module
    from leagent.tools.base import ToolContext
    from leagent.tools.code.execution import CodeExecutionConfig
    from leagent.tools.code.uv_pip_install import UvPipInstallTool

    settings = settings_module.get_settings()
    monkeypatch.setattr(settings, "agent_uv_pip_install_enabled", False)

    tool = UvPipInstallTool(
        config=CodeExecutionConfig(workspace_root=str(tmp_path / "ws")),
    )
    ctx = ToolContext(user_id="u", session_id="s")
    out = await tool.execute({"packages": ["setuptools"]}, ctx)
    assert out["status"] == "error"
    assert "disabled" in str(out.get("error", "")).lower()


@pytest.mark.asyncio
async def test_uv_pip_install_requires_packages_or_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from leagent.config import settings as settings_module
    from leagent.tools.base import ToolContext
    from leagent.tools.code.execution import CodeExecutionConfig
    from leagent.tools.code.uv_pip_install import UvPipInstallTool

    settings = settings_module.get_settings()
    monkeypatch.setattr(settings, "agent_uv_pip_install_enabled", True)

    tool = UvPipInstallTool(
        config=CodeExecutionConfig(workspace_root=str(tmp_path / "ws")),
    )
    ctx = ToolContext(user_id="u", session_id="s")
    out = await tool.execute({"packages": []}, ctx)
    assert out["status"] == "error"
    assert "at least one" in str(out.get("error", "")).lower()


@pytest.mark.asyncio
async def test_uv_pip_install_invokes_run_uv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from leagent.config import settings as settings_module
    from leagent.tools.base import ToolContext
    from leagent.tools.code.execution import CodeExecutionConfig
    from leagent.tools.code import uv_pip_install as mod
    from leagent.tools.code.uv_pip_install import UvPipInstallTool

    settings = settings_module.get_settings()
    monkeypatch.setattr(settings, "agent_uv_pip_install_enabled", True)

    captured: dict[str, object] = {}

    async def _fake_run(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"ok": True, "stdout": "installed", "stderr": "", "returncode": 0}

    monkeypatch.setattr(mod, "run_uv_pip_install", _fake_run)
    monkeypatch.setattr(mod, "resolve_backend_python_executable", lambda: "/venv/bin/python")

    tool = UvPipInstallTool(
        config=CodeExecutionConfig(workspace_root=str(tmp_path / "ws")),
    )
    ctx = ToolContext(user_id="u", session_id="sess-1")
    out = await tool.execute({"packages": ["setuptools", "pandas"]}, ctx)

    assert out["status"] == "ok"
    assert out.get("ok") is True
    assert captured.get("packages") == ["setuptools", "pandas"]
    assert captured.get("requirements_file") is None
    assert captured.get("python_executable") == "/venv/bin/python"
    assert float(captured.get("timeout_sec", 0)) > 0


def test_code_execution_tool_uses_resolved_python(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from leagent.tools.code import execution as mod
    from leagent.tools.code.execution import CodeExecutionConfig, CodeExecutionTool

    monkeypatch.setattr(mod, "resolve_backend_python_executable", lambda: "/venv/bin/python")

    tool = CodeExecutionTool(
        config=CodeExecutionConfig(workspace_root=str(tmp_path / "ws")),
    )

    assert tool._sandbox._python == "/venv/bin/python"


@pytest.mark.asyncio
async def test_run_uv_pip_install_requires_content() -> None:
    from leagent.skills.python_deps import run_uv_pip_install

    out = await run_uv_pip_install(
        python_executable="/usr/bin/python3",
        packages=[],
        requirements_file=None,
        timeout_sec=30.0,
    )
    assert out.get("ok") is False
