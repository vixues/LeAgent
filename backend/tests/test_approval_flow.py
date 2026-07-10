"""Tests for the Codex-style approval flow (pause instead of fail-closed)."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from leagent.tools import approval as approval_mod
from leagent.tools.approval import (
    ApprovalStore,
    PendingApproval,
    approval_reply_content,
    build_approval_question,
    get_approval_store,
    parse_approval_decision,
    reset_approval_store,
)
from leagent.tools.base import (
    BaseTool,
    ToolCategory,
    ToolContext,
    ToolPermissionContext,
    ToolResult,
    check_tool_permission,
)


@pytest.fixture(autouse=True)
def _fresh_store():
    reset_approval_store()
    yield
    reset_approval_store()


class _DestructiveTool(BaseTool):
    name = "danger_tool"
    description = "test"
    category = ToolCategory.UTIL
    is_destructive = True
    is_read_only = False
    parameters = {"type": "object", "properties": {}}

    async def execute(self, params, context):
        return ToolResult.ok({"ran": True})


class _ReadTool(BaseTool):
    name = "read_tool"
    description = "test"
    category = ToolCategory.UTIL
    is_destructive = False
    is_read_only = True
    parameters = {"type": "object", "properties": {}}

    async def execute(self, params, context):
        return ToolResult.ok({"ran": True})


def _ctx(session_id=None) -> ToolContext:
    return ToolContext(user_id=None, session_id=session_id)


# ---------------------------------------------------------------------------
# check_tool_permission: needs_approval semantics
# ---------------------------------------------------------------------------


def test_ask_rule_needs_approval():
    perm_ctx = ToolPermissionContext(always_ask_rules=["danger_*"])
    res = check_tool_permission(_DestructiveTool(), {}, perm_ctx, _ctx())
    assert not res.allowed
    assert res.needs_approval


def test_confirm_destructive_needs_approval():
    perm_ctx = ToolPermissionContext(confirm_destructive=True)
    res = check_tool_permission(_DestructiveTool(), {}, perm_ctx, _ctx())
    assert not res.allowed
    assert res.needs_approval


def test_policy_never_skips_approval():
    sid = uuid4()
    get_approval_store().set_policy(str(sid), "never")
    perm_ctx = ToolPermissionContext(confirm_destructive=True)
    res = check_tool_permission(_DestructiveTool(), {}, perm_ctx, _ctx(sid))
    assert res.allowed


def test_policy_untrusted_gates_non_readonly():
    sid = uuid4()
    get_approval_store().set_policy(str(sid), "untrusted")
    perm_ctx = ToolPermissionContext()
    res = check_tool_permission(_DestructiveTool(), {}, perm_ctx, _ctx(sid))
    assert not res.allowed and res.needs_approval
    # read-only tools flow through
    res2 = check_tool_permission(_ReadTool(), {}, perm_ctx, _ctx(sid))
    assert res2.allowed


def test_session_grant_allows_through():
    sid = uuid4()
    get_approval_store().grant(str(sid), "danger_tool", scope="session")
    perm_ctx = ToolPermissionContext(confirm_destructive=True)
    res = check_tool_permission(_DestructiveTool(), {}, perm_ctx, _ctx(sid))
    assert res.allowed


def test_once_grant_is_consumed():
    sid = uuid4()
    store = get_approval_store()
    store.grant(str(sid), "danger_tool", scope="once")
    perm_ctx = ToolPermissionContext(confirm_destructive=True)
    assert check_tool_permission(_DestructiveTool(), {}, perm_ctx, _ctx(sid)).allowed
    # consumed: second call needs approval again
    res = check_tool_permission(_DestructiveTool(), {}, perm_ctx, _ctx(sid))
    assert not res.allowed and res.needs_approval


def test_deny_rule_is_hard_deny_not_approval():
    perm_ctx = ToolPermissionContext(always_deny_rules=["danger_*"])
    res = check_tool_permission(_DestructiveTool(), {}, perm_ctx, _ctx())
    assert not res.allowed
    assert not res.needs_approval


# ---------------------------------------------------------------------------
# Decision parsing / reply synthesis
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "content,expected",
    [
        ("Allow once", "allow_once"),
        ("allow", "allow_once"),
        ("Allow for session", "allow_session"),
        ("Deny", "deny"),
        ("拒绝", "deny"),
        ('{"decision": "allow_session"}', "allow_session"),
        ('{"answers": {"approval::x": "Deny"}}', "deny"),
        ("", None),
        ("what does this command do?", None),
    ],
)
def test_parse_approval_decision(content, expected):
    assert parse_approval_decision(content) == expected


def test_reply_content_shapes():
    allow = json.loads(approval_reply_content("allow_once", "project_shell"))
    assert allow["approval_decision"] == "allow_once"
    assert "Re-issue" in allow["note"]
    deny = json.loads(approval_reply_content("deny", "project_shell"))
    assert deny["approval_decision"] == "deny"
    assert "Do not retry" in deny["note"]


def test_build_approval_question_shape():
    q = build_approval_question(
        tool_call_id="call_1", tool_name="project_shell", reason="destructive",
    )
    assert q["id"] == "approval::call_1"
    assert q["ui_variant"] == "permission"
    assert "Allow once" in q["choices"] and "Deny" in q["choices"]


# ---------------------------------------------------------------------------
# ApprovalStore pending lifecycle
# ---------------------------------------------------------------------------


def test_pending_lifecycle():
    store = ApprovalStore()
    p = PendingApproval(
        tool_call_id="c1", tool_name="t", params_digest="d", reason="r",
    )
    store.set_pending("s1", p)
    assert store.get_pending("s1") is p
    assert store.pop_pending("s1", tool_call_id="other") is None
    assert store.pop_pending("s1", tool_call_id="c1") is p
    assert store.get_pending("s1") is None


# ---------------------------------------------------------------------------
# Chat reply transformation
# ---------------------------------------------------------------------------


def test_transform_approval_reply_allow_session():
    from leagent.api.v1.chat.approvals import transform_approval_reply

    sid = uuid4()
    store = get_approval_store()
    pending = PendingApproval(
        tool_call_id="call_9", tool_name="project_shell",
        params_digest="abc", reason="destructive",
    )
    store.set_pending(str(sid), pending)

    content, out_pending, decision = transform_approval_reply(
        sid, {"tool_call_id": "call_9", "content": "Allow for session"},
    )
    assert out_pending is pending
    assert decision == "allow_session"
    assert json.loads(content)["approval_decision"] == "allow_session"
    # grant recorded
    assert store.is_granted(str(sid), "project_shell")
    # pending cleared
    assert store.get_pending(str(sid)) is None


def test_transform_non_approval_reply_passthrough():
    from leagent.api.v1.chat.approvals import transform_approval_reply

    sid = uuid4()
    content, pending, decision = transform_approval_reply(
        sid, {"tool_call_id": "call_1", "content": "my answer"},
    )
    assert content == "my answer"
    assert pending is None and decision is None


# ---------------------------------------------------------------------------
# Query-loop approval pause terminal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approval_pause_terminal_emitted():
    import asyncio

    from leagent.agent.query import _approval_pause_terminal
    from leagent.agent.tool_use_context import ToolUseContext
    from leagent.context.file_state import FileState
    from leagent.tools.executor import ToolExecutor
    from leagent.tools.registry import ToolRegistry

    registry = ToolRegistry()
    registry.register(_DestructiveTool())
    executor = ToolExecutor(
        registry=registry,
        service_manager=None,
        permission_context=ToolPermissionContext(confirm_destructive=True),
    )
    sid = uuid4()
    ctx = ToolUseContext(
        abort_event=asyncio.Event(),
        tools=registry,
        executor=executor,
        file_state_cache=FileState(),
        session_id=sid,
    )
    calls = [{"id": "call_a", "name": "danger_tool", "arguments": {}}]
    terminal = await _approval_pause_terminal(calls, ctx, turn_count=1, usage={})
    assert terminal is not None
    meta = terminal.meta
    assert meta["tool_call"]["id"] == "call_a"
    assert meta["questions"][0]["ui_variant"] == "permission"
    assert meta["approval_request"]["tool_name"] == "danger_tool"
    # pending recorded for the session
    assert get_approval_store().get_pending(str(sid)).tool_call_id == "call_a"


@pytest.mark.asyncio
async def test_no_pause_for_allowed_tool():
    import asyncio

    from leagent.agent.query import _approval_pause_terminal
    from leagent.agent.tool_use_context import ToolUseContext
    from leagent.context.file_state import FileState
    from leagent.tools.executor import ToolExecutor
    from leagent.tools.registry import ToolRegistry

    registry = ToolRegistry()
    registry.register(_ReadTool())
    executor = ToolExecutor(
        registry=registry,
        service_manager=None,
        permission_context=ToolPermissionContext(confirm_destructive=True),
    )
    ctx = ToolUseContext(
        abort_event=asyncio.Event(),
        tools=registry,
        executor=executor,
        file_state_cache=FileState(),
        session_id=uuid4(),
    )
    calls = [{"id": "call_b", "name": "read_tool", "arguments": {}}]
    assert await _approval_pause_terminal(calls, ctx, turn_count=1, usage={}) is None
