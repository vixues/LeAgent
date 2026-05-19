"""Hybrid semantic + lexical recall across the three cognitive stores.

The pipeline combines three ranking signals:

1. **Semantic similarity** via Milvus. We embed the query once and fan out
   one ``search`` per store; the raw cosine scores become the base ranking.
2. **Lexical fallback** via SQLAlchemy ``ilike`` (works on SQLite and Postgres)
   when Milvus is unavailable
   or returns nothing useful. This is intentionally simple (no BM25 server
   dependency) but always available.
3. **Recency + quality rerank**: episodes and procedures with a more
   recent ``last_run_at`` / ``created_at`` get a modest boost, and
   :class:`RecallEntry` items pointing at procedures with a low success
   rate are demoted.

Finally the pipeline filters results against :class:`FileStateCache` so
the controller doesn't re-inject content already visible in the current
turn (e.g. a file the agent just read).
"""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from leagent.memory.types import MemoryKind, RecallBundle, RecallEntry

if TYPE_CHECKING:
    from leagent.context.file_state import FileState as FileStateCache
    from leagent.memory.embeddings import EmbeddingProvider
    from leagent.memory.episodic import EpisodicStore
    from leagent.memory.procedural import ProceduralStore
    from leagent.memory.semantic import SemanticStore

logger = logging.getLogger(__name__)

DEFAULT_LIMIT_PER_STORE = 4
DEFAULT_TOTAL_LIMIT = 8
RECENCY_HALF_LIFE_DAYS = 14.0


@dataclass(slots=True)
class RecallOptions:
    """Tuning knobs for :meth:`RetrievalPipeline.recall`."""

    query: str
    recall_anchor: str | None = None
    user_id: UUID | None = None
    session_id: UUID | None = None
    workspace_id: UUID | None = None
    limit: int = DEFAULT_TOTAL_LIMIT
    per_store_limit: int = DEFAULT_LIMIT_PER_STORE
    include_episodic: bool = True
    include_semantic: bool = True
    include_procedural: bool = True
    file_state: FileStateCache | None = None


class RetrievalPipeline:
    """Orchestrates recall across the three cognitive stores."""

    def __init__(
        self,
        *,
        episodic: EpisodicStore,
        semantic: SemanticStore,
        procedural: ProceduralStore,
        embeddings: EmbeddingProvider,
    ) -> None:
        self._episodic = episodic
        self._semantic = semantic
        self._procedural = procedural
        self._embeddings = embeddings

    async def recall(self, options: RecallOptions) -> RecallBundle:
        query = (options.query or "").strip()
        if not query and options.recall_anchor:
            query = (options.recall_anchor or "").strip()
        bundle = RecallBundle(query=query)
        if not query:
            return bundle

        options = replace(options, query=query)

        vector: list[float] | None = None
        if self._vector_search_enabled(options):
            try:
                vector = await self._embeddings.embed_one(query)
                # NullEmbeddingProvider and other degraded paths must not run cosine
                # search on poison or placeholder vectors.
                if getattr(self._embeddings, "last_degraded", False):
                    vector = None
            except Exception as exc:  # noqa: BLE001
                logger.warning("recall_embed_failed: %s", exc)
                vector = None

        async def _empty() -> list[RecallEntry]:
            return []

        ep_task = (
            self._episodic_candidates(options, vector)
            if options.include_episodic
            else _empty()
        )
        sem_task = (
            self._semantic_candidates(options, vector)
            if options.include_semantic and options.user_id is not None
            else _empty()
        )
        proc_task = (
            self._procedural_candidates(options, vector)
            if options.include_procedural
            else _empty()
        )
        ep_r, sem_r, proc_r = await asyncio.gather(ep_task, sem_task, proc_task)
        candidates: list[RecallEntry] = []
        candidates.extend(ep_r)
        candidates.extend(sem_r)
        candidates.extend(proc_r)

        ranked = self._rerank(candidates)
        deduped = self._deduplicate(ranked, options.file_state)
        collapsed = self._collapse_semantic_over_episodic(deduped)
        bundle.extend(collapsed[: max(1, options.limit)])

        for entry in bundle.entries:
            if entry.kind is MemoryKind.EPISODIC:
                try:
                    await self._episodic.note_recall(entry.source_id)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("recall_note_failed: %s", exc)
        return bundle

    def _vector_search_enabled(self, options: RecallOptions) -> bool:
        stores: list[object] = []
        if options.include_episodic:
            stores.append(self._episodic)
        if options.include_semantic and options.user_id is not None:
            stores.append(self._semantic)
        if options.include_procedural:
            stores.append(self._procedural)

        collections = [
            getattr(store, "collection", None)
            for store in stores
            if getattr(store, "collection", None) is not None
        ]
        if not collections:
            # Unit-test fakes and custom stores may not expose vector health;
            # preserve the previous behavior for those implementations.
            return True
        return any(bool(getattr(collection, "can_search", False)) for collection in collections)

    # -- store-specific candidate gathering -----------------------------

    async def _episodic_candidates(
        self,
        options: RecallOptions,
        vector: list[float] | None,
    ) -> list[RecallEntry]:
        results: list[RecallEntry] = []
        if vector is not None:
            try:
                results.extend(
                    await self._episodic.semantic_search(
                        vector,
                        user_id=options.user_id,
                        session_id=options.session_id,
                        limit=options.per_store_limit,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("episodic_semantic_failed: %s", exc)
        if not results:
            try:
                results.extend(
                    await self._episodic.lexical_search(
                        options.query,
                        user_id=options.user_id,
                        session_id=options.session_id,
                        limit=options.per_store_limit,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("episodic_lexical_failed: %s", exc)
        return results

    async def _semantic_candidates(
        self,
        options: RecallOptions,
        vector: list[float] | None,
    ) -> list[RecallEntry]:
        if options.user_id is None:
            return []
        results: list[RecallEntry] = []
        if vector is not None:
            try:
                results.extend(
                    await self._semantic.semantic_search(
                        vector,
                        user_id=options.user_id,
                        workspace_id=options.workspace_id,
                        limit=options.per_store_limit,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("semantic_semantic_failed: %s", exc)
        if not results:
            try:
                results.extend(
                    await self._semantic.lexical_search(
                        options.query,
                        user_id=options.user_id,
                        workspace_id=options.workspace_id,
                        limit=options.per_store_limit,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("semantic_lexical_failed: %s", exc)
        return results

    async def _procedural_candidates(
        self,
        options: RecallOptions,
        vector: list[float] | None,
    ) -> list[RecallEntry]:
        results: list[RecallEntry] = []
        if vector is not None:
            try:
                results.extend(
                    await self._procedural.semantic_search(
                        vector,
                        user_id=options.user_id,
                        workspace_id=options.workspace_id,
                        limit=options.per_store_limit,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("procedural_semantic_failed: %s", exc)
        if not results:
            try:
                results.extend(
                    await self._procedural.lexical_search(
                        options.query,
                        user_id=options.user_id,
                        workspace_id=options.workspace_id,
                        limit=options.per_store_limit,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("procedural_lexical_failed: %s", exc)
        return results

    # -- ranking --------------------------------------------------------

    def _rerank(self, candidates: list[RecallEntry]) -> list[RecallEntry]:
        now = datetime.now(timezone.utc)
        for entry in candidates:
            entry.score = _apply_boosts(entry, now=now)
        return sorted(candidates, key=lambda e: e.score, reverse=True)

    def _deduplicate(
        self,
        ranked: list[RecallEntry],
        file_state: FileStateCache | None,
    ) -> list[RecallEntry]:
        seen_ids: set[str] = set()
        seen_texts: set[str] = set()
        out: list[RecallEntry] = []
        for entry in ranked:
            id_key = f"{entry.kind.value}:{entry.source_id}"
            if id_key in seen_ids:
                continue
            seen_ids.add(id_key)
            if file_state is not None and _mentions_known_file(entry, file_state):
                continue
            text_sig = _text_signature(entry.text)
            if text_sig in seen_texts:
                continue
            seen_texts.add(text_sig)
            out.append(entry)
        return out

    @staticmethod
    def _collapse_semantic_over_episodic(
        entries: list[RecallEntry],
    ) -> list[RecallEntry]:
        """When a semantic fact covers the same content as an episodic entry,
        prefer the fact (more stable, higher confidence) and drop the episode."""
        semantic_texts: set[str] = set()
        for e in entries:
            if e.kind is MemoryKind.SEMANTIC:
                semantic_texts.add(_text_signature(e.text))
        if not semantic_texts:
            return entries
        return [
            e for e in entries
            if e.kind is not MemoryKind.EPISODIC
            or _text_signature(e.text) not in semantic_texts
        ]


def _text_signature(text: str) -> str:
    """Cheap content fingerprint for near-duplicate collapse."""
    t = (text or "").strip().lower()[:300]
    return t


def _apply_boosts(entry: RecallEntry, *, now: datetime) -> float:
    base = max(0.0, float(entry.score or 0.0))
    boost = 1.0

    created_at_raw = entry.metadata.get("last_run_at") or entry.metadata.get(
        "created_at"
    )
    if isinstance(created_at_raw, str):
        try:
            timestamp = datetime.fromisoformat(created_at_raw)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            age_days = max(0.0, (now - timestamp).total_seconds() / 86_400)
            boost *= 0.5 + 0.5 * math.exp(-age_days / RECENCY_HALF_LIFE_DAYS)
        except ValueError:
            pass

    if entry.kind is MemoryKind.SEMANTIC:
        confidence = float(entry.metadata.get("confidence") or 0.0)
        boost *= 0.5 + 0.5 * max(0.0, min(1.0, confidence))
        boost *= 1.15

    if entry.kind is MemoryKind.PROCEDURAL:
        success_rate = float(entry.metadata.get("success_rate") or 0.0)
        run_count = int(entry.metadata.get("run_count") or 0)
        boost *= 0.4 + 0.6 * success_rate
        if run_count == 0:
            boost *= 0.8
        elif run_count >= 3:
            boost *= 1.1

    if entry.kind is MemoryKind.EPISODIC:
        importance = float(entry.metadata.get("importance") or 0.0)
        boost *= 1.0 + 0.3 * max(0.0, min(1.0, importance))
        recalls = int(entry.metadata.get("recall_count") or 0)
        boost *= 1.0 + min(0.6, 0.04 * recalls)

    return base * boost


def _mentions_known_file(entry: RecallEntry, file_state: FileStateCache) -> bool:
    paths = file_state.paths()
    if not paths:
        return False
    text = entry.text or ""
    return any(path and path in text for path in paths)


__all__ = ["RecallOptions", "RetrievalPipeline"]
