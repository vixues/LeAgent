"""ContextManager — the single entry point for per-turn context assembly.

One ``ContextManager`` is constructed per ``QueryEngine`` session. Each
``prepare_turn`` call concurrently resolves every source in the active
recipe, runs the budget minimiser, partitions blocks into system-prompt
text and user-role attachments, and returns a :class:`TurnContext`.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections import OrderedDict
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

from leagent.context.artifact_error_tracker import ArtifactErrorTracker
from leagent.context.budget import minimise
from leagent.context.cache import SourceCache
from leagent.context.file_state import FileState
from leagent.context.ledger import ContextLedger, LedgerRow
from leagent.context.recipe import ContextRecipe, get_recipe
from leagent.context.sources import get_all_sources
from leagent.context.sources.base import ResolveContext
from leagent.context.types import (
    ContextBlock,
    EnvironmentSnapshot,
    ProjectMemorySource,
    RenderTarget,
    TurnContext,
)
from leagent.context.working_set import WorkingSet

if TYPE_CHECKING:
    from leagent.memory.agent_memory import AgentMemory, RecallHandle
    from leagent.memory.working_scratchpad import WorkingScratchpad
    from leagent.prompts.registry import PromptRegistry
    from leagent.prompts.types import BuiltPrompt
    from leagent.services.session import SessionManager
    from leagent.skills.manager import SkillsManager
    from leagent.tools.base import ToolPermissionContext
    from leagent.tools.code.artifact import SessionArtifactStore
    from leagent.tools.code.operations import OperationJournal
    from leagent.tools.registry import ToolRegistry

logger = structlog.get_logger(__name__)

# Bounded LRU dedupe for attachment signatures (long sessions otherwise leak memory).
_MAX_SEEN_ATTACHMENT_SIGNATURES = 256

__all__ = ["ContextManager"]


class ContextManager:
    """Session-scoped owner of all context state.

    Construction mirrors what ``QueryEngineConfig`` used to wire ad-hoc:
    tools, memory, permissions, file state, working set. ``prepare_turn``
    is the only method the engine calls per turn.
    """

    def __init__(
        self,
        *,
        cwd: str = ".",
        settings: Any | None = None,
        tools: "ToolRegistry | None" = None,
        permission_context: "ToolPermissionContext | None" = None,
        skills_manager: "SkillsManager | None" = None,
        agent_memory: "AgentMemory | None" = None,
        session_manager: "SessionManager | None" = None,
        working_scratchpad: "WorkingScratchpad | None" = None,
        prompt_registry: "PromptRegistry | None" = None,
        session_id: UUID | None = None,
        user_id: UUID | None = None,
        agent_id: str = "default",
        variant: str = "default_agent",
        template_variant: str = "default",
        file_state: FileState | None = None,
        working_set: WorkingSet | None = None,
        artifact_tracker: ArtifactErrorTracker | None = None,
        artifact_store: "SessionArtifactStore | None" = None,
        operation_journal: "OperationJournal | None" = None,
    ) -> None:
        self.cwd = cwd
        self._settings = settings
        self.tools = tools
        self.permission_context = permission_context
        self.skills_manager = skills_manager
        self.agent_memory = agent_memory
        self.session_manager = session_manager
        self.working_scratchpad = working_scratchpad
        self.prompt_registry = prompt_registry
        self.session_id = session_id
        self.user_id = user_id
        self.agent_id = agent_id
        self.variant = variant
        self.template_variant = template_variant
        self.artifact_store = artifact_store
        self.operation_journal = operation_journal

        self.file_state: FileState = file_state or FileState(
            max_entries=self._cfg("file_state_max_entries", 64),
            max_tokens=self._cfg("file_state_max_tokens", 16_000),
        )
        self.working_set: WorkingSet = working_set or WorkingSet(
            head_lines=self._cfg("working_set_excerpt_head_lines", 20),
            tail_lines=self._cfg("working_set_excerpt_tail_lines", 10),
        )
        self.artifact_tracker: ArtifactErrorTracker = artifact_tracker or ArtifactErrorTracker()

        self._cache = SourceCache()
        self._seen_signatures: OrderedDict[tuple[str, str], None] = OrderedDict()
        self._last_prefix_hash: str = ""

    @property
    def prompt_builder(self):
        """Shared :class:`~leagent.prompts.builder.PromptBuilder` (prompt composition façade)."""
        from leagent.prompts import get_prompt_builder

        if self.prompt_registry is not None:
            return get_prompt_builder(registry=self.prompt_registry, refresh=False)
        return get_prompt_builder()

    # -- public API --------------------------------------------------------

    async def prepare_turn(
        self,
        query: str,
        *,
        task_id: UUID,
        persona_override: str = "",
        append_extra: str = "",
        workflow_hint: str = "",
        template_vars: dict[str, Any] | None = None,
        recall_handle: "RecallHandle | None" = None,
        project_roots: list[str] | None = None,
    ) -> TurnContext:
        start = time.perf_counter()
        self.artifact_tracker.advance_turn()

        recipe = get_recipe(self.variant)
        source_classes = get_all_sources()

        resolve_ctx = self._build_resolve_context(
            query=query,
            task_id=task_id,
            persona_override=persona_override,
            append_extra=append_extra,
            workflow_hint=workflow_hint,
            template_vars=template_vars or {},
            recall_handle=recall_handle,
            project_roots=project_roots or [],
        )

        blocks, ledger_rows_extra = await self._resolve_sources(recipe, source_classes, resolve_ctx)

        if self.artifact_tracker.has_dirty_artifacts():
            blocks = self._inject_regeneration_directives(blocks)

        budget_result = minimise(
            blocks,
            max_chars=recipe.max_chars,
            freshness_half_life_seconds=self._cfg("freshness_half_life_seconds", 300.0),
        )

        system_blocks = [b for b in budget_result.kept if b.render_target == RenderTarget.SYSTEM]
        attachment_blocks = [b for b in budget_result.kept if b.render_target == RenderTarget.ATTACHMENT_USER]

        # Three-tier ordering for KV cache stability:
        # Tier 0 — pinned sources that rarely change (fixed order for maximum
        #          prompt-prefix overlap across turns).
        # Tier 1 — normal (session-scoped) sources, ordered by priority.
        # Tier 2 — volatile (per-turn) sources at the tail.
        _PINNED_ORDER = {
            "identity": 0,
            "capabilities": 1,
            "policies": 2,
            "project_memory": 3,
            "active_project": 4,
            "user_instructions": 5,
        }
        _VOLATILE_SOURCES = frozenset({
            "environment", "session_attachments", "session_artifacts",
            "recall", "working_set", "tool_history", "recent_reads",
            "artifact_regeneration",
        })

        def _block_sort_key(b: ContextBlock) -> tuple[int, int, str]:
            if b.source_id in _PINNED_ORDER:
                return (0, _PINNED_ORDER[b.source_id], b.source_id)
            if b.source_id in _VOLATILE_SOURCES:
                return (2, -b.priority, b.source_id)
            return (1, -b.priority, b.source_id)

        system_blocks.sort(key=_block_sort_key)

        system_text = "\n\n".join(b.body.rstrip() for b in system_blocks if b.body.strip())

        attachment_messages = self._render_attachments(attachment_blocks)

        stable_hash = self._compute_hash(system_blocks)
        pm_hash = self._compute_project_memory_hash(system_blocks)

        # Log prefix hash drift to surface cache-busting changes between turns.
        pinned_blocks = [b for b in system_blocks if b.source_id in _PINNED_ORDER]
        prefix_hash = self._compute_hash(pinned_blocks) if pinned_blocks else ""
        if hasattr(self, "_last_prefix_hash") and self._last_prefix_hash and prefix_hash != self._last_prefix_hash:
            logger.debug(
                "context_prefix_hash_changed",
                prev=self._last_prefix_hash[:12],
                curr=prefix_hash[:12],
            )
        self._last_prefix_hash = prefix_hash
        full_hash = self._compute_hash(budget_result.kept)

        from leagent.prompts.types import BuiltPrompt, LayerResult

        built = BuiltPrompt(
            system_text=system_text,
            messages=[{"role": "system", "content": system_text}] if system_text else [],
            layers=[
                LayerResult(
                    name=b.source_id,
                    body=b.body,
                    tokens=b.tokens,
                    metadata=dict(b.metadata) if b.metadata else {},
                )
                for b in budget_result.kept
            ],
            render_target=RenderTarget.SYSTEM,  # type: ignore[arg-type]
            stable_hash=stable_hash,
            full_hash=full_hash,
            total_chars=len(system_text),
            truncations=budget_result.truncated,
            variant_key=f"{self.variant}:{self.template_variant}",
        )

        env_snapshot = self._extract_environment(budget_result.kept)
        pm_sources = self._extract_project_memory_sources(budget_result.kept)

        duration_ms = int((time.perf_counter() - start) * 1000)
        try:
            from leagent.utils.metrics import get_metrics

            get_metrics().record_agent_turn_phase(
                "context_prepare",
                duration_ms / 1000,
            )
            stats = self._cache.stats
            get_metrics().cache_entries.labels(cache_name="context_source").set(stats["size"])
        except Exception:
            logger.debug("context_prepare_metrics_failed", exc_info=True)

        ledger_rows: list[LedgerRow] = []
        for row in budget_result.rows:
            ledger_rows.append(LedgerRow(
                source_id=row.source_id,
                bytes=row.final_cost,
                tokens=row.final_cost // 3,
                cache_hit=False,
                skip_reason="",
                truncated=row.truncated,
                dropped=row.dropped,
                render_target="system" if row.kept else "dropped",
                priority=int(row.score),
            ))
        for extra in ledger_rows_extra:
            ledger_rows.append(extra)

        ledger = ContextLedger(
            rows=ledger_rows,
            stable_hash=stable_hash,
            project_memory_hash=pm_hash,
            full_hash=full_hash,
            duration_ms=duration_ms,
            cache_stats=self._cache.stats,
        )

        logger.info("context_prepare", **ledger.to_structlog_dict())

        return TurnContext(
            built_prompt=built,
            attachment_messages=attachment_messages,
            ledger=ledger,
            environment=env_snapshot,
            recall_handle=recall_handle,
            task_id=task_id,
            project_memory_sources=pm_sources,
        )

    def clone(self) -> ContextManager:
        """Create a child manager with a branched file state + empty working set."""
        return ContextManager(
            cwd=self.cwd,
            settings=self._settings,
            tools=self.tools,
            permission_context=self.permission_context,
            skills_manager=self.skills_manager,
            agent_memory=self.agent_memory,
            session_manager=self.session_manager,
            working_scratchpad=self.working_scratchpad,
            prompt_registry=self.prompt_registry,
            user_id=self.user_id,
            agent_id=f"{self.agent_id}/fork",
            variant=self.variant,
            template_variant=self.template_variant,
            file_state=self.file_state.clone(),
            artifact_tracker=self.artifact_tracker.clone(),
        )

    async def close(self) -> None:
        self._cache.clear()

    # -- internal ----------------------------------------------------------

    def _cfg(self, key: str, default: Any) -> Any:
        if self._settings is not None:
            return getattr(self._settings, key, default)
        return default

    def _inject_regeneration_directives(self, blocks: list[ContextBlock]) -> list[ContextBlock]:
        """Prepend a high-priority system block instructing the LLM to regenerate dirty artifacts."""
        directives = self.artifact_tracker.get_regeneration_directives()
        if not directives:
            return blocks
        body = (
            "[ARTIFACT REGENERATION REQUIRED]\n"
            "Previous artifact generation failed. You MUST regenerate the "
            "artifact completely from scratch. Do NOT apply incremental "
            "patches to the previously generated output.\n\n"
            + "\n".join(f"- {d}" for d in directives)
        )
        regen_block = ContextBlock(
            source_id="artifact_regeneration",
            kind="directive",
            render_target=RenderTarget.SYSTEM,
            body=body,
            tokens=len(body) // 3,
            cost=len(body),
            signature="regen",
            priority=1000,
            weight=10.0,
        )
        logger.info(
            "artifact_regeneration_directive_injected",
            dirty_count=len(directives),
        )
        return [regen_block] + blocks

    def _build_resolve_context(
        self,
        *,
        query: str,
        task_id: UUID,
        persona_override: str,
        append_extra: str,
        workflow_hint: str,
        template_vars: dict[str, Any],
        recall_handle: Any,
        project_roots: list[str] | None = None,
    ) -> ResolveContext:
        return ResolveContext(
            cwd=self.cwd,
            query=query,
            variant=self.variant,
            template_variant=self.template_variant,
            persona_override=persona_override,
            append_extra=append_extra,
            workflow_hint=workflow_hint,
            template_vars=template_vars,
            agent_id=self.agent_id,
            tools=self.tools,
            permission_context=self.permission_context,
            skills_manager=self.skills_manager,
            agent_memory=self.agent_memory,
            recall_handle=recall_handle,
            recall_limit=self._cfg("recall_attachment_limit", 5),
            session_manager=self.session_manager,
            session_id=self.session_id,
            user_id=self.user_id,
            task_id=task_id,
            file_state=self.file_state,
            working_scratchpad=self.working_scratchpad,
            working_set=self.working_set,
            project_memory_denylist=self._cfg(
                "project_memory_denylist",
                ["**/leagent/AGENTS.md", "**/backend/AGENTS.md"],
            ),
            project_memory_allowlist=self._cfg("project_memory_allowlist", []),
            respect_git_boundary=self._cfg("respect_git_boundary", True),
            recall_attachment_limit=self._cfg("recall_attachment_limit", 5),
            tool_history_attachment_limit=self._cfg("tool_history_attachment_limit", 5),
            recent_reads_attachment_limit=self._cfg("recent_reads_attachment_limit", 5),
            prompt_registry=self.prompt_registry,
            project_roots=list(project_roots or []),
            artifact_store=self.artifact_store,
            operation_journal=self.operation_journal,
        )

    async def _resolve_sources(
        self,
        recipe: ContextRecipe,
        source_classes: dict[str, type],
        ctx: ResolveContext,
    ) -> tuple[list[ContextBlock], list[LedgerRow]]:
        blocks: list[ContextBlock] = []
        ledger_extras: list[LedgerRow] = []

        async def _resolve_one(entry: Any) -> None:
            source_started = time.perf_counter()
            source_cls = source_classes.get(entry.source_id)
            if source_cls is None:
                ledger_extras.append(LedgerRow(
                    source_id=entry.source_id,
                    bytes=0, tokens=0, cache_hit=False,
                    skip_reason="unknown_source",
                    truncated=False, dropped=True,
                    render_target="", priority=0,
                ))
                return
            if not entry.enabled:
                ledger_extras.append(LedgerRow(
                    source_id=entry.source_id,
                    bytes=0, tokens=0, cache_hit=False,
                    skip_reason="disabled",
                    truncated=False, dropped=True,
                    render_target="", priority=0,
                ))
                return

            source = source_cls()
            inv_key = source.invalidation_key(ctx)

            cached = self._cache.get(inv_key, source.scope)
            if cached is not None:
                try:
                    from leagent.utils.metrics import get_metrics

                    get_metrics().record_cache_event(
                        "context_source",
                        hit=True,
                        entries=self._cache.stats["size"],
                    )
                    get_metrics().record_agent_turn_phase(
                        f"context_source:{entry.source_id}",
                        time.perf_counter() - source_started,
                    )
                except Exception:
                    logger.debug("context_source_metrics_failed", exc_info=True)
                block = cached
                if entry.priority_override is not None:
                    block = ContextBlock(
                        source_id=block.source_id,
                        kind=block.kind,
                        render_target=block.render_target,
                        body=block.body,
                        tokens=block.tokens,
                        cost=block.cost,
                        signature=block.signature,
                        priority=entry.priority_override,
                        weight=entry.weight_override if entry.weight_override is not None else block.weight,
                        metadata=block.metadata,
                    )
                blocks.append(block)
                ledger_extras.append(LedgerRow(
                    source_id=entry.source_id,
                    bytes=len(block.body),
                    tokens=block.tokens,
                    cache_hit=True,
                    skip_reason="",
                    truncated=False, dropped=False,
                    render_target=block.render_target.value,
                    priority=block.priority,
                ))
                return
            try:
                from leagent.utils.metrics import get_metrics

                get_metrics().record_cache_event(
                    "context_source",
                    hit=False,
                    entries=self._cache.stats["size"],
                )
            except Exception:
                logger.debug("context_cache_metrics_failed", exc_info=True)

            try:
                block = await source.resolve(ctx)
            except Exception as exc:
                logger.warning("source_resolve_error", source_id=entry.source_id, error=str(exc))
                block = None

            if block is None:
                ledger_extras.append(LedgerRow(
                    source_id=entry.source_id,
                    bytes=0, tokens=0, cache_hit=False,
                    skip_reason="resolved_none",
                    truncated=False, dropped=True,
                    render_target="", priority=0,
                ))
                return

            if entry.priority_override is not None or entry.weight_override is not None:
                block = ContextBlock(
                    source_id=block.source_id,
                    kind=block.kind,
                    render_target=block.render_target,
                    body=block.body,
                    tokens=block.tokens,
                    cost=block.cost,
                    signature=block.signature,
                    priority=entry.priority_override if entry.priority_override is not None else block.priority,
                    weight=entry.weight_override if entry.weight_override is not None else block.weight,
                    metadata=block.metadata,
                )

            self._cache.put(inv_key, block)
            blocks.append(block)
            try:
                from leagent.utils.metrics import get_metrics

                get_metrics().record_agent_turn_phase(
                    f"context_source:{entry.source_id}",
                    time.perf_counter() - source_started,
                )
            except Exception:
                logger.debug("context_source_metrics_failed", exc_info=True)

        await asyncio.gather(*(_resolve_one(e) for e in recipe.entries))
        return blocks, ledger_extras

    def _render_attachments(self, blocks: list[ContextBlock]) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for block in blocks:
            sig = (block.source_id, block.signature)
            if sig in self._seen_signatures:
                continue
            self._seen_signatures[sig] = None
            while len(self._seen_signatures) > _MAX_SEEN_ATTACHMENT_SIGNATURES:
                self._seen_signatures.popitem(last=False)
            messages.append({
                "role": "user",
                "content": block.body,
                "metadata": {
                    "attachment": True,
                    "kind": block.source_id,
                    "signature": block.signature,
                },
            })
        return messages

    def _compute_hash(self, blocks: list[ContextBlock]) -> str:
        parts = [f"§{b.source_id}§\n{b.body}" for b in blocks]
        canonical = f"{self.variant}:{self.template_variant}\n" + "\n".join(parts)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def _compute_project_memory_hash(self, blocks: list[ContextBlock]) -> str:
        pm = [b for b in blocks if b.source_id == "project_memory"]
        if not pm:
            return ""
        return self._compute_hash(pm)

    def _extract_environment(self, blocks: list[ContextBlock]) -> EnvironmentSnapshot | None:
        for b in blocks:
            if b.source_id == "environment":
                snap = b.metadata.get("snapshot")
                if isinstance(snap, EnvironmentSnapshot):
                    return snap
        return None

    def _extract_project_memory_sources(self, blocks: list[ContextBlock]) -> list[ProjectMemorySource]:
        for b in blocks:
            if b.source_id == "project_memory":
                sources = b.metadata.get("sources")
                if isinstance(sources, list):
                    return sources
        return []
