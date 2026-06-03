"""Track artifact generation failures and signal clean-state regeneration.

When a tool result indicates that a previously-generated artifact (GenUI
tree, HTML canvas, code output) encountered a runtime or compilation
error, the tracker marks it as *dirty*.  On the next turn the
:class:`ContextManager` queries the tracker and, when dirty artifacts
exist, injects a high-priority regeneration directive into the system
prompt and evicts stale intermediate state from file/source caches.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

__all__ = ["ArtifactError", "ArtifactErrorTracker"]

_CODE_ESCALATE_AFTER_FAILURES = 3

_ARTIFACT_TOOL_NAMES: frozenset[str] = frozenset({
    "emit_ui_tree",
    "emit_ui_patch",
    "canvas_publish",
    "code_execution",
    "python_run",
    "run_code",
    "exec_python",
})


@dataclass
class ArtifactError:
    """Single recorded artifact failure."""

    artifact_id: str
    artifact_type: str  # "genui", "canvas", "code"
    error_message: str
    source_tool_call_id: str
    turn_index: int
    error_type: str = ""
    failure_count: int = 1
    timestamp: float = field(default_factory=time.monotonic)


def classify_artifact_tool(tool_name: str) -> str | None:
    """Return the artifact type for a known artifact-producing tool, or ``None``."""
    if tool_name in {"emit_ui_tree", "emit_ui_patch"}:
        return "genui"
    if tool_name == "canvas_publish":
        return "canvas"
    if tool_name in {"code_execution", "python_run", "run_code", "exec_python"}:
        return "code"
    return None


class ArtifactErrorTracker:
    """Session-scoped tracker of dirty artifacts that need regeneration."""

    def __init__(self) -> None:
        self._errors: dict[str, ArtifactError] = {}
        self._turn_index: int = 0
        self._workspace_dirty: bool = False

    # -- mutation -----------------------------------------------------------

    def advance_turn(self) -> None:
        self._turn_index += 1

    def record_error(self, error: ArtifactError) -> None:
        existing = self._errors.get(error.artifact_id)
        if existing is not None:
            error.failure_count = existing.failure_count + 1
        error.turn_index = self._turn_index
        self._errors[error.artifact_id] = error
        if error.artifact_type == "code":
            self._workspace_dirty = True

    def record_from_tool_result(
        self,
        tool_name: str,
        tool_call_id: str,
        success: bool,
        error_text: str,
        *,
        canvas_id: str = "",
        error_type: str = "",
    ) -> None:
        """Convenience: derive an :class:`ArtifactError` from a tool result."""
        if success:
            art_type = classify_artifact_tool(tool_name)
            if art_type is not None:
                aid = canvas_id or tool_call_id
                self._errors.pop(aid, None)
                if art_type == "code":
                    self._workspace_dirty = False
            return

        art_type = classify_artifact_tool(tool_name)
        if art_type is None:
            return
        aid = canvas_id or tool_call_id
        self.record_error(ArtifactError(
            artifact_id=aid,
            artifact_type=art_type,
            error_message=error_text[:500],
            source_tool_call_id=tool_call_id,
            turn_index=self._turn_index,
            error_type=(error_type or "").strip().lower(),
        ))

    def clear_artifact(self, artifact_id: str) -> None:
        self._errors.pop(artifact_id, None)

    def clear_all(self) -> None:
        self._errors.clear()
        self._workspace_dirty = False

    # -- introspection -----------------------------------------------------

    def has_dirty_artifacts(self) -> bool:
        return bool(self._errors)

    @property
    def needs_workspace_reset(self) -> bool:
        return self._workspace_dirty

    def dirty_artifacts(self) -> list[ArtifactError]:
        return list(self._errors.values())

    def _code_directive(self, err: ArtifactError) -> str:
        et = err.error_type
        base = (
            f"Previous code execution (tool_call {err.source_tool_call_id}) "
            f"failed: {err.error_message}."
        )
        if err.failure_count >= _CODE_ESCALATE_AFTER_FAILURES:
            return (
                f"{base} This artifact failed {err.failure_count} times. "
                "Pass `reset_workspace: true` and regenerate the script from "
                "scratch with `code_execution`."
            )
        if et in ("syntax", "runtime", "timeout", ""):
            return (
                f"{base} Prefer a minimal fix: use `source_echo`, "
                "`suggested_fix_region`, and `repair_workflow` from the tool "
                "result. Patch the persisted script with `code_workspace_edit` "
                "on `__last_source__.py`, then re-run `code_execution` with "
                "`workspace_file=__last_source__.py`. Do NOT rewrite the "
                "entire program unless multiple regions are broken."
            )
        if et in ("validation", "dependency"):
            return (
                f"{base} Fix transport or environment first (valid JSON tool "
                "args, `tool_argument_blob` + `source_blob_id`, or "
                "`uv_pip_install` for missing packages). Then retry "
                "`code_execution`."
            )
        return (
            f"{base} Follow `repair_workflow` in the tool result. Prefer "
            "`code_workspace_edit` + `workspace_file` over resending full "
            "`source`."
        )

    def get_regeneration_directives(self) -> list[str]:
        """Return human-readable directives for the LLM system prompt."""
        if not self._errors:
            return []
        directives: list[str] = []
        for err in self._errors.values():
            if err.artifact_type == "genui":
                msg = err.error_message
                if "tree is not valid JSON" in msg:
                    directives.append(
                        f"Previous `emit_ui_tree` (tool_call {err.source_tool_call_id}) "
                        f"failed — nested tree JSON did not parse: {msg}. "
                        "Fix escaping at the indicated byte position (\\\" inside strings, \\n for "
                        "newlines), or pass `tree` as a structured object instead of one giant "
                        "JSON string. Re-call `emit_ui_tree` with the corrected tree (same layout "
                        "is fine). Do NOT use `emit_ui_patch` until a tree has validated."
                    )
                else:
                    directives.append(
                        f"Previous gen-UI artifact (tool_call {err.source_tool_call_id}) "
                        f"failed: {msg}. "
                        "Regenerate the UI tree from scratch using `emit_ui_tree`. "
                        "Do NOT apply incremental patches via `emit_ui_patch` to "
                        "the broken tree."
                    )
            elif err.artifact_type == "canvas":
                directives.append(
                    f"Previous canvas publish (tool_call {err.source_tool_call_id}) "
                    f"failed: {err.error_message}. "
                    "Regenerate the canvas content completely. Do NOT reuse "
                    "the previous HTML/embed output."
                )
            elif err.artifact_type == "code":
                directives.append(self._code_directive(err))
        return directives

    # -- serialisation (for clone) -----------------------------------------

    def clone(self) -> ArtifactErrorTracker:
        new = ArtifactErrorTracker()
        new._errors = dict(self._errors)
        new._turn_index = self._turn_index
        new._workspace_dirty = self._workspace_dirty
        return new
