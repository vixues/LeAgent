"""Session-artifacts context source.

Injects two compact sections into the system prompt:

1. **Recent code artifacts** — metadata (path, language, kind,
   validation status, content hash) from :class:`SessionArtifactStore`.
2. **Recent operations** — an ordered journal of tool calls from
   :class:`OperationJournal`.

Together they let the LLM know what files it has written and which
tool calls it has made this session — without re-reading files.
"""

from __future__ import annotations

import structlog

from leagent.context.sources import SOURCE_REGISTRY
from leagent.context.sources.base import ResolveContext
from leagent.context.types import ContextBlock, ContextScope, RenderTarget

logger = structlog.get_logger(__name__)


class SessionArtifactsSource:
    """Resolves a summary of recent artifacts + operations for the LLM."""

    id: str = "session_artifacts"
    kind: str = "state"
    scope: ContextScope = ContextScope.TURN
    priority: int = 850
    weight: float = 0.8
    render_target: RenderTarget = RenderTarget.SYSTEM

    def invalidation_key(self, ctx: ResolveContext) -> str:
        return f"session_artifacts:{ctx.session_id}"

    async def resolve(self, ctx: ResolveContext) -> ContextBlock | None:
        try:
            session_id = str(ctx.session_id or "")
            if not session_id:
                return None

            parts: list[str] = []

            store = ctx.artifact_store
            if store is not None:
                artifact_text = store.summary_text(session_id, limit=15)
                if artifact_text and artifact_text.strip():
                    parts.append(artifact_text)

            journal = ctx.operation_journal
            if journal is not None:
                from leagent.tools.code.operations import OperationJournal

                if isinstance(journal, OperationJournal) and len(journal) > 0:
                    journal_text = journal.summary_text(limit=15)
                    if journal_text and journal_text.strip():
                        parts.append(journal_text)

            if not parts:
                return None

            body = "\n\n".join(parts)
            return ContextBlock(
                source_id=self.id,
                kind=self.kind,
                render_target=self.render_target,
                body=body,
                tokens=ContextBlock.approx_tokens(body),
                cost=ContextBlock.approx_tokens(body),
                signature=ContextBlock.content_signature(self.id, body),
                priority=self.priority,
                weight=self.weight,
                metadata={},
            )
        except Exception:
            logger.exception("session_artifacts_resolve_failed")
            return None


SOURCE_REGISTRY[SessionArtifactsSource.id] = SessionArtifactsSource
