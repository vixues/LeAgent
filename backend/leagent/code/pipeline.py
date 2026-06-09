"""Unified code generation pipeline.

All code-producing tools call :meth:`CodeGenerationPipeline.prepare`
before executing or writing. The pipeline builds a :class:`CodeArtifact`,
validates syntax when applicable, registers the artifact, fires the
``on_code_artifact`` hook, and returns the artifact so the tool can
decide whether to proceed (via :meth:`should_block`).

Usage inside a tool's ``execute()``::

    pipeline = get_pipeline(context)
    artifact = await pipeline.prepare(
        kind=ArtifactKind.EXECUTE,
        source=source,
        language="python",
        origin_tool=self.name,
        context=context,
    )
    if pipeline.should_block(artifact):
        return {"status": "error", ...}
    # proceed with execution / write
"""

from __future__ import annotations

import logging
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from leagent.code.artifacts import (
    ArtifactKind,
    CodeArtifact,
    CodeArtifactRegistry,
    SessionArtifactStore,
)

if TYPE_CHECKING:
    from leagent.tools.base import ToolContext

logger = logging.getLogger(__name__)

_VALIDATABLE_LANGUAGES = frozenset({"python", "json", "jsonc", "toml", "yaml"})

_EXT_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".pyw": "python",
    ".json": "json",
    ".jsonc": "jsonc",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".md": "markdown",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".sh": "shell",
    ".bash": "shell",
    ".sql": "sql",
    ".xml": "xml",
    ".svg": "xml",
}


def _detect_language(target_path: str | None) -> str:
    """Best-effort language detection from a file path suffix."""
    if not target_path:
        return "text"
    suffix = PurePosixPath(target_path).suffix.lower()
    return _EXT_TO_LANGUAGE.get(suffix, "text")


class CodeGenerationPipeline:
    """Stateless pipeline that tools call to produce validated artifacts."""

    def __init__(
        self,
        registry: CodeArtifactRegistry,
        artifact_store: SessionArtifactStore | None = None,
    ) -> None:
        self._registry = registry
        self._artifact_store = artifact_store

    async def prepare(
        self,
        kind: ArtifactKind,
        source: str,
        language: str,
        origin_tool: str,
        context: "ToolContext",
        *,
        target_path: str | None = None,
        skip_validation: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> CodeArtifact:
        """Build, validate, register, and emit a code artifact."""
        if language == "auto":
            language = _detect_language(target_path)

        session_id = str(getattr(context, "session_id", None) or "")

        artifact = CodeArtifact(
            kind=kind,
            language=language,
            source=source,
            origin_tool=origin_tool,
            session_id=session_id,
            target_path=target_path,
            metadata=dict(metadata) if metadata else {},
        )

        if not skip_validation and language in _VALIDATABLE_LANGUAGES:
            self._validate(artifact)

        self._registry.register(artifact)

        if self._artifact_store is not None:
            try:
                self._artifact_store.persist(artifact)
            except Exception:  # noqa: BLE001
                logger.debug("artifact_store_persist_error", exc_info=True)

        await self._fire_hook(artifact, context)

        logger.info(
            "code_artifact_prepared",
            extra={
                "artifact_id": artifact.artifact_id,
                "kind": artifact.kind.value,
                "language": artifact.language,
                "origin_tool": artifact.origin_tool,
                "syntax_valid": artifact.syntax_valid,
                "source_length": len(artifact.source),
                "target_path": artifact.target_path,
            },
        )
        return artifact

    @staticmethod
    def _validate(artifact: CodeArtifact) -> None:
        """Run syntax validation and update the artifact in place."""
        try:
            from leagent.services.syntax_validation import validate_syntax

            result = validate_syntax(
                artifact.source,
                language=artifact.language,  # type: ignore[arg-type]
                filename=artifact.target_path,
                context_lines=2,
            )
            artifact.syntax_valid = result.valid
            artifact.diagnostics = [d.to_dict() for d in (result.diagnostics or [])]
        except Exception:  # noqa: BLE001
            logger.warning(
                "code_artifact_validation_error",
                extra={"artifact_id": artifact.artifact_id},
                exc_info=True,
            )
            artifact.syntax_valid = None

    @staticmethod
    def should_block(artifact: CodeArtifact) -> bool:
        """Return True if the artifact must not proceed to execution/write.

        Only ``EXECUTE`` artifacts are blocked on syntax errors.
        File writes/edits are advisory (the LLM may write incrementally).
        Snippets and patches are never blocked.
        """
        if artifact.kind != ArtifactKind.EXECUTE:
            return False
        return artifact.syntax_valid is False

    @staticmethod
    async def _fire_hook(
        artifact: CodeArtifact, context: "ToolContext"
    ) -> None:
        """Invoke the on_code_artifact hook if a HookManager is available."""
        extra = getattr(context, "extra", None) or {}
        hooks = extra.get("hooks")
        if hooks is None:
            return
        fire = getattr(hooks, "fire_code_artifact", None)
        if fire is None:
            return
        try:
            await fire(artifact)
        except Exception:  # noqa: BLE001
            logger.warning(
                "code_artifact_hook_error",
                extra={"artifact_id": artifact.artifact_id},
                exc_info=True,
            )


# ---------------------------------------------------------------------------
# Convenience accessor for tools
# ---------------------------------------------------------------------------

_CONTEXT_REGISTRY_KEY = "_code_artifact_registry"
_CONTEXT_ARTIFACT_STORE_KEY = "_session_artifact_store"


def get_pipeline(context: "ToolContext") -> CodeGenerationPipeline | None:
    """Return the pipeline from the tool context, or None if unavailable.

    The registry is attached to ``context.extra`` by :class:`QueryEngine`
    at the start of a turn. If absent, tools should fall back to their
    original behavior (no artifact tracking).
    """
    extra = getattr(context, "extra", None) or {}
    registry = extra.get(_CONTEXT_REGISTRY_KEY)
    if registry is None:
        return None
    if not isinstance(registry, CodeArtifactRegistry):
        return None
    store = extra.get(_CONTEXT_ARTIFACT_STORE_KEY)
    if store is not None and not isinstance(store, SessionArtifactStore):
        store = None
    return CodeGenerationPipeline(registry, artifact_store=store)


def record_operation(
    context: "ToolContext",
    *,
    tool: str,
    kind: str,
    path: str | None = None,
    summary: str = "",
    success: bool = True,
    artifact_id: str | None = None,
    verification: str | None = None,
) -> None:
    """Append a :class:`JournalEntry` to the session journal (best-effort).

    Called by each code-producing tool after execution completes.
    """
    from leagent.code.operations import (
        JOURNAL_CONTEXT_KEY,
        JournalEntry,
        OperationJournal,
    )

    extra = getattr(context, "extra", None) or {}
    journal = extra.get(JOURNAL_CONTEXT_KEY)
    if journal is None or not isinstance(journal, OperationJournal):
        return
    try:
        journal.append(JournalEntry(
            tool=tool,
            kind=kind,
            path=path,
            summary=summary,
            success=success,
            artifact_id=artifact_id,
            verification=verification,
        ))
    except Exception:  # noqa: BLE001
        logger.debug("record_operation_error", exc_info=True)
