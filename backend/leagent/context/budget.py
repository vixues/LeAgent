"""Cost-function minimiser for context blocks."""

from __future__ import annotations

from dataclasses import dataclass, replace

import structlog

from leagent.context.types import ContextBlock, ContextScope

logger = structlog.get_logger(__name__)

__all__ = [
    "BudgetRow",
    "MinimiseResult",
    "PINNED_THRESHOLD",
    "TRUNCATION_SUFFIX",
    "DEFAULT_SOURCE_HARD_CAP_CHARS",
    "SOURCE_HARD_CAPS",
    "enforce_source_hard_budgets",
    "minimise",
]

PINNED_THRESHOLD = 1000
TRUNCATION_SUFFIX = "\n…[truncated by context budget]"

#: ~10K tokens ≈ 30K chars (approx_tokens = len // 3). Hard ceiling per
#: fragment so a single source cannot dominate the prompt (Codex context rule).
DEFAULT_SOURCE_HARD_CAP_CHARS = 30_000

#: Per-source hard caps (chars). Volatile / bulky sources get tighter budgets.
SOURCE_HARD_CAPS: dict[str, int] = {
    "tool_history": 12_000,
    "recent_reads": 12_000,
    "recall": 12_000,
    "working_set": 12_000,
    "session_attachments": 18_000,
    "session_artifacts": 12_000,
    "project_memory": 24_000,
    "playbooks": 18_000,
    "art_playbook": 18_000,
    "document_generation": 18_000,
    "structured_output_elicitation": 6_000,
    "policies": 18_000,
}


def enforce_source_hard_budgets(
    blocks: list[ContextBlock],
    *,
    default_cap: int = DEFAULT_SOURCE_HARD_CAP_CHARS,
    caps: dict[str, int] | None = None,
) -> tuple[list[ContextBlock], list[str]]:
    """Truncate each block that exceeds its per-source hard char budget.

    Returns ``(blocks, truncated_source_ids)``. Always runs *before*
    the global :func:`minimise` pass so no single fragment can exceed
    ~10K tokens regardless of remaining global budget.
    """
    table = caps if caps is not None else SOURCE_HARD_CAPS
    out: list[ContextBlock] = []
    truncated: list[str] = []
    for block in blocks:
        cap = table.get(block.source_id, default_cap)
        if block.cost <= cap:
            out.append(block)
            continue
        max_body = max(0, cap - len(TRUNCATION_SUFFIX))
        tb = _truncate_block(block, max_body)
        out.append(tb)
        truncated.append(block.source_id)
        logger.info(
            "context_source_hard_budget",
            source_id=block.source_id,
            original_chars=block.cost,
            cap_chars=cap,
            final_chars=tb.cost,
        )
    return out, truncated


@dataclass(slots=True)
class BudgetRow:
    source_id: str
    original_cost: int
    final_cost: int
    score: float
    kept: bool
    truncated: bool
    dropped: bool


@dataclass(slots=True)
class MinimiseResult:
    kept: list[ContextBlock]
    truncated: list[str]
    dropped: list[str]
    rows: list[BudgetRow]


def _freshness_decay(scope: ContextScope, half_life: float) -> float:
    if scope in (ContextScope.PROCESS, ContextScope.SESSION):
        return 1.0
    return 0.95


def _truncate_block(block: ContextBlock, max_body_chars: int) -> ContextBlock:
    """Return a new ContextBlock with its body truncated to *max_body_chars*."""
    truncated_body = block.body[:max_body_chars] + TRUNCATION_SUFFIX
    new_tokens = ContextBlock.approx_tokens(truncated_body)
    return replace(
        block,
        body=truncated_body,
        tokens=new_tokens,
        cost=len(truncated_body),
    )


def minimise(
    blocks: list[ContextBlock],
    *,
    max_chars: int = 24_000,
    freshness_half_life_seconds: float = 300.0,
) -> MinimiseResult:
    """Budget-aware block selection.

    1. Separate blocks into *pinned* (priority >= PINNED_THRESHOLD) and
       *candidates*.
    2. Sum pinned cost.  If it exceeds *max_chars*, truncate pinned blocks
       in priority-descending order until the budget is met.
    3. Score candidates: ``priority * weight * freshness_decay(scope)``.
    4. Sort by ``score / cost`` descending with a deterministic tie-break
       on ``source_id``.
    5. Greedily include candidates until cap is reached.
    """
    pinned: list[ContextBlock] = []
    candidates: list[ContextBlock] = []
    for b in blocks:
        (pinned if b.priority >= PINNED_THRESHOLD else candidates).append(b)

    kept: list[ContextBlock] = []
    truncated_ids: list[str] = []
    dropped_ids: list[str] = []
    rows: list[BudgetRow] = []
    used = 0

    # --- pinned blocks (highest priority first) ---
    pinned.sort(key=lambda b: (-b.priority, b.source_id))
    for b in pinned:
        remaining = max_chars - used
        if remaining <= 0:
            dropped_ids.append(b.source_id)
            rows.append(BudgetRow(
                source_id=b.source_id,
                original_cost=b.cost,
                final_cost=0,
                score=float(b.priority),
                kept=False,
                truncated=False,
                dropped=True,
            ))
            continue
        if b.cost <= remaining:
            kept.append(b)
            used += b.cost
            rows.append(BudgetRow(
                source_id=b.source_id,
                original_cost=b.cost,
                final_cost=b.cost,
                score=float(b.priority),
                kept=True,
                truncated=False,
                dropped=False,
            ))
        else:
            max_body = remaining - len(TRUNCATION_SUFFIX)
            if max_body > 0:
                tb = _truncate_block(b, max_body)
                kept.append(tb)
                used += tb.cost
                truncated_ids.append(b.source_id)
                rows.append(BudgetRow(
                    source_id=b.source_id,
                    original_cost=b.cost,
                    final_cost=tb.cost,
                    score=float(b.priority),
                    kept=True,
                    truncated=True,
                    dropped=False,
                ))
            else:
                dropped_ids.append(b.source_id)
                rows.append(BudgetRow(
                    source_id=b.source_id,
                    original_cost=b.cost,
                    final_cost=0,
                    score=float(b.priority),
                    kept=False,
                    truncated=False,
                    dropped=True,
                ))

    # --- candidate blocks (score / cost ratio) ---
    scored: list[tuple[float, str, ContextBlock]] = []
    for b in candidates:
        scope = ContextScope(b.metadata.get("scope", ContextScope.SESSION.value)) if "scope" in b.metadata else ContextScope.SESSION
        decay = _freshness_decay(scope, freshness_half_life_seconds)
        score = b.priority * b.weight * decay
        ratio = score / max(b.cost, 1)
        scored.append((ratio, b.source_id, b))

    scored.sort(key=lambda t: (-t[0], t[1]))

    for _ratio, _, b in scored:
        remaining = max_chars - used
        scope = ContextScope(b.metadata.get("scope", ContextScope.SESSION.value)) if "scope" in b.metadata else ContextScope.SESSION
        score = b.priority * b.weight * _freshness_decay(scope, freshness_half_life_seconds)
        if remaining <= 0:
            dropped_ids.append(b.source_id)
            rows.append(BudgetRow(
                source_id=b.source_id,
                original_cost=b.cost,
                final_cost=0,
                score=score,
                kept=False,
                truncated=False,
                dropped=True,
            ))
            continue
        if b.cost <= remaining:
            kept.append(b)
            used += b.cost
            rows.append(BudgetRow(
                source_id=b.source_id,
                original_cost=b.cost,
                final_cost=b.cost,
                score=score,
                kept=True,
                truncated=False,
                dropped=False,
            ))
        else:
            max_body = remaining - len(TRUNCATION_SUFFIX)
            if max_body > 0:
                tb = _truncate_block(b, max_body)
                kept.append(tb)
                used += tb.cost
                truncated_ids.append(b.source_id)
                rows.append(BudgetRow(
                    source_id=b.source_id,
                    original_cost=b.cost,
                    final_cost=tb.cost,
                    score=score,
                    kept=True,
                    truncated=True,
                    dropped=False,
                ))
            else:
                dropped_ids.append(b.source_id)
                rows.append(BudgetRow(
                    source_id=b.source_id,
                    original_cost=b.cost,
                    final_cost=0,
                    score=score,
                    kept=False,
                    truncated=False,
                    dropped=True,
                ))

    return MinimiseResult(
        kept=kept,
        truncated=truncated_ids,
        dropped=dropped_ids,
        rows=rows,
    )
