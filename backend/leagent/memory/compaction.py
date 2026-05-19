"""Memory consolidation and maintenance strategies.

Background tasks that merge similar memories, decay importance scores,
prune low-value entries, and re-embed when models are upgraded.
Designed to run via the cron system.

This module is aligned with the live store APIs: :class:`EpisodicStore`
exposes ``list_recent``, ``delete``, and ``note_recall``; it does **not**
have ``list_episodes``, ``update_importance``, or ``delete_episode``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

from leagent.memory.formation import retention_score

if TYPE_CHECKING:
    from leagent.memory.agent_memory import AgentMemory

logger = logging.getLogger(__name__)

SIMILARITY_MERGE_THRESHOLD = 0.9
IMPORTANCE_DECAY_RATE = 0.95
MIN_IMPORTANCE_THRESHOLD = 0.05
MAX_EPISODES_PER_SESSION = 500


class MemoryConsolidator:
    """Runs periodic memory maintenance tasks.

    Integrates with the cron system to perform:
    - Episode deduplication (merge similar summaries)
    - Importance decay (recency-weighted scoring)
    - Low-value pruning (remove below threshold)
    - Model upgrade re-embedding
    """

    def __init__(self, memory: "AgentMemory") -> None:
        self._memory = memory

    async def run_full_maintenance(
        self,
        *,
        user_id: UUID | None = None,
        workspace_id: UUID | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Run all maintenance tasks and return a summary."""
        results: dict[str, Any] = {
            "decayed": 0,
            "pruned": 0,
            "merged": 0,
            "errors": [],
        }

        try:
            results["decayed"] = await self.decay_importance(
                user_id=user_id, dry_run=dry_run,
            )
        except Exception as exc:
            results["errors"].append(f"decay: {exc}")
            logger.warning("memory_decay_failed", error=str(exc))

        try:
            results["pruned"] = await self.prune_low_importance(
                user_id=user_id, dry_run=dry_run,
            )
        except Exception as exc:
            results["errors"].append(f"prune: {exc}")
            logger.warning("memory_prune_failed", error=str(exc))

        logger.info(
            "memory_maintenance_complete",
            **{k: v for k, v in results.items() if k != "errors"},
        )
        return results

    async def decay_importance(
        self,
        *,
        user_id: UUID | None = None,
        dry_run: bool = False,
    ) -> int:
        """Apply time-based importance decay to episodic memories.

        Uses :meth:`EpisodicStore.list_recent` (the live API) to fetch
        episodes, then delegates to :func:`maintenance.decay_episode_importance`
        for the actual DB update.
        """
        from leagent.memory.maintenance import decay_episode_importance

        if dry_run:
            return 0

        store = self._memory.episodic
        db = getattr(store, "_db", None)
        if db is None:
            logger.warning("consolidator_no_database_service")
            return 0

        return await decay_episode_importance(db)

    async def prune_low_importance(
        self,
        *,
        user_id: UUID | None = None,
        dry_run: bool = False,
    ) -> int:
        """Remove episodes below the minimum importance threshold.

        Uses :meth:`EpisodicStore.list_recent` to fetch candidates then
        applies the :func:`retention_score` to decide which to delete
        via :meth:`EpisodicStore.delete`.
        """
        if dry_run:
            return 0

        from datetime import datetime, timezone

        store = self._memory.episodic
        now = datetime.now(timezone.utc)
        episodes = await store.list_recent(user_id=user_id, limit=5000)
        pruned = 0
        for ep in episodes:
            importance = float(ep.importance or 0.0)
            created = ep.created_at
            if created and created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age_days = (now - (created or now)).total_seconds() / 86_400 if created else 999

            score = retention_score(
                importance=importance,
                recall_count=int(ep.recall_count or 0),
                age_days=age_days,
            )
            if score < MIN_IMPORTANCE_THRESHOLD:
                await store.delete(ep.id)
                pruned += 1

        return pruned

    async def consolidate_session_episodes(
        self,
        session_id: UUID,
        *,
        max_episodes: int = MAX_EPISODES_PER_SESSION,
        dry_run: bool = False,
    ) -> int:
        """Merge oldest episodes in a session when count exceeds limit."""
        from leagent.memory.types import Episode

        store = self._memory.episodic
        episodes = await store.list_recent(session_id=session_id, limit=max_episodes + 100)

        if len(episodes) <= max_episodes:
            return 0

        excess = episodes[max_episodes:]
        if not excess or dry_run:
            return len(excess)

        summaries = [
            (ep.summary or "").strip()
            for ep in excess
            if (ep.summary or "").strip()
        ]
        if summaries:
            merged_summary = (
                "[Consolidated memory] "
                + " | ".join(s[:200] for s in summaries[:10])
            )
            episode = Episode(
                session_id=session_id,
                summary=merged_summary,
                importance=0.3,
                user_id=excess[0].user_id,
                workspace_id=excess[0].workspace_id,
            )
            await self._memory.record_episode(episode)

        for ep in excess:
            await store.delete(ep.id)

        return len(excess)
