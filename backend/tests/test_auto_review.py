"""Tests for the auto-review approval reviewer (Codex auto-review parity)."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from leagent.tools.approval import (
    PendingApproval,
    get_approval_store,
    reset_approval_store,
)
from leagent.tools.auto_review import (
    auto_review_decision,
    default_reviewer,
    normalize_reviewer,
    parse_auto_review_response,
)


@pytest.fixture(autouse=True)
def _fresh_store():
    reset_approval_store()
    yield
    reset_approval_store()


def _pending(tool: str = "danger_tool") -> PendingApproval:
    return PendingApproval(
        tool_call_id="c1",
        tool_name=tool,
        params_digest="deadbeef",
        reason="destructive",
        detail="{}",
    )


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"decision": "allow", "rationale": "safe"}', "allow"),
        ('{"decision": "deny", "rationale": "bad"}', "deny"),
        ('{"decision": "escalate"}', "escalate"),
        ('```json\n{"decision": "allow"}\n```', "allow"),
        ('prefix {"decision": "deny"} suffix', "deny"),
        ("", "escalate"),
        ("not json at all", "escalate"),
        ('{"decision": "maybe"}', "escalate"),
    ],
)
def test_parse_auto_review_response(raw, expected):
    decision, _ = parse_auto_review_response(raw)
    assert decision == expected


# ---------------------------------------------------------------------------
# Reviewer setting
# ---------------------------------------------------------------------------


def test_default_reviewer_is_user(monkeypatch):
    monkeypatch.delenv("LEAGENT_APPROVALS_REVIEWER", raising=False)
    assert default_reviewer() == "user"


def test_reviewer_env_override(monkeypatch):
    monkeypatch.setenv("LEAGENT_APPROVALS_REVIEWER", "auto_review")
    assert default_reviewer() == "auto_review"


def test_normalize_reviewer_rejects_unknown():
    with pytest.raises(ValueError):
        normalize_reviewer("robot")


def test_store_reviewer_roundtrip():
    sid = str(uuid4())
    store = get_approval_store()
    assert store.get_reviewer(sid) == "user"
    store.set_reviewer(sid, "auto_review")
    assert store.get_reviewer(sid) == "auto_review"
    store.clear_session(sid)
    assert store.get_reviewer(sid) == "user"


# ---------------------------------------------------------------------------
# auto_review_decision with a stubbed LLM service
# ---------------------------------------------------------------------------


class _StubLLM:
    def __init__(self, content: str | Exception) -> None:
        self._content = content
        self.calls: list[dict] = []

    async def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        if isinstance(self._content, Exception):
            raise self._content
        return {"content": self._content}


@pytest.mark.asyncio
async def test_auto_review_allow():
    llm = _StubLLM('{"decision": "allow", "rationale": "tests are safe"}')
    sm = SimpleNamespace(llm_service=llm)
    decision, rationale = await auto_review_decision(_pending(), {}, service_manager=sm)
    assert decision == "allow"
    assert "safe" in rationale
    assert llm.calls, "reviewer LLM should be invoked"


@pytest.mark.asyncio
async def test_auto_review_llm_error_escalates():
    llm = _StubLLM(RuntimeError("provider down"))
    sm = SimpleNamespace(llm_service=llm)
    decision, _ = await auto_review_decision(_pending(), {}, service_manager=sm)
    assert decision == "escalate"


@pytest.mark.asyncio
async def test_auto_review_no_llm_escalates():
    sm = SimpleNamespace(llm_service=None)
    decision, _ = await auto_review_decision(_pending(), {}, service_manager=sm)
    assert decision == "escalate"


# ---------------------------------------------------------------------------
# Query-loop integration: _auto_review_resolved
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_review_resolved_grants_once(monkeypatch):
    from leagent.agent import query as query_mod

    sid = str(uuid4())
    store = get_approval_store()
    store.set_reviewer(sid, "auto_review")

    async def _fake_decision(pending, params, *, service_manager=None):
        return "allow", "fine"

    monkeypatch.setattr(
        "leagent.tools.auto_review.auto_review_decision", _fake_decision,
    )

    ctx = SimpleNamespace(session_id=sid, user_id=None, executor=None)
    resolved = await query_mod._auto_review_resolved(_pending(), {}, ctx)
    assert resolved
    assert store.is_granted(sid, "danger_tool")


@pytest.mark.asyncio
async def test_auto_review_resolved_escalates_to_user(monkeypatch):
    from leagent.agent import query as query_mod

    sid = str(uuid4())
    store = get_approval_store()
    store.set_reviewer(sid, "auto_review")

    async def _fake_decision(pending, params, *, service_manager=None):
        return "escalate", "not sure"

    monkeypatch.setattr(
        "leagent.tools.auto_review.auto_review_decision", _fake_decision,
    )

    ctx = SimpleNamespace(session_id=sid, user_id=None, executor=None)
    resolved = await query_mod._auto_review_resolved(_pending(), {}, ctx)
    assert not resolved
    assert not store.is_granted(sid, "danger_tool")


@pytest.mark.asyncio
async def test_auto_review_skipped_when_reviewer_is_user():
    from leagent.agent import query as query_mod

    sid = str(uuid4())
    ctx = SimpleNamespace(session_id=sid, user_id=None, executor=None)
    resolved = await query_mod._auto_review_resolved(_pending(), {}, ctx)
    assert not resolved
