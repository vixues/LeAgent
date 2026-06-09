"""Public façade for the agent memory stack.

The agent runtime never talks to :class:`EpisodicStore`, :class:`SemanticStore`,
:class:`ProceduralStore`, or :class:`RetrievalPipeline` directly. Instead it
goes through :class:`AgentMemory`, which exposes exactly four methods:

* :meth:`record_episode` — store a summary of the turn that just finished.
* :meth:`upsert_fact` — add or refresh a durable user/workspace fact.
* :meth:`record_procedure` — record the outcome of a tool chain.
* :meth:`recall` — hybrid recall across all stores.

Keeping the surface this narrow is the whole point of the "clean slate"
memory redesign: downstream code should never have to reach into a
specific store. The :class:`RecallHandle` is a small convenience wrapper
for use in streaming contexts where we want to fire-and-forget a recall
and consume the result later in the turn.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

_MAX_OBSERVED_TURN_KEYS = 2048

from leagent.memory.formation import (
    FormationDecision,
    FormationPolicy,
    FormationTarget,
    TurnObservation,
    build_episode_summary,
    build_procedure_signature,
)
from leagent.memory.recall import RecallOptions, RetrievalPipeline
from leagent.memory.types import (
    Episode,
    Fact,
    Procedure,
    RecallBundle,
)

if TYPE_CHECKING:
    from leagent.context.file_state import FileState as FileStateCache
    from leagent.memory.embeddings import EmbeddingProvider
    from leagent.memory.episodic import EpisodicStore
    from leagent.memory.procedural import ProceduralStore
    from leagent.memory.semantic import SemanticStore

logger = logging.getLogger(__name__)


class AgentMemory:
    """Single entry-point the agent runtime uses for long-lived memory."""

    def __init__(
        self,
        *,
        episodic: EpisodicStore,
        semantic: SemanticStore,
        procedural: ProceduralStore,
        embeddings: EmbeddingProvider,
        formation_policy: FormationPolicy | None = None,
    ) -> None:
        self._episodic = episodic
        self._semantic = semantic
        self._procedural = procedural
        self._embeddings = embeddings
        self._formation = formation_policy or FormationPolicy()
        self._last_procedure_write_status: dict[str, object] | None = None
        self._last_episode_write: dict[str, Any] = {"ok": True, "error": None}
        self._last_fact_write: dict[str, Any] = {"ok": True, "error": None}
        self.last_write_failed_at: datetime | None = None
        self._pipeline = RetrievalPipeline(
            episodic=episodic,
            semantic=semantic,
            procedural=procedural,
            embeddings=embeddings,
        )
        # Deterministic bounded LRU of observed ``(session_id, turn_id)`` keys
        # so duplicate ``observe_turn`` calls (controller + hook) are
        # idempotent without unbounded growth or non-deterministic eviction.
        self._observed_turn_keys: OrderedDict[str, None] = OrderedDict()

    @property
    def pipeline(self) -> RetrievalPipeline:
        return self._pipeline

    @property
    def episodic(self) -> EpisodicStore:
        return self._episodic

    @property
    def semantic(self) -> SemanticStore:
        return self._semantic

    @property
    def procedural(self) -> ProceduralStore:
        return self._procedural

    def procedure_write_status(self) -> dict[str, object]:
        """Best-effort health for the most recent procedural memory write."""
        if self._last_procedure_write_status is not None:
            return dict(self._last_procedure_write_status)
        return self._build_procedure_write_status(pg_written=True)

    def memory_write_status(self) -> dict[str, Any]:
        """Aggregate write health for episodes, facts, and procedures."""
        proc = self.procedure_write_status()
        return {
            "last_write_failed_at": (
                self.last_write_failed_at.isoformat()
                if self.last_write_failed_at
                else None
            ),
            "episode": dict(self._last_episode_write),
            "fact": dict(self._last_fact_write),
            "procedure": dict(proc),
            "any_write_degraded": bool(
                not self._last_episode_write.get("ok", True)
                or not self._last_fact_write.get("ok", True)
                or bool(proc.get("degraded"))
            ),
        }

    def _memory_wal_path(self) -> Path:
        root = os.environ.get("LEAGENT_HOME") or os.environ.get("WORKING_DIR") or "/tmp"
        return Path(root) / "memory_failed_writes.wal"

    def _append_failed_write_wal(self, kind: str, error: str, detail: str) -> None:
        """Append-only log for operational replay / auditing (best-effort)."""
        line = json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "kind": kind,
                "error": error,
                "detail": detail[:2000],
            },
            ensure_ascii=False,
        )
        try:
            path = self._memory_wal_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError as exc:
            logger.debug("memory_wal_append_failed: %s", exc)

    def _build_procedure_write_status(self, *, pg_written: bool) -> dict[str, object]:
        vector_write = getattr(self._procedural, "last_vector_write", None)
        embedding_degraded = bool(getattr(self._embeddings, "last_degraded", False))
        embedding_error = getattr(self._embeddings, "last_error", None)
        vector_written = bool(getattr(vector_write, "written", False))
        vector_error = getattr(vector_write, "error", None)
        collection = getattr(self._procedural, "collection", None)
        vector_optional = collection is not None and not bool(getattr(collection, "enabled", True))
        vector_degraded = (
            False
            if vector_optional
            else bool(getattr(vector_write, "degraded", not vector_written))
        )
        return {
            "pg_written": pg_written,
            "vector_written": vector_written,
            "vector_optional": vector_optional,
            "embedding_degraded": embedding_degraded,
            "vector_degraded": vector_degraded,
            "degraded": (not pg_written) or embedding_degraded or vector_degraded,
            "embedding_error": str(embedding_error) if embedding_error else None,
            "vector_error": str(vector_error) if vector_error else None,
        }

    # -- writes ---------------------------------------------------------

    async def record_episode(self, episode: Episode) -> Episode:
        """Persist a past-turn summary. Safe to call in streaming paths."""
        try:
            out = await self._episodic.record(episode)
            self._last_episode_write = {"ok": True, "error": None}
            return out
        except Exception as exc:  # noqa: BLE001
            logger.warning("record_episode_failed: %s", exc)
            self._last_episode_write = {"ok": False, "error": str(exc)}
            self.last_write_failed_at = datetime.now(timezone.utc)
            self._append_failed_write_wal("episode", str(exc), repr(episode.id))
            return episode

    async def upsert_fact(self, fact: Fact) -> Fact:
        try:
            out = await self._semantic.upsert(fact)
            self._last_fact_write = {"ok": True, "error": None}
            return out
        except Exception as exc:  # noqa: BLE001
            logger.warning("upsert_fact_failed: %s", exc)
            self._last_fact_write = {"ok": False, "error": str(exc)}
            self.last_write_failed_at = datetime.now(timezone.utc)
            self._append_failed_write_wal("fact", str(exc), str(fact.key))
            return fact

    async def record_procedure(
        self,
        procedure: Procedure,
        *,
        outcome: str,
        success: bool,
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> Procedure:
        try:
            out = await self._procedural.record(
                procedure,
                outcome=outcome,
                success=success,
                error=error,
                duration_ms=duration_ms,
            )
            self._last_procedure_write_status = self._build_procedure_write_status(pg_written=True)
            return out
        except Exception as exc:  # noqa: BLE001
            logger.warning("record_procedure_failed: %s", exc)
            self.last_write_failed_at = datetime.now(timezone.utc)
            self._append_failed_write_wal("procedure", str(exc), procedure.signature or "")
            self._last_procedure_write_status = {
                "pg_written": False,
                "vector_written": False,
                "embedding_degraded": bool(getattr(self._embeddings, "last_degraded", False)),
                "vector_degraded": True,
                "degraded": True,
                "embedding_error": str(getattr(self._embeddings, "last_error", None) or "") or None,
                "vector_error": None,
                "error": str(exc),
            }
            return procedure

    # -- policy-driven observation API -----------------------------------

    @property
    def formation_policy(self) -> FormationPolicy:
        return self._formation

    async def observe_turn(self, obs: TurnObservation) -> FormationDecision:
        """Evaluate a turn observation and write to appropriate stores.

        This is the primary entry-point for multi-signal memory formation.
        Idempotent per ``(session_id, turn_id)`` — duplicate calls from
        both the controller and the hook are silently deduplicated.

        Returns the formation decision for observability / tests.
        Safe to call from streaming paths — never raises.
        """
        turn_key = f"{obs.session_id}:{getattr(obs, 'turn_id', '') or ''}"
        if turn_key in self._observed_turn_keys:
            return FormationDecision(suppress=True, reasoning="duplicate observe_turn")
        self._observed_turn_keys[turn_key] = None
        while len(self._observed_turn_keys) > _MAX_OBSERVED_TURN_KEYS:
            self._observed_turn_keys.popitem(last=False)

        try:
            decision = self._formation.evaluate(obs)
        except Exception as exc:  # noqa: BLE001
            logger.warning("formation_evaluate_failed: %s", exc)
            return FormationDecision(suppress=True, reasoning=f"evaluate error: {exc}")

        if decision.suppress or not decision.targets:
            return decision

        if FormationTarget.EPISODIC in decision.targets:
            try:
                summary = build_episode_summary(obs)
                if summary.strip():
                    episode = Episode(
                        session_id=obs.session_id,
                        user_id=obs.user_id,
                        workspace_id=obs.workspace_id,
                        summary=summary,
                        importance=decision.importance,
                        tags=obs.tags[:48],
                    )
                    await self.record_episode(episode)
            except Exception as exc:  # noqa: BLE001
                logger.warning("observe_turn_episodic_failed: %s", exc)

        if FormationTarget.PROCEDURAL in decision.targets and obs.tool_names:
            try:
                sig = build_procedure_signature(obs)
                tool_line = ", ".join(obs.tool_names[:32])
                intent = (obs.user_text or "")[:200].strip() or "(no user text)"
                output = (obs.assistant_text or "")[:200].strip() or "No output"
                description = f"{intent}\n→ {output}\nTools: {tool_line}"[:4000]
                procedure = Procedure(
                    name="auto run",
                    signature=sig,
                    description=description,
                    user_id=obs.user_id,
                    workspace_id=obs.workspace_id,
                )
                success = obs.tool_failure_count == 0 and obs.tool_success_count > 0
                await self.record_procedure(
                    procedure,
                    outcome=output,
                    success=success,
                    error=obs.error,
                    duration_ms=obs.duration_ms,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("observe_turn_procedural_failed: %s", exc)

        if FormationTarget.SEMANTIC in decision.targets and obs.user_id is not None:
            try:
                text = (obs.user_text or "").strip()
                if text:
                    key = f"auto.turn.{obs.session_id}"
                    await self.upsert_fact(
                        Fact(
                            user_id=obs.user_id,
                            workspace_id=obs.workspace_id,
                            key=key,
                            value=text[:2000],
                            confidence=decision.confidence,
                            source=f"formation.{decision.provenance}",
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("observe_turn_semantic_failed: %s", exc)

        return decision

    async def observe_feedback(
        self,
        *,
        is_like: bool,
        has_tools: bool,
        tool_count: int = 0,
        existing_importance: float = 0.3,
    ) -> FormationDecision:
        """Score a feedback event without writing — caller decides action.

        Returns the formation decision so the feedback endpoint can combine
        it with the existing ``record_procedure_for_liked_assistant`` path
        or act on dislikes.
        """
        try:
            return self._formation.score_feedback(
                is_like=is_like,
                has_tools=has_tools,
                tool_count=tool_count,
                existing_importance=existing_importance,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("observe_feedback_failed: %s", exc)
            return FormationDecision(suppress=True, reasoning=f"feedback error: {exc}")

    # -- reads ----------------------------------------------------------

    async def recall(
        self,
        query: str,
        *,
        recall_anchor: str | None = None,
        user_id: UUID | None = None,
        session_id: UUID | None = None,
        workspace_id: UUID | None = None,
        limit: int = 8,
        per_store_limit: int = 4,
        include_episodic: bool = True,
        include_semantic: bool = True,
        include_procedural: bool = True,
        file_state: FileStateCache | None = None,
    ) -> RecallBundle:
        options = RecallOptions(
            query=query,
            recall_anchor=recall_anchor,
            user_id=user_id,
            session_id=session_id,
            workspace_id=workspace_id,
            limit=limit,
            per_store_limit=per_store_limit,
            include_episodic=include_episodic,
            include_semantic=include_semantic,
            include_procedural=include_procedural,
            file_state=file_state,
        )
        try:
            return await self._pipeline.recall(options)
        except Exception as exc:  # noqa: BLE001
            logger.warning("recall_failed: %s", exc)
            return RecallBundle(query=query)


    # -- lifecycle -------------------------------------------------------

    async def forget_episode(self, episode_id: UUID) -> None:
        """Delete a single episodic memory entry."""
        await self._episodic.delete(episode_id)

    async def forget_fact(self, fact_id: UUID) -> None:
        """Delete a single semantic fact."""
        await self._semantic.delete(fact_id)

    async def export_episodes(
        self, *, user_id: UUID, limit: int = 500,
    ) -> list[Episode]:
        """Export recent episodes for a user (GDPR / data portability)."""
        return await self._episodic.list_recent(user_id=user_id, limit=limit)

    async def export_facts(
        self, *, user_id: UUID, limit: int = 500,
    ) -> list[Fact]:
        """Export all facts for a user."""
        return await self._semantic.list_for_user(user_id, limit=limit)

    async def delete_user_data(self, user_id: UUID) -> dict[str, int]:
        """Delete all memory data for a user (GDPR right-to-erasure).

        Returns counts of deleted rows per store.
        """
        counts: dict[str, int] = {}
        episodes = await self._episodic.list_recent(user_id=user_id, limit=10_000)
        for ep in episodes:
            if ep.id:
                await self._episodic.delete(ep.id)
        counts["episodes"] = len(episodes)

        facts = await self._semantic.list_for_user(user_id, limit=10_000)
        for f in facts:
            if f.id:
                await self._semantic.delete(f.id)
        counts["facts"] = len(facts)

        procs = await self._procedural.list_recent_for_user(user_id=user_id, limit=10_000)
        for p in procs:
            if p.id:
                await self._procedural.delete(p.id)
        counts["procedures"] = len(procs)

        return counts


class RecallHandle:
    """Fire-and-forget wrapper around :meth:`AgentMemory.recall`.

    The query engine kicks off :meth:`start` while the LLM is still
    generating, then awaits :meth:`consume` right before composing the
    final system prompt. The bundle is cached, so re-calling
    :meth:`consume` is cheap.

    This class replaces the previous ``MemoryPrefetchHandle`` from the
    legacy memory module — same shape, different backing store.
    """

    def __init__(self, memory: AgentMemory) -> None:
        self._memory = memory
        self._task: asyncio.Task[RecallBundle] | None = None
        self._result: RecallBundle | None = None

    def start(
        self,
        query: str,
        *,
        recall_anchor: str | None = None,
        user_id: UUID | None = None,
        session_id: UUID | None = None,
        workspace_id: UUID | None = None,
        limit: int = 8,
        per_store_limit: int = 4,
        file_state: FileStateCache | None = None,
    ) -> None:
        """Kick off recall in the background. Idempotent per handle."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(
            self._memory.recall(
                query,
                recall_anchor=recall_anchor,
                user_id=user_id,
                session_id=session_id,
                workspace_id=workspace_id,
                limit=limit,
                per_store_limit=per_store_limit,
                file_state=file_state,
            )
        )

    async def consume(self) -> RecallBundle:
        """Await the in-flight task, caching the result for reuse."""
        if self._result is not None:
            return self._result
        if self._task is None:
            self._result = RecallBundle(query="")
            return self._result
        try:
            self._result = await self._task
        except Exception as exc:  # noqa: BLE001
            logger.warning("recall_handle_consume_failed: %s", exc)
            self._result = RecallBundle(query="")
        return self._result

    def cancel(self) -> None:
        """Cancel the background task if it is still running."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = None


__all__ = ["AgentMemory", "RecallHandle"]
