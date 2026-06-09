"""Scheduled-style memory hygiene: forgetting, consolidation, and adaptive decay.

Functions here are designed to run from the cron system. They use the
:func:`retention_score` from :mod:`formation` for consistent scoring.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from sqlmodel import select

from leagent.memory.formation import retention_score
from leagent.memory.types import Fact
from leagent.db.models.agent_memory import AgentEpisode, AgentFact

if TYPE_CHECKING:
    from leagent.memory.agent_memory import AgentMemory
    from leagent.db.service import DatabaseService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Episode forgetting
# ---------------------------------------------------------------------------


async def forget_low_value_episodes(
    database: DatabaseService,
    *,
    older_than_days: int = 120,
    max_importance: float = 0.07,
    max_recalls: int = 0,
    retention_threshold: float = 0.05,
) -> int:
    """Delete old episodic rows that scored below the retention threshold.

    Two-stage filter: first the cheap SQL predicates, then the richer
    :func:`retention_score` computation on surviving rows.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, older_than_days))
    cutoff_naive = cutoff.replace(tzinfo=None)
    now = datetime.now(timezone.utc)
    removed = 0
    async with database.session() as session:
        result = await session.exec(
            select(AgentEpisode).where(
                AgentEpisode.created_at < cutoff_naive,
                AgentEpisode.importance <= max_importance,
                AgentEpisode.recall_count <= max_recalls,
            )
        )
        rows = list(result.all())
        for row in rows:
            created = row.created_at
            if created and created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age_days = (now - (created or now)).total_seconds() / 86_400 if created else 999
            score = retention_score(
                importance=float(row.importance or 0.0),
                recall_count=int(row.recall_count or 0),
                age_days=age_days,
            )
            if score < retention_threshold:
                await session.delete(row)
                removed += 1
    if removed:
        logger.info("memory_forget_episodes_removed", count=removed)
    return removed


# ---------------------------------------------------------------------------
# Episode → Semantic consolidation
# ---------------------------------------------------------------------------


async def consolidate_notable_episodes(
    agent_memory: AgentMemory,
    *,
    limit: int = 48,
    min_summary_len: int = 40,
    min_importance: float = 0.2,
    min_recall_count: int = 0,
    dedup_existing: bool = True,
) -> int:
    """Promote episodic summaries into semantic facts for durable retrieval.

    Uses deterministic keys ``digest.episode.<uuid>`` so re-runs upsert in
    place. When *dedup_existing* is True, skips episodes whose key already
    exists in the semantic store at a higher confidence.
    """
    episodes = await agent_memory.episodic.list_recent(limit=max(1, limit))
    written = 0
    for ep in episodes:
        if ep.user_id is None:
            continue
        summary = (ep.summary or "").strip()
        if len(summary) < min_summary_len:
            continue
        if float(ep.importance or 0.0) < min_importance:
            continue
        if int(ep.recall_count or 0) < min_recall_count:
            continue

        key = f"digest.episode.{ep.id}"
        confidence = min(0.85, 0.45 + float(ep.importance or 0.0))

        if dedup_existing:
            try:
                existing = await agent_memory.semantic.get_by_key(
                    user_id=ep.user_id,
                    key=key,
                    workspace_id=ep.workspace_id,
                )
                if existing is not None and existing.confidence >= confidence:
                    continue
            except Exception:  # noqa: BLE001
                pass

        await agent_memory.upsert_fact(
            Fact(
                user_id=ep.user_id,
                workspace_id=ep.workspace_id,
                key=key,
                value=summary[:8000],
                confidence=confidence,
                source="memory.consolidation",
            )
        )
        written += 1
    if written:
        logger.info("memory_consolidation_facts_written", count=written)
    return written


# ---------------------------------------------------------------------------
# Adaptive importance decay
# ---------------------------------------------------------------------------


async def decay_episode_importance(
    database: DatabaseService,
    *,
    decay_rate: float = 0.95,
    floor: float = 0.02,
    recall_protection_per_count: float = 0.01,
) -> int:
    """Apply time-based importance decay to all episodic rows.

    Recalled episodes decay more slowly. The floor prevents rows from
    becoming un-recoverable before the forgetting job removes them.
    """
    updated = 0
    async with database.session() as session:
        result = await session.exec(select(AgentEpisode))
        rows = list(result.all())
        for row in rows:
            old = float(row.importance or 0.0)
            new = old * decay_rate
            recalls = int(row.recall_count or 0)
            if recalls > 0:
                new = min(old, new + recalls * recall_protection_per_count)
            new = max(floor, new)
            if abs(new - old) > 0.001:
                row.importance = new
                updated += 1
    if updated:
        logger.info("memory_decay_episodes_updated", count=updated)
    return updated


# ---------------------------------------------------------------------------
# Semantic fact confidence decay
# ---------------------------------------------------------------------------


async def decay_fact_confidence(
    database: DatabaseService,
    *,
    older_than_days: int = 90,
    decay_rate: float = 0.97,
    floor: float = 0.10,
) -> int:
    """Decay confidence on semantic facts that haven't been refreshed recently."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, older_than_days))
    cutoff_naive = cutoff.replace(tzinfo=None)
    updated = 0
    async with database.session() as session:
        result = await session.exec(
            select(AgentFact).where(AgentFact.updated_at < cutoff_naive)
        )
        rows = list(result.all())
        for row in rows:
            old = float(row.confidence or 0.0)
            new = max(floor, old * decay_rate)
            if abs(new - old) > 0.001:
                row.confidence = new
                updated += 1
    if updated:
        logger.info("memory_decay_facts_updated", count=updated)
    return updated


# ---------------------------------------------------------------------------
# Full maintenance
# ---------------------------------------------------------------------------


async def run_full_maintenance(
    agent_memory: AgentMemory,
    database: DatabaseService,
    *,
    dry_run: bool = False,
) -> dict[str, int]:
    """Run all maintenance steps and return a summary."""
    results: dict[str, int] = {
        "episodes_decayed": 0,
        "episodes_forgotten": 0,
        "facts_consolidated": 0,
        "facts_decayed": 0,
    }
    if dry_run:
        return results

    try:
        results["episodes_decayed"] = await decay_episode_importance(database)
    except Exception as exc:  # noqa: BLE001
        logger.warning("maintenance_decay_failed", error=str(exc))

    try:
        results["episodes_forgotten"] = await forget_low_value_episodes(database)
    except Exception as exc:  # noqa: BLE001
        logger.warning("maintenance_forget_failed", error=str(exc))

    try:
        results["facts_consolidated"] = await consolidate_notable_episodes(agent_memory)
    except Exception as exc:  # noqa: BLE001
        logger.warning("maintenance_consolidation_failed", error=str(exc))

    try:
        results["facts_decayed"] = await decay_fact_confidence(database)
    except Exception as exc:  # noqa: BLE001
        logger.warning("maintenance_fact_decay_failed", error=str(exc))

    logger.info("memory_full_maintenance_complete", **results)
    return results


__all__ = [
    "consolidate_notable_episodes",
    "decay_episode_importance",
    "decay_fact_confidence",
    "forget_low_value_episodes",
    "run_full_maintenance",
]
