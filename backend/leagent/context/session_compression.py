"""Session transcript compression — microcompact, progressive, optional LLM autocompact."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from leagent.agent.tool_use_context import ToolUseContext
from leagent.context.compression import CompressionConfig, ProgressiveCompressor
from leagent.memory.compact import (
    _approximate_tokens,
    apply_forced_autocompact,
    build_microcompact,
)

if TYPE_CHECKING:
    from leagent.config.settings import Settings
    from leagent.llm.service import LLMService

from leagent.services.session.state import (
    SessionMessage,
    _parse_dt,
    _serialise_dt,
    _utc_now,
)


def _session_compress_budget_tokens(settings: "Settings", override: int | None) -> int:
    """Token budget used by progressive + dry-run pipeline (aligned with historical default)."""
    session_threshold = getattr(settings.session, "autocompact_token_threshold", 96_000)
    if override is not None:
        return override
    return max(8_000, session_threshold // 4)


@dataclass
class CompressionPipelineResult:
    approx_tokens_before: int
    approx_tokens_after: int
    stages_applied: list[str]
    llm_autocompact_applied: bool
    messages: list[dict[str, Any]]


def _compression_stub_context() -> ToolUseContext:
    """Minimal :class:`ToolUseContext` for compaction helpers that ignore it."""
    import asyncio

    from leagent.context.file_state import FileState
    from leagent.tools.base import ToolPermissionContext
    from leagent.tools.executor import ToolExecutor
    from leagent.tools.registry import get_registry

    registry = get_registry()
    return ToolUseContext(
        abort_event=asyncio.Event(),
        tools=registry,
        executor=ToolExecutor(
            registry=registry,
            service_manager=None,
            permission_context=ToolPermissionContext(),
        ),
        file_state_cache=FileState(),
    )


def _progressive_output_dicts(
    mc: list[dict[str, Any]],
    pc_cfg: CompressionConfig,
    cms: list[Any],
) -> list[dict[str, Any]]:
    """Map ProgressiveCompressor output back to LLM dicts; preserve tool tail from ``mc``.

    The protected window is snapped with :func:`snap_autocompact_split` so a
    rolling-summary head never leaves orphan ``tool`` rows at the start of the
    kept suffix (providers reject ``tool`` without a preceding ``tool_calls``).
    """
    from leagent.memory.compact import snap_autocompact_split

    protected = pc_cfg.min_recent_turns * 2
    if len(mc) <= protected:
        return list(mc)
    split = snap_autocompact_split(mc, len(mc) - protected)
    n_recent = len(mc) - split
    # ProgressiveCompressor only carries role + text body on ``CompressedMessage``.
    # When output is 1:1 with ``mc``, merge compressed ``content`` onto the original
    # wire dicts so OpenAI-compatible APIs still receive ``tool_call_id`` / ``tool_calls``
    # / ``name`` / ``reasoning_content`` (dropping them yields 400 on ``role: tool``).
    if len(cms) == len(mc):
        head: list[dict[str, Any]] = []
        for i in range(split):
            merged = dict(mc[i])
            merged["content"] = cms[i].content
            head.append(merged)
        return head + mc[split:]
    if n_recent and len(cms) >= n_recent:
        head = [{"role": c.role, "content": c.content} for c in cms[:-n_recent]]
    else:
        head = [{"role": c.role, "content": c.content} for c in cms]
    return head + mc[split:]


def apply_progressive_transcript_compress(
    llm_messages: list[dict[str, Any]],
    *,
    settings: "Settings",
    budget_tokens: int | None = None,
) -> list[dict[str, Any]]:
    """Progressive token shrink for the live LLM payload (no summariser LLM, no DB writes).

    Intended to run **after** :func:`build_microcompact` on each model call.
    Summarisation stays in :func:`build_autocompact` (``QueryDeps.autocompact``).
    """
    budget = _session_compress_budget_tokens(settings, budget_tokens)
    if _approximate_tokens(llm_messages) <= budget:
        return list(llm_messages)

    pc_cfg = CompressionConfig()
    pc = ProgressiveCompressor(pc_cfg)
    cms = pc.compress(llm_messages, budget_tokens=budget)
    return _progressive_output_dicts(llm_messages, pc_cfg, cms)


async def run_session_compression_pipeline(
    llm_messages: list[dict[str, Any]],
    *,
    settings: "Settings",
    llm: "LLMService | None",
    budget_tokens: int | None = None,
    force_llm: bool = False,
    system_prompt_for_autocompact: str = "",
) -> CompressionPipelineResult:
    """Run microcompact → progressive compression → optional forced LLM autocompact."""
    stages: list[str] = []
    before = _approximate_tokens(llm_messages)
    working = list(llm_messages)
    stub = _compression_stub_context()
    micro = build_microcompact(llm)
    working = await micro(working, stub)
    stages.append("microcompact")

    budget = _session_compress_budget_tokens(settings, budget_tokens)
    working = apply_progressive_transcript_compress(
        working, settings=settings, budget_tokens=budget
    )
    stages.append("progressive_compressor")

    after_prog = _approximate_tokens(working)
    llm_applied = False

    keep_recent = int(getattr(settings.session, "autocompact_keep_recent", 20))
    need_llm = force_llm or after_prog >= budget

    if need_llm and llm is not None:
        before_llm = list(working)
        merged = await apply_forced_autocompact(
            working,
            llm=llm,
            tool_use_context=stub,
            system_prompt=system_prompt_for_autocompact,
            keep_recent=keep_recent,
        )
        llm_applied = merged != before_llm
        working = merged
        stages.append("forced_llm_autocompact")

    after = _approximate_tokens(working)
    return CompressionPipelineResult(
        approx_tokens_before=before,
        approx_tokens_after=after,
        stages_applied=stages,
        llm_autocompact_applied=llm_applied,
        messages=working,
    )


def session_messages_to_compact_llm_dicts(messages: list[SessionMessage]) -> list[dict[str, Any]]:
    """LLM-shaped dicts plus stable ``id`` / timestamps for tests or future persist paths.

    :meth:`SessionMessage.to_llm_message` omits ``id``; when re-materialising
    :class:`SessionMessage` rows from compressed dicts, :func:`merge_compressed_with_session_tail`
    uses ``id`` to preserve primary keys, ``attachment_ids``, and ``created_at``.
    """
    out: list[dict[str, Any]] = []
    for m in messages:
        d = m.to_llm_message()
        d["id"] = str(m.id)
        if m.attachment_ids:
            d["attachment_ids"] = list(m.attachment_ids)
        d["created_at"] = _serialise_dt(m.created_at)
        if m.model:
            d["model"] = m.model
        out.append(d)
    return out


def _session_message_from_compact_overlay(
    base: SessionMessage,
    d: dict[str, Any],
) -> SessionMessage:
    """Apply compressed wire fields onto an existing transcript row."""
    content = d.get("content")
    if not isinstance(content, str):
        content = str(content or "")

    role = str(d.get("role") or base.role)

    if "tool_calls" in d:
        tc = d.get("tool_calls")
        tool_calls = tc if isinstance(tc, list) else None
    else:
        tool_calls = base.tool_calls

    if "tool_call_id" in d:
        tcid = d.get("tool_call_id")
        tool_call_id = str(tcid) if tcid else None
    else:
        tool_call_id = base.tool_call_id

    if "reasoning_content" in d:
        rc = d.get("reasoning_content")
        if isinstance(rc, str) and rc.strip():
            reasoning_content: str | None = rc.strip()
        else:
            reasoning_content = None
    else:
        reasoning_content = base.reasoning_content

    model = str(d["model"]) if d.get("model") else base.model

    return SessionMessage(
        id=base.id,
        role=role,
        content=content,
        created_at=base.created_at,
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
        attachment_ids=list(base.attachment_ids),
        model=model,
        reasoning_content=reasoning_content,
    )


def llm_dict_to_session_message(d: dict[str, Any], *, msg_id: Any = None) -> SessionMessage:
    """Convert one LLM-shaped dict to :class:`SessionMessage`."""
    from uuid import UUID, uuid4

    role = str(d.get("role") or "user")
    content = d.get("content")
    if not isinstance(content, str):
        content = str(content or "")
    tc = d.get("tool_calls")
    tool_calls = tc if isinstance(tc, list) else None
    tcid = d.get("tool_call_id")
    tool_call_id = str(tcid) if tcid else None
    raw_id = msg_id or d.get("id")
    sid = UUID(str(raw_id)) if raw_id else uuid4()

    raw_att = d.get("attachment_ids")
    attachment_ids = [str(a) for a in raw_att] if isinstance(raw_att, list) else []

    created_at = _parse_dt(d.get("created_at")) if d.get("created_at") else _utc_now()
    model = str(d["model"]) if d.get("model") else None

    rc = d.get("reasoning_content")
    reasoning_content = (
        (s or None)
        if isinstance(rc, str) and (s := str(rc).strip())
        else None
    )

    return SessionMessage(
        id=sid,
        role=role,
        content=content,
        created_at=created_at,
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
        attachment_ids=attachment_ids,
        model=model,
        reasoning_content=reasoning_content,
    )


def merge_compressed_with_session_tail(
    original: list[SessionMessage],
    final_dicts: list[dict[str, Any]],
) -> list[SessionMessage]:
    """Map compressed wire messages back to :class:`SessionMessage` rows.

    When each dict carries ``id`` from :func:`session_messages_to_compact_llm_dicts`,
    stable rows are updated in place (preserving ``attachment_ids``, ``created_at``,
    primary key). Rows without a known id (e.g. new ``<compacted_history>`` system
    message) are minted via :func:`llm_dict_to_session_message`.
    """
    if not final_dicts:
        return []

    orig_by_id = {str(m.id): m for m in original}

    def row_id(d: dict[str, Any]) -> str | None:
        x = d.get("id")
        if x is None:
            return None
        s = str(x).strip()
        return s or None

    out: list[SessionMessage] = []
    for d in final_dicts:
        rid = row_id(d)
        base = orig_by_id.get(rid) if rid else None
        if base is not None:
            out.append(_session_message_from_compact_overlay(base, d))
        else:
            out.append(llm_dict_to_session_message(d))
    return out
