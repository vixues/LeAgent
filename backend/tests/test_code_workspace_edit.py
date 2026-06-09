"""Tests for code_workspace_edit tool."""

import pytest


@pytest.mark.asyncio
async def test_code_workspace_edit_patches_last_source(tmp_path) -> None:
    from leagent.tools.base import ToolContext
    from leagent.code.execution import CodeExecutionConfig, CodeExecutionTool
    from leagent.code.workspace_edit import CodeWorkspaceEditTool

    ws_root = tmp_path / "ws"
    cfg = CodeExecutionConfig(workspace_root=str(ws_root))
    exec_tool = CodeExecutionTool(config=cfg)
    edit_tool = CodeWorkspaceEditTool(config=cfg)
    ctx = ToolContext(user_id="u", session_id="sess-edit")

    broken = "def broken(\n    pass\n"
    res = await exec_tool.run({"source": broken}, ctx)
    assert res.success is False

    edit_res = await edit_tool.run(
        {
            "path": "__last_source__.py",
            "old_string": "def broken(",
            "new_string": "def fixed():",
        },
        ctx,
    )
    assert edit_res.success, edit_res.error
    assert edit_res.data["replacements"] == 1

    rerun = await exec_tool.run(
        {"workspace_file": "__last_source__.py", "timeout_sec": 10.0},
        ctx,
    )
    assert rerun.success, rerun.error


@pytest.mark.asyncio
async def test_code_execution_syntax_error_exposes_repair_envelope(tmp_path) -> None:
    """Syntax failures must persist source and expose repair_workflow."""
    from leagent.tools.base import ToolContext
    from leagent.code.execution import CodeExecutionConfig, CodeExecutionTool
    from leagent.code.workspace_edit import CodeWorkspaceEditTool

    ws_root = tmp_path / "ws"
    cfg = CodeExecutionConfig(workspace_root=str(ws_root))
    exec_tool = CodeExecutionTool(config=cfg)
    edit_tool = CodeWorkspaceEditTool(config=cfg)
    ctx = ToolContext(user_id="u", session_id="sess-envelope")

    broken = "def add_values():\n    return 17 + 25\n\nprint(add_values()\n"
    res = await exec_tool.run({"source": broken}, ctx)
    assert res.success is False, res.error

    data = res.data if isinstance(res.data, dict) else {}
    assert data.get("workspace_file") == "__last_source__.py"
    assert data.get("repair_workflow")

    edit_res = await edit_tool.run(
        {
            "path": "__last_source__.py",
            "old_string": "print(add_values()",
            "new_string": "print(add_values())",
        },
        ctx,
    )
    assert edit_res.success, edit_res.error

    rerun = await exec_tool.run(
        {"workspace_file": "__last_source__.py", "timeout_sec": 15.0},
        ctx,
    )
    assert rerun.success, rerun.error
    assert "42" in ((rerun.data or {}).get("stdout") or "")


@pytest.mark.asyncio
async def test_code_workspace_edit_no_match_returns_patch_hint(tmp_path) -> None:
    from leagent.tools.base import ToolContext
    from leagent.code.execution import CodeExecutionConfig, CodeExecutionTool
    from leagent.code.workspace_edit import CodeWorkspaceEditTool

    ws_root = tmp_path / "ws"
    cfg = CodeExecutionConfig(workspace_root=str(ws_root))
    exec_tool = CodeExecutionTool(config=cfg)
    edit_tool = CodeWorkspaceEditTool(config=cfg)
    ctx = ToolContext(user_id="u", session_id="sess-hint")

    await exec_tool.run({"source": "x = 1\n"}, ctx)
    res = await edit_tool.run(
        {
            "old_string": "missing token",
            "new_string": "y = 2",
        },
        ctx,
    )
    assert res.success is False
    assert isinstance(res.data, dict)
    assert res.data.get("patch_hint")
