"""Runtime approval system (Codex-style approval policies).

Bridges the gap between the static permission check
(:func:`leagent.tools.base.check_tool_permission`) and the chat UI's
``ask_user`` permission card: instead of fail-closed denials, tools that
*need approval* pause the turn (``AWAITING_USER_INPUT``), surface an
Allow/Deny card, and resume once the user decides.

Pieces:

* :class:`ApprovalStore` — in-process, per-session state: approval
  policy (``untrusted`` / ``on-request`` / ``never``), session-scoped
  grants, one-shot grants, and the pending approval request while a
  turn is paused. Single-worker semantics, consistent with
  ``ExecutionRunRegistry``.
* :func:`parse_approval_decision` — normalise an Allow/Deny reply.
* :func:`approval_reply_content` — the structured tool-row body the
  model sees after the user decides (so it re-issues or abandons the
  call).

Durable audit lives in the ``approval_decisions`` table (see
``leagent.db.models.approval_decision``); this module is the hot path.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Literal

import structlog

logger = structlog.get_logger(__name__)

ApprovalPolicy = Literal["untrusted", "on-request", "never"]
ApprovalDecision = Literal["allow_once", "allow_session", "deny"]

_VALID_POLICIES: frozenset[str] = frozenset({"untrusted", "on-request", "never"})

#: Sentinel prefix for synthesized approval question ids.
APPROVAL_QUESTION_PREFIX = "approval::"


def default_approval_policy() -> str:
    raw = os.environ.get("LEAGENT_APPROVAL_POLICY", "").strip().lower()
    if raw in _VALID_POLICIES:
        return raw
    return "on-request"


def params_digest(params: dict[str, Any] | None) -> str:
    """Stable short digest of tool params for grant matching / audit."""
    try:
        blob = json.dumps(params or {}, sort_keys=True, default=str)[:20_000]
    except Exception:  # noqa: BLE001
        blob = repr(params)[:20_000]
    return hashlib.sha256(blob.encode("utf-8", "replace")).hexdigest()[:16]


@dataclass
class PendingApproval:
    """The approval request that paused a turn."""

    tool_call_id: str
    tool_name: str
    params_digest: str
    reason: str
    detail: str = ""
    created_at: float = field(default_factory=time.time)

    def to_meta(self) -> dict[str, Any]:
        return {
            "tool_call_id": self.tool_call_id,
            "tool_name": self.tool_name,
            "params_digest": self.params_digest,
            "reason": self.reason,
            "detail": self.detail,
        }


class ApprovalStore:
    """Per-session approval state (policies, grants, pending requests)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._policies: dict[str, str] = {}
        self._reviewers: dict[str, str] = {}
        self._session_grants: dict[str, set[str]] = {}
        self._once_grants: dict[str, set[str]] = {}
        self._pending: dict[str, PendingApproval] = {}

    # -- policy ---------------------------------------------------------

    def set_policy(self, session_id: str, policy: str) -> None:
        policy = (policy or "").strip().lower()
        if policy not in _VALID_POLICIES:
            raise ValueError(f"Unknown approval policy {policy!r}")
        with self._lock:
            self._policies[str(session_id)] = policy

    def get_policy(self, session_id: str | None) -> str:
        if session_id is None:
            return default_approval_policy()
        with self._lock:
            return self._policies.get(str(session_id), default_approval_policy())

    # -- reviewer ---------------------------------------------------------

    def set_reviewer(self, session_id: str, reviewer: str) -> None:
        from leagent.tools.auto_review import normalize_reviewer

        with self._lock:
            self._reviewers[str(session_id)] = normalize_reviewer(reviewer)

    def get_reviewer(self, session_id: str | None) -> str:
        from leagent.tools.auto_review import default_reviewer

        if session_id is None:
            return default_reviewer()
        with self._lock:
            return self._reviewers.get(str(session_id), default_reviewer())

    # -- grants ---------------------------------------------------------

    def grant(
        self,
        session_id: str,
        tool_name: str,
        *,
        scope: Literal["once", "session"],
    ) -> None:
        sid = str(session_id)
        with self._lock:
            if scope == "session":
                self._session_grants.setdefault(sid, set()).add(tool_name)
            else:
                self._once_grants.setdefault(sid, set()).add(tool_name)

    def is_granted(self, session_id: str | None, tool_name: str) -> bool:
        """Check (and consume, for one-shot) an existing grant."""
        if session_id is None:
            return False
        sid = str(session_id)
        with self._lock:
            if tool_name in self._session_grants.get(sid, ()):
                return True
            once = self._once_grants.get(sid)
            if once and tool_name in once:
                once.discard(tool_name)
                return True
        return False

    # -- pending request ------------------------------------------------

    def set_pending(self, session_id: str, request: PendingApproval) -> None:
        with self._lock:
            self._pending[str(session_id)] = request

    def get_pending(self, session_id: str | None) -> PendingApproval | None:
        if session_id is None:
            return None
        with self._lock:
            return self._pending.get(str(session_id))

    def pop_pending(
        self, session_id: str | None, *, tool_call_id: str | None = None,
    ) -> PendingApproval | None:
        if session_id is None:
            return None
        sid = str(session_id)
        with self._lock:
            pending = self._pending.get(sid)
            if pending is None:
                return None
            if tool_call_id is not None and pending.tool_call_id != tool_call_id:
                return None
            return self._pending.pop(sid, None)

    def clear_session(self, session_id: str) -> None:
        sid = str(session_id)
        with self._lock:
            self._policies.pop(sid, None)
            self._reviewers.pop(sid, None)
            self._session_grants.pop(sid, None)
            self._once_grants.pop(sid, None)
            self._pending.pop(sid, None)


_STORE: ApprovalStore | None = None


def get_approval_store() -> ApprovalStore:
    global _STORE
    if _STORE is None:
        _STORE = ApprovalStore()
    return _STORE


def reset_approval_store() -> None:
    """Testing hook."""
    global _STORE
    _STORE = None


# ---------------------------------------------------------------------------
# Decision parsing + reply synthesis
# ---------------------------------------------------------------------------

_ALLOW_ONCE_TOKENS = frozenset({
    "allow", "allow once", "allow_once", "approve", "approved", "yes",
    "允许", "允许一次", "批准",
})
_ALLOW_SESSION_TOKENS = frozenset({
    "allow for session", "allow_session", "always allow", "allow always",
    "本会话允许", "始终允许",
})
_DENY_TOKENS = frozenset({
    "deny", "denied", "reject", "rejected", "no", "拒绝", "不允许",
})


def parse_approval_decision(content: str | None) -> ApprovalDecision | None:
    """Map a user's approval-card reply onto a decision."""
    raw = (content or "").strip()
    if not raw:
        return None
    # Structured JSON answers ({"decision": "allow_once"} or ask_user-shaped)
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            cand = data.get("decision") or data.get("answer") or data.get("value")
            if isinstance(cand, str):
                raw = cand
            elif isinstance(data.get("answers"), dict) and data["answers"]:
                first = next(iter(data["answers"].values()))
                if isinstance(first, str):
                    raw = first
    token = raw.strip().lower()
    if token in _ALLOW_SESSION_TOKENS:
        return "allow_session"
    if token in _ALLOW_ONCE_TOKENS:
        return "allow_once"
    if token in _DENY_TOKENS:
        return "deny"
    return None


def approval_reply_content(decision: ApprovalDecision, tool_name: str) -> str:
    """Tool-row body the model sees after the decision.

    Approval pauses leave a ``_wa_pending`` tool row for the *gated*
    call; this content replaces it so the model knows whether to
    re-issue the call (now granted) or abandon it.
    """
    if decision == "deny":
        return json.dumps({
            "approval_decision": "deny",
            "note": (
                f"The user DENIED running `{tool_name}`. Do not retry this "
                "call. Explain the situation or propose an alternative."
            ),
        })
    scope = "for this session" if decision == "allow_session" else "once"
    return json.dumps({
        "approval_decision": decision,
        "note": (
            f"The user APPROVED running `{tool_name}` ({scope}). "
            "Re-issue the exact same tool call now; it will execute."
        ),
    })


def build_approval_question(
    *,
    tool_call_id: str,
    tool_name: str,
    reason: str,
    detail: str = "",
) -> dict[str, Any]:
    """Synthesize an ask_user-shaped permission question for the UI."""
    return {
        "id": f"{APPROVAL_QUESTION_PREFIX}{tool_call_id}",
        "prompt": f"Allow the agent to run `{tool_name}`?",
        "choices": ["Allow once", "Allow for session", "Deny"],
        "allow_custom": False,
        "multi_select": False,
        "ui_variant": "permission",
        "permission_kind": "tool_run",
        "detail": (detail or reason)[:500],
        "primary_choice": "Allow once",
        "secondary_choice": "Deny",
    }
