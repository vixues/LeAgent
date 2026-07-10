"""Auto-review reviewer for tool approval requests (Codex auto-review parity).

When a session sets ``approvals_reviewer = auto_review``, approval requests
are first shown to a cheap-model reviewer instead of immediately pausing the
turn. The reviewer sees the tool name, a parameter summary, and the gating
reason, and answers with exactly one of:

* ``allow`` — grant the call once and let the batch proceed,
* ``deny`` — refuse the call (fail-closed, the model sees the denial),
* ``escalate`` — fall back to the human Allow/Deny card.

Any parse/transport failure escalates to the user (fail-safe). Every
auto-review decision is written to the ``approval_decisions`` audit table
with ``decided_by="auto_review"``.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any, Literal

import structlog

if TYPE_CHECKING:
    from leagent.tools.approval import PendingApproval

logger = structlog.get_logger(__name__)

ReviewerKind = Literal["user", "auto_review"]
AutoReviewDecision = Literal["allow", "deny", "escalate"]

_VALID_REVIEWERS: frozenset[str] = frozenset({"user", "auto_review"})

_SYSTEM_PROMPT = """\
You are a security reviewer for an AI agent's tool calls. A tool call was
flagged for approval. Decide whether it is safe to run WITHOUT asking the
human operator.

Rules:
- "allow" only for clearly safe, reversible operations that match the
  session's apparent intent (e.g. running tests, formatting, reading data).
- "deny" for calls that are clearly unsafe or destructive with no sign of
  user intent (e.g. deleting files outside the workspace, exfiltrating
  secrets, disabling security controls).
- "escalate" whenever you are unsure, the blast radius is large, or the
  action is irreversible (credential changes, force pushes, rm -rf, sending
  emails/messages, payments).

Respond with ONLY a JSON object: {"decision": "allow"|"deny"|"escalate",
"rationale": "<one short sentence>"}."""


def default_reviewer() -> str:
    raw = os.environ.get("LEAGENT_APPROVALS_REVIEWER", "").strip().lower()
    if raw in _VALID_REVIEWERS:
        return raw
    return "user"


def normalize_reviewer(value: str | None) -> str:
    raw = (value or "").strip().lower()
    if raw in _VALID_REVIEWERS:
        return raw
    raise ValueError(f"Unknown approvals reviewer {value!r}; expected one of {sorted(_VALID_REVIEWERS)}")


def parse_auto_review_response(content: str | None) -> tuple[AutoReviewDecision, str]:
    """Parse the reviewer model's JSON reply; malformed output escalates."""
    raw = (content or "").strip()
    if not raw:
        return "escalate", "empty reviewer response"
    # Tolerate fenced output.
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return "escalate", "no JSON object in reviewer response"
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return "escalate", "unparseable reviewer JSON"
    decision = str(data.get("decision") or "").strip().lower()
    rationale = str(data.get("rationale") or "")[:500]
    if decision in ("allow", "deny", "escalate"):
        return decision, rationale  # type: ignore[return-value]
    return "escalate", f"unknown reviewer decision {decision!r}"


def _review_user_prompt(pending: "PendingApproval", params: dict[str, Any]) -> str:
    try:
        params_blob = json.dumps(params, ensure_ascii=False, default=str)[:4000]
    except Exception:  # noqa: BLE001
        params_blob = repr(params)[:4000]
    return (
        f"Tool: {pending.tool_name}\n"
        f"Gating reason: {pending.reason}\n"
        f"Detail: {pending.detail or '(none)'}\n"
        f"Parameters: {params_blob}\n\n"
        "Decide: allow, deny, or escalate."
    )


async def auto_review_decision(
    pending: "PendingApproval",
    params: dict[str, Any],
    *,
    service_manager: Any | None = None,
) -> tuple[AutoReviewDecision, str]:
    """Run the cheap-model reviewer for one pending approval.

    Returns ``(decision, rationale)``. Every failure path escalates to the
    human reviewer rather than allowing or denying blindly.
    """
    sm = service_manager
    if sm is None:
        try:
            from leagent.main import get_service_manager

            sm = get_service_manager()
        except Exception:  # noqa: BLE001
            return "escalate", "service manager unavailable"
    llm = getattr(sm, "llm_service", None) if sm is not None else None
    if llm is None:
        return "escalate", "llm service unavailable"

    try:
        from leagent.llm.model_spec import ModelTask

        response = await llm.chat(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _review_user_prompt(pending, params)},
            ],
            task=ModelTask.FAST,
            temperature=0.0,
            max_tokens=200,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("auto_review_llm_failed", tool=pending.tool_name, error=str(exc))
        return "escalate", f"reviewer call failed: {exc}"

    content = ""
    if isinstance(response, dict):
        content = str(response.get("content") or "")
    decision, rationale = parse_auto_review_response(content)
    logger.info(
        "auto_review_decision",
        tool=pending.tool_name,
        decision=decision,
        rationale=rationale[:200],
    )
    return decision, rationale
