"""Tests for executor-enforced plan mode (read-only gate + exit approval)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from leagent.agent.control import (
    get_session_control_registry,
    reset_session_control_registry,
)
from leagent.tools.approval import get_approval_store, reset_approval_store
from leagent.tools.base import (
    BaseTool,
    ToolCategory,
    ToolContext,
    ToolPermissionContext,
    ToolResult,
    check_tool_permission,
)
from leagent.tools.util.plan_tools import EnterPlanModeTool, ExitPlanModeTool


@pytest.fixture(autouse=True)
def _fresh_state():
    reset_session_control_registry()
    reset_approval_store()
    yield
    reset_session_control_registry()
    reset_approval_store()


class _MutatingTool(BaseTool):
    name = "write_tool"
    description = "test"
    category = ToolCategory.UTIL
    is_read_only = False
    parameters = {"type": "object", "properties": {}}

    async def execute(self, params, context):
        return ToolResult.ok({"ran": True})


class _ReadTool(BaseTool):
    name = "read_tool"
    description = "test"
    category = ToolCategory.UTIL
    is_read_only = True
    parameters = {"type": "object", "properties": {}}

    async def execute(self, params, context):
        return ToolResult.ok({"ran": True})


class _ExitPlanStub(BaseTool):
    name = "exit_plan_mode"
    description = "test"
    category = ToolCategory.UTIL
    is_read_only = True
    parameters = {"type": "object", "properties": {}}

    async def execute(self, params, context):
        return ToolResult.ok({"ran": True})


def _ctx(session_id=None, plan_mode=False) -> ToolContext:
    ctx = ToolContext(user_id=None, session_id=session_id)
    if plan_mode:
        ctx.extra["plan_mode"] = True
    return ctx


def test_no_plan_mode_mutating_tool_allowed():
    res = check_tool_permission(_MutatingTool(), {}, ToolPermissionContext(), _ctx())
    assert res.allowed


def test_plan_mode_blocks_mutating_tool():
    res = check_tool_permission(
        _MutatingTool(), {}, ToolPermissionContext(), _ctx(plan_mode=True),
    )
    assert not res.allowed
    assert not res.needs_approval
    assert "Plan mode" in (res.reason or "")


def test_plan_mode_allows_read_only_tool():
    res = check_tool_permission(
        _ReadTool(), {}, ToolPermissionContext(), _ctx(plan_mode=True),
    )
    assert res.allowed


def test_plan_mode_registry_flag_gates_without_extra():
    sid = uuid4()
    get_session_control_registry().set_plan_mode(str(sid), True)
    res = check_tool_permission(_MutatingTool(), {}, ToolPermissionContext(), _ctx(sid))
    assert not res.allowed


def test_plan_mode_allowlist_todo_write():
    class _TodoWrite(_MutatingTool):
        name = "todo_write"

    res = check_tool_permission(
        _TodoWrite(), {}, ToolPermissionContext(), _ctx(plan_mode=True),
    )
    assert res.allowed


def test_exit_plan_mode_needs_approval():
    sid = uuid4()
    res = check_tool_permission(
        _ExitPlanStub(), {}, ToolPermissionContext(), _ctx(sid, plan_mode=True),
    )
    assert not res.allowed
    assert res.needs_approval


def test_exit_plan_mode_allowed_after_grant():
    sid = uuid4()
    get_approval_store().grant(str(sid), "exit_plan_mode", scope="once")
    res = check_tool_permission(
        _ExitPlanStub(), {}, ToolPermissionContext(), _ctx(sid, plan_mode=True),
    )
    assert res.allowed


def test_exit_plan_mode_allowed_when_policy_never():
    sid = uuid4()
    get_approval_store().set_policy(str(sid), "never")
    res = check_tool_permission(
        _ExitPlanStub(), {}, ToolPermissionContext(), _ctx(sid, plan_mode=True),
    )
    assert res.allowed


@pytest.mark.asyncio
async def test_enter_exit_tools_toggle_registry_flag():
    sid = str(uuid4())
    reg = get_session_control_registry()

    enter = EnterPlanModeTool()
    ctx = ToolContext(user_id=None, session_id=sid)
    await enter.execute({}, ctx)
    assert reg.plan_mode_active(sid)

    exit_tool = ExitPlanModeTool()
    await exit_tool.execute({}, ctx)
    assert not reg.plan_mode_active(sid)
