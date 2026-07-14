"""``CodeExecutionTool`` — professional Python execution in a subprocess sandbox.

This is the high-trust counterpart to the workflow :class:`ScriptNode`.
It runs user-supplied Python in a fresh interpreter subprocess with
SIGALRM timeouts, a sanitized environment, and a per-session
:class:`~leagent.services.code_execution.Workspace` that doubles as the
process ``cwd`` and a scratch for produced files. See
:mod:`leagent.services.code_execution` for the underlying plumbing.

The tool is intentionally conservative on I/O: it accepts at most a
small mapping of JSON-serialisable ``inputs`` to inject as globals,
optional inline ``files`` to stage into the workspace, and returns the
captured ``stdout``/``stderr``, the ``result`` bound in the script, and
the list of newly produced files (relative paths + sizes). Callers who
need the file contents should re-read them through the normal file
tools — the CodeExecutionTool does not itself marshal large bodies
back through the parent.

Designed for a single caller at a time per workspace. The tool is safe
to run in parallel across **different** sessions (the
:class:`WorkspaceManager` scopes per-session) but callers should avoid
concurrent invocations against the same session because the scratch
directory is shared.

The execution flow is split into two explicit phases:

1. **Generation** (``_phase_generate``) — resolve source text from
   inline ``source`` or ``source_blob_id``, create a
   :class:`~leagent.tools.code.artifact.CodeArtifact` via the
   :class:`~leagent.tools.code.pipeline.CodeGenerationPipeline`,
   validate syntax, and decide whether to block execution.
2. **Execution** (``_phase_execute``) — set up the workspace, install
   skill dependencies if needed, dispatch to the subprocess sandbox,
   capture results, and build the typed return envelope.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, TypedDict

import structlog

from leagent.code.sandbox import SubprocessSandbox
from leagent.code.workspace import Workspace, WorkspaceManager
from leagent.services.python_env.resolve import resolve_backend_python_executable
from leagent.tools.base import BaseTool, ToolCategory, ToolContext, ToolResult

if TYPE_CHECKING:
    from leagent.code.artifacts import CodeArtifact

logger = structlog.get_logger(__name__)

_SOURCE_ECHO_LIMIT = 12_000

_REPAIR_WORKFLOW_SYNTAX = (
    "1) Use `code_workspace_edit` on `__last_source__.py` (or the failing "
    "`workspace_file`) with a minimal old_string/new_string fix using "
    "`source_echo` and `suggested_fix_region`; "
    "2) Re-run `code_execution` with `workspace_file=__last_source__.py` "
    "(no need to resend full `source`)."
)
_REPAIR_WORKFLOW_RUNTIME = (
    "1) Read stderr/traceback and `suggested_fix_region`; "
    "2) Fix with `code_workspace_edit` on `__last_source__.py`; "
    "3) Re-run via `workspace_file=__last_source__.py`."
)
_REPAIR_WORKFLOW_VALIDATION = (
    "Tool-call JSON may be malformed. Retry with strict JSON escaping or "
    "use `tool_argument_blob` + `source_blob_id`. If the script itself is "
    "fine, regenerate `source` from scratch."
)


# ---------------------------------------------------------------------------
# Typed result envelope
# ---------------------------------------------------------------------------

ErrorType = Literal["syntax", "timeout", "runtime", "dependency", "validation"]


class CodeExecutionEnvelope(TypedDict, total=False):
    """Typed envelope returned by every ``code_execution`` exit path.

    All fields are always present in practice; ``total=False`` keeps
    TypedDict construction flexible while the canonical builder
    :func:`_build_envelope` guarantees completeness.
    """

    status: str
    error: str | None
    error_type: ErrorType | None
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool
    result: Any
    produced_files: list[dict[str, Any]]
    images: list[dict[str, Any]]
    files: list[dict[str, Any]]
    duration_ms: int
    workspace: str
    returncode: int
    source_echo: str
    source_length: int
    artifact_id: str | None
    syntax_diagnostics: list[dict[str, Any]] | None
    suggested_fix_region: dict[str, Any] | None
    workspace_file: str | None
    repair_workflow: str | None


def _repair_workflow_for(error_type: ErrorType | None) -> str | None:
    if error_type == "syntax":
        return _REPAIR_WORKFLOW_SYNTAX
    if error_type == "runtime":
        return _REPAIR_WORKFLOW_RUNTIME
    if error_type in ("validation", "dependency"):
        return _REPAIR_WORKFLOW_VALIDATION
    if error_type == "timeout":
        return (
            "Inspect partial stdout/stderr; reduce work or raise `timeout_sec`, "
            "then fix via `code_workspace_edit` and re-run with `workspace_file`."
        )
    return None


def _extract_fix_region(
    stderr: str,
    syntax_diagnostics: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Parse stderr traceback or syntax diagnostics to identify the failing region."""
    if syntax_diagnostics:
        first = syntax_diagnostics[0]
        line = first.get("line")
        if isinstance(line, int):
            return {
                "start_line": max(1, line - 2),
                "end_line": line + 2,
                "message": first.get("message", ""),
            }

    import re

    tb_match = re.search(
        r'File "(?:<sandbox>|<code_execution>|<string>)", line (\d+)',
        stderr,
    )
    if tb_match:
        line = int(tb_match.group(1))
        err_lines = stderr.strip().splitlines()
        last_line = err_lines[-1] if err_lines else ""
        return {
            "start_line": max(1, line - 2),
            "end_line": line + 2,
            "message": last_line,
        }
    return None


def _build_envelope(
    *,
    status: str,
    source: str,
    error: str | None = None,
    error_type: ErrorType | None = None,
    stdout: str = "",
    stderr: str = "",
    stdout_truncated: bool = False,
    stderr_truncated: bool = False,
    result: Any = None,
    produced_files: list[dict[str, Any]] | None = None,
    images: list[dict[str, Any]] | None = None,
    files: list[dict[str, Any]] | None = None,
    duration_ms: int = 0,
    workspace: str = "",
    returncode: int = 0,
    artifact_id: str | None = None,
    syntax_diagnostics: list[dict[str, Any]] | None = None,
    include_source_echo: bool = False,
    workspace_file: str | None = None,
) -> dict[str, Any]:
    """Build a complete :class:`CodeExecutionEnvelope` dict.

    Every exit path calls this so the envelope shape is always uniform.
    """
    is_error = status not in ("ok", None)
    fix_region = (
        _extract_fix_region(stderr, syntax_diagnostics) if is_error else None
    )

    envelope: dict[str, Any] = {
        "status": status,
        "error": error,
        "error_type": error_type,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "result": result,
        "produced_files": produced_files or [],
        "images": images or [],
        "files": files or [],
        "duration_ms": duration_ms,
        "workspace": workspace,
        "returncode": returncode,
        "source_echo": _source_echo(source) if include_source_echo else "",
        "source_length": len(source),
        "artifact_id": artifact_id,
        "syntax_diagnostics": syntax_diagnostics,
        "suggested_fix_region": fix_region,
        "workspace_file": workspace_file,
        "repair_workflow": _repair_workflow_for(error_type) if is_error else None,
    }
    return envelope


def _source_echo(source: str) -> str:
    """Return a truncated copy of *source* suitable for error feedback."""
    if len(source) <= _SOURCE_ECHO_LIMIT:
        return source
    return source[:_SOURCE_ECHO_LIMIT]


def _default_code_workspace_root() -> str:
    try:
        from leagent.config.constants import CODE_EXEC_ROOT

        p = CODE_EXEC_ROOT.resolve()
        p.mkdir(parents=True, exist_ok=True)
        return str(p)
    except Exception:  # noqa: BLE001
        return "/tmp/leagent-code-exec"


@dataclass(frozen=True)
class CodeExecutionConfig:
    """Centralised defaults for the code execution sandbox."""

    workspace_root: str = field(default_factory=_default_code_workspace_root)
    default_timeout_sec: float = 15.0
    max_timeout_sec: float = 120.0
    max_inline_file_bytes: int = 1 * 1024 * 1024
    max_inline_total_bytes: int = 4 * 1024 * 1024
    max_workspace_bytes: int = 64 * 1024 * 1024
    default_memory_bytes: int = 256 * 1024 * 1024
    default_file_bytes: int = 64 * 1024 * 1024
    default_open_files: int = 64
    default_max_processes: int = 32
    allow_env: tuple[str, ...] = field(default_factory=tuple)
    #: Extra top-level names allowed for ``import`` inside the sandbox subprocess (merged with stdlib allow-list in ``runner.py``).
    extra_import_roots: tuple[str, ...] = ()
    #: Import policy passed to the subprocess runner: stdlib, extended, or unrestricted.
    import_tier: str = "stdlib"
    #: Namespace isolation mode for the subprocess runner.
    isolation_mode: str = "auto"


def _extra_import_roots_from_settings(raw: str) -> tuple[str, ...]:
    text = (raw or "").strip()
    if not text:
        return ()
    seen: dict[str, None] = {}
    for part in text.split(","):
        root = part.strip().split(".", 1)[0]
        if root and root not in seen:
            seen[root] = None
    return tuple(seen.keys())


def build_default_code_execution_config() -> CodeExecutionConfig:
    """Resolve sandbox defaults from :class:`~leagent.config.settings.Settings`."""
    from pathlib import Path

    from leagent.config.settings import get_settings

    s = get_settings()
    raw = (s.code_execution_workspace_root or "").strip()
    if raw:
        ws_root = str(Path(raw).expanduser().resolve())
    else:
        ws_root = _default_code_workspace_root()
    Path(ws_root).mkdir(parents=True, exist_ok=True)

    extra_roots = _extra_import_roots_from_settings(s.code_execution_extra_import_roots)
    import_tier = (s.code_execution_import_tier or "").strip().lower()
    permissive = getattr(s, "code_execution_permissive", False)

    if s.is_single_machine_profile:
        cfg = CodeExecutionConfig(
            workspace_root=ws_root,
            default_timeout_sec=60.0,
            max_timeout_sec=900.0,
            max_inline_file_bytes=2 * 1024 * 1024,
            max_inline_total_bytes=8 * 1024 * 1024,
            max_workspace_bytes=256 * 1024 * 1024,
            default_memory_bytes=1024 * 1024 * 1024,
            default_file_bytes=128 * 1024 * 1024,
            default_open_files=512,
            default_max_processes=256,
            allow_env=(
                "PORT",
                "HOST",
                "HTTP_HOST",
                "HTTP_PORT",
                "UVICORN_PORT",
                "FLASK_RUN_PORT",
            ),
            extra_import_roots=extra_roots,
            import_tier=import_tier or "unrestricted",
            isolation_mode=(s.code_execution_isolation_mode or "auto").strip().lower(),
        )
        return _apply_runtime_profile_overrides(cfg, s)

    if permissive:
        cfg = CodeExecutionConfig(
            workspace_root=ws_root,
            default_timeout_sec=60.0,
            max_timeout_sec=600.0,
            max_inline_file_bytes=2 * 1024 * 1024,
            max_inline_total_bytes=8 * 1024 * 1024,
            max_workspace_bytes=256 * 1024 * 1024,
            default_memory_bytes=1024 * 1024 * 1024,
            default_file_bytes=128 * 1024 * 1024,
            default_open_files=512,
            default_max_processes=128,
            allow_env=(),
            extra_import_roots=extra_roots,
            import_tier=import_tier or "unrestricted",
            isolation_mode=(s.code_execution_isolation_mode or "auto").strip().lower(),
        )
        return _apply_runtime_profile_overrides(cfg, s)

    cfg = CodeExecutionConfig(
        workspace_root=ws_root,
        default_timeout_sec=30.0,
        max_timeout_sec=300.0,
        max_inline_file_bytes=2 * 1024 * 1024,
        max_inline_total_bytes=8 * 1024 * 1024,
        max_workspace_bytes=128 * 1024 * 1024,
        default_memory_bytes=512 * 1024 * 1024,
        default_file_bytes=128 * 1024 * 1024,
        default_open_files=256,
        default_max_processes=64,
        allow_env=(),
        extra_import_roots=extra_roots,
        import_tier=import_tier or "extended",
        isolation_mode=(s.code_execution_isolation_mode or "auto").strip().lower(),
    )
    return _apply_runtime_profile_overrides(cfg, s)


def _apply_runtime_profile_overrides(cfg: CodeExecutionConfig, settings: Any) -> CodeExecutionConfig:
    from leagent.agent.runtime_profile import resolve_runtime_budget

    budget = resolve_runtime_budget(settings=settings)
    if budget.name == "standard":
        return cfg
    return replace(
        cfg,
        default_timeout_sec=max(cfg.default_timeout_sec, budget.code_execution_default_timeout_sec),
        max_timeout_sec=max(cfg.max_timeout_sec, budget.code_execution_max_timeout_sec),
    )


def _configured_code_execution_ceiling(settings: Any) -> float:
    return max(
        float(getattr(settings, "code_execution_long_max_timeout_sec", 0) or 0),
        float(getattr(settings, "code_execution_extended_max_timeout_sec", 0) or 0),
    )


class CodeExecutionTool(BaseTool):
    """Execute a Python script in an isolated subprocess sandbox.

    Shared state is kept on the tool instance (not in the context) so a
    single workspace manager survives across runs and can enforce idle
    cleanup. A future rework might plumb the manager through
    :class:`ServiceManager`; for now the tool owns it directly which
    matches how other stateful util tools (cache manager) are wired.
    """

    name = "code_execution"
    description = (
        "Run Python inside an isolated subprocess sandbox with CPU/memory "
        "caps, a sanitized environment, and a persistent per-session "
        "workspace as cwd. Use this for focused computation, data inspection, "
        "and file generation. Keep tool arguments valid JSON; assign a "
        "concise JSON-serialisable `result` for summaries, and write large "
        "outputs to files so they are returned as `produced_files`. "
        "Optional `skill_name` syncs that skill's declared Python packages "
        "(via uv) before execution when auto-install is enabled. "
        "When generating PDF (ReportLab), DOCX, PPTX, or Excel with mixed "
        "Chinese and English, use pan-Unicode fonts and OS-aware font paths "
        "or names (see the document_fonts policy in the system prompt)."
    )
    category = ToolCategory.CODE
    version = "1.0.0"
    aliases = ["python_run", "run_code", "exec_python"]
    search_hint = "python sandbox subprocess rlimit code execute run script interpreter"
    is_concurrency_safe = False
    is_read_only = False
    is_destructive = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000

    def __init__(self, *, config: CodeExecutionConfig | None = None) -> None:
        cfg = config if config is not None else build_default_code_execution_config()
        self._config = cfg
        try:
            from leagent.config.settings import get_settings

            configured_ceiling = _configured_code_execution_ceiling(get_settings())
        except Exception:  # noqa: BLE001
            configured_ceiling = 0
        self.timeout_sec = int(max(cfg.max_timeout_sec, configured_ceiling)) + 10
        self._workspaces = WorkspaceManager(
            cfg.workspace_root,
            max_workspace_bytes=cfg.max_workspace_bytes,
        )
        self._sandbox = SubprocessSandbox(
            python_exe=resolve_backend_python_executable(),
            default_timeout_sec=cfg.default_timeout_sec,
            default_memory_bytes=cfg.default_memory_bytes,
            default_file_bytes=cfg.default_file_bytes,
            default_open_files=cfg.default_open_files,
            default_max_processes=cfg.default_max_processes,
            allow_env=cfg.allow_env,
            extra_import_roots=cfg.extra_import_roots,
            import_tier=cfg.import_tier,
            isolation_mode=cfg.isolation_mode,
        )

    @property
    def parameters(self) -> dict[str, Any]:
        cfg = self._config
        return {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": (
                        "Complete Python source to execute. Omit when using "
                        "`source_blob_id`. When inlined here, the tool call must "
                        "remain valid JSON (escape newlines and quotes). Prefer "
                        "`tool_argument_blob` + `source_blob_id` for large programs."
                    ),
                },
                "source_blob_id": {
                    "type": "string",
                    "description": (
                        "Finalized UTF-8 blob from `tool_argument_blob` containing "
                        "the Python program. Consumed on success—avoids giant "
                        "escaped JSON strings in `source`."
                    ),
                },
                "inputs": {
                    "type": "object",
                    "description": (
                        "JSON-serialisable mapping injected as module-level "
                        "globals. Put structured parameters here instead of "
                        "string-concatenating untrusted values into source."
                    ),
                    "default": {},
                },
                "timeout_sec": {
                    "type": "number",
                    "description": "Wall-clock limit in seconds.",
                    "default": cfg.default_timeout_sec,
                    "minimum": 0.1,
                    "maximum": cfg.max_timeout_sec,
                },
                "memory_bytes": {
                    "type": "integer",
                    "description": "Address-space cap (bytes).",
                    "minimum": 16 * 1024 * 1024,
                    "maximum": 2 * 1024 * 1024 * 1024,
                },
                "import_tier": {
                    "type": "string",
                    "description": (
                        "Optional import policy override for this run. "
                        "`stdlib` permits the curated stdlib roots, "
                        "`extended` adds common data/visualization packages, "
                        "and `unrestricted` disables the import hook."
                    ),
                    "enum": ["stdlib", "extended", "unrestricted"],
                    "default": cfg.import_tier,
                },
                "files": {
                    "type": "array",
                    "description": (
                        "Optional inline files to stage into the sandbox "
                        "workspace before execution. Paths must be relative; "
                        "use this only for small text/base64 inputs."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "content": {"type": "string"},
                            "encoding": {
                                "type": "string",
                                "enum": ["utf-8", "base64"],
                                "default": "utf-8",
                            },
                        },
                        "required": ["path", "content"],
                    },
                    "default": [],
                },
                "reset_workspace": {
                    "type": "boolean",
                    "description": (
                        "If true, wipe the session workspace before "
                        "executing (start from a clean state)."
                    ),
                    "default": False,
                },
                "skill_name": {
                    "type": "string",
                    "description": (
                        "Optional Agent Skill name. When set, declared Python "
                        "dependencies for that skill (requirements.txt, pyproject, "
                        "metadata.leagent.python_dependencies) are synced into this "
                        "process interpreter via `uv pip install` before running "
                        "(if LEAGENT_SKILL_PYTHON_DEPS_AUTO_INSTALL is enabled)."
                    ),
                },
                "skip_syntax_check": {
                    "type": "boolean",
                    "description": (
                        "When false (default), parse-check Python with ast before "
                        "spawning the sandbox so syntax errors return immediately "
                        "without subprocess overhead."
                    ),
                    "default": False,
                },
                "workspace_file": {
                    "type": "string",
                    "description": (
                        "Relative path inside the session workspace to use as "
                        "the source. If the file exists it is read as the "
                        "program (omit `source` / `source_blob_id`). The "
                        "last-executed source is always persisted as "
                        "`__last_source__.py` so you can edit it with "
                        "`project_edit` and re-execute by passing "
                        "`workspace_file=__last_source__.py` without "
                        "re-transmitting the full source."
                    ),
                },
            },
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Running Python in sandbox"

    def coerce_tool_result(self, raw: Any, *, duration_ms: int, attempt: int) -> ToolResult:
        if isinstance(raw, dict):
            status = str(raw.get("status") or "")
            if status and status != "ok":
                err = str(raw.get("error") or status or "execution failed")
                return ToolResult.fail(err, duration_ms=duration_ms, data=raw, attempts=attempt)
        return ToolResult.ok(raw, duration_ms=duration_ms, attempts=attempt)

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        # Phase 1: Generation — resolve source, validate, create artifact
        source, artifact = await self._phase_generate(params, context)
        if isinstance(source, dict):
            return source  # early error envelope from generation phase

        # Phase 2: Execution — workspace setup, sandbox dispatch, result capture
        return await self._phase_execute(source, artifact, params, context)

    async def _phase_generate(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> tuple[str, "CodeArtifact | None"] | tuple[dict[str, Any], None]:
        """Phase 1: resolve source text, validate syntax, create artifact.

        Returns ``(source, artifact)`` on success, or
        ``(error_envelope_dict, None)`` if execution should be blocked.
        """
        ws_file_raw = params.get("workspace_file")
        if isinstance(ws_file_raw, str) and ws_file_raw.strip():
            source = self._read_workspace_file(ws_file_raw.strip(), context)
        else:
            from leagent.project.fs import resolve_content

            try:
                source = await resolve_content(
                    params, context,
                    inline_key="source", blob_key="source_blob_id",
                )
            except ValueError as exc:
                raise ValueError(
                    str(exc) or (
                        "Provide non-empty `source`, `source_blob_id`, or "
                        "`workspace_file` pointing to an existing file in "
                        "the session workspace."
                    )
                ) from exc

        skip_syntax = bool(params.get("skip_syntax_check", False))
        artifact = await self._prepare_artifact(source, params, context, skip_syntax)

        if artifact is not None and artifact.syntax_valid is False:
            from leagent.code.pipeline import CodeGenerationPipeline

            if CodeGenerationPipeline.should_block(artifact):
                prim = artifact.diagnostics[0] if artifact.diagnostics else None
                msg = prim["message"] if prim else "Python syntax error"
                ws_path = ""
                persisted: str | None = None
                try:
                    ws = self._get_workspace(context)
                    ws_path = str(ws.path)
                    persisted = self._persist_source(source, context)
                except Exception:  # noqa: BLE001
                    ws_path = ""
                return _build_envelope(
                    status="error",
                    source=source,
                    error=msg,
                    error_type="syntax",
                    workspace=ws_path,
                    returncode=-1,
                    artifact_id=artifact.artifact_id,
                    syntax_diagnostics=artifact.diagnostics,
                    include_source_echo=True,
                    workspace_file=persisted,
                ), None

        if artifact is None and not skip_syntax:
            from leagent.services.syntax_validation import validate_syntax

            syn = validate_syntax(
                source,
                language="python",
                filename="<code_execution>",
                context_lines=2,
            )
            if not syn.valid:
                prim = syn.diagnostics[0] if syn.diagnostics else None
                msg = prim.message if prim else "Python syntax error"
                ws_path = ""
                persisted: str | None = None
                try:
                    ws = self._get_workspace(context)
                    ws_path = str(ws.path)
                    persisted = self._persist_source(source, context)
                except Exception:  # noqa: BLE001
                    ws_path = ""
                return _build_envelope(
                    status="error",
                    source=source,
                    error=msg,
                    error_type="syntax",
                    workspace=ws_path,
                    returncode=-1,
                    syntax_diagnostics=[d.to_dict() for d in syn.diagnostics],
                    include_source_echo=True,
                    workspace_file=persisted,
                ), None

        return source, artifact

    async def _phase_execute(
        self,
        source: str,
        artifact: "CodeArtifact | None",
        params: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        """Phase 2: workspace setup, dependency install, sandbox dispatch, result capture."""
        cfg = self._config
        artifact_id = artifact.artifact_id if artifact else None

        inputs = params.get("inputs") or {}
        if not isinstance(inputs, dict):
            raise ValueError("'inputs' must be an object of name -> value pairs")

        runtime_profile = ""
        try:
            runtime_profile = str((context.extra or {}).get("runtime_profile") or "")
        except Exception:  # noqa: BLE001
            runtime_profile = ""
        max_timeout = float(cfg.max_timeout_sec)
        default_timeout = float(cfg.default_timeout_sec)
        if runtime_profile:
            from leagent.agent.runtime_profile import resolve_runtime_budget

            budget = resolve_runtime_budget(runtime_profile)
            if budget.name != "standard":
                max_timeout = max(max_timeout, float(budget.code_execution_max_timeout_sec))
                default_timeout = max(default_timeout, float(budget.code_execution_default_timeout_sec))

        timeout = float(params.get("timeout_sec") or default_timeout)
        if timeout <= 0 or timeout > max_timeout:
            raise ValueError(
                f"'timeout_sec' must be in (0, {max_timeout:g}], got {timeout}"
            )
        memory_bytes = params.get("memory_bytes")
        import_tier = (
            str(params.get("import_tier") or cfg.import_tier).strip().lower()
        )
        if import_tier not in {"stdlib", "extended", "unrestricted"}:
            raise ValueError(
                "'import_tier' must be one of: stdlib, extended, unrestricted"
            )
        files = params.get("files") or []
        reset_workspace = bool(params.get("reset_workspace") or False)
        skill_name_raw = params.get("skill_name")
        skill_name = (
            str(skill_name_raw).strip()
            if isinstance(skill_name_raw, str) and skill_name_raw.strip()
            else ""
        )

        if skill_name:
            from leagent.skills.python_deps import ensure_skill_python_deps
            from leagent.tools.skills import resolve_skills_manager

            manager = await resolve_skills_manager()
            if not manager:
                logger.debug("code_execution_skill_name_no_manager", skill_name=skill_name)
            else:
                sk = manager.get_skill(skill_name)
                if not sk:
                    logger.debug("code_execution_skill_name_not_found", skill_name=skill_name)
                else:
                    dep_result = await ensure_skill_python_deps(sk)
                    if not dep_result.get("ok"):
                        return _build_envelope(
                            status="error",
                            source=source,
                            error=dep_result.get(
                                "error", "Skill Python dependency install failed."
                            ),
                            error_type="dependency",
                            returncode=-1,
                            artifact_id=artifact_id,
                            include_source_echo=True,
                        )

        workspace = self._get_workspace(context)
        if reset_workspace:
            workspace.reset()

        extra_ctx = getattr(context, "extra", None) or {}
        proj_roots = extra_ctx.get("project_roots")
        if isinstance(proj_roots, list) and proj_roots:
            if "timeout_sec" not in params:
                timeout = min(cfg.max_timeout_sec, max(timeout, 60.0))
            logger.info(
                "code_execution_with_project_binding",
                project_roots_count=len(proj_roots),
                first_root_preview=str(proj_roots[0])[:200],
            )

        self._stage_files(workspace, files)
        scan_roots = self._scan_roots_for(context)

        result = await self._sandbox.execute(
            source,
            workspace=workspace,
            globals=inputs,
            timeout_sec=timeout,
            memory_bytes=memory_bytes,
            import_tier=import_tier,
            extra_scan_roots=scan_roots,
        )

        if result.status == "timeout":
            persisted = self._persist_source(source, context)
            return _build_envelope(
                status="timeout",
                source=source,
                error=result.error or "execution timed out",
                error_type="timeout",
                stdout=result.stdout,
                stderr=result.stderr,
                stdout_truncated=result.stdout_truncated,
                stderr_truncated=result.stderr_truncated,
                duration_ms=result.duration_ms or int(timeout * 1000),
                workspace=str(workspace.path),
                artifact_id=artifact_id,
                include_source_echo=True,
                workspace_file=persisted,
            )

        try:
            workspace.enforce_quota()
        except Exception as exc:  # noqa: BLE001 - surfaced but non-fatal
            logger.warning("code_execution_quota_exceeded", error=str(exc))

        from leagent.services.session.artifacts import (
            ingest_previewable_produced_files,
            strip_base64_from_text,
            strip_inline_base64_payloads,
            _scan_image_preview_urls,
        )

        persisted_file = self._persist_source(source, context)

        is_error = result.status not in ("ok", None)
        error_type: ErrorType | None = "runtime" if is_error else None

        produced_files = list(result.produced_files or [])
        managed_artifacts: list[dict[str, Any]] = []
        image_artifacts = list(result.image_artifacts or [])
        file_artifacts = list(result.file_artifacts or [])
        if not is_error and produced_files:
            produced_files, managed_artifacts = await ingest_previewable_produced_files(
                context,
                produced_files,
                workspace=str(workspace.path),
            )
            from leagent.code.sandbox import split_produced_artifacts

            image_artifacts, file_artifacts = split_produced_artifacts(produced_files)

        envelope = strip_inline_base64_payloads(
            _build_envelope(
                status=result.status,
                source=source,
                error=result.error,
                error_type=error_type,
                stdout=strip_base64_from_text(result.stdout),
                stderr=result.stderr,
                stdout_truncated=result.stdout_truncated,
                stderr_truncated=result.stderr_truncated,
                result=result.result,
                produced_files=produced_files,
                images=image_artifacts,
                files=file_artifacts,
                duration_ms=result.duration_ms,
                workspace=str(workspace.path),
                returncode=result.returncode,
                artifact_id=artifact_id,
                include_source_echo=is_error,
                workspace_file=persisted_file,
            )
        )
        if managed_artifacts:
            envelope["managed_artifacts"] = managed_artifacts
            downloadable = [
                a for a in managed_artifacts
                if a.get("download_url") or a.get("id")
            ]
            if downloadable:
                cites = []
                for a in downloadable[:8]:
                    name = a.get("filename") or a.get("name") or "file"
                    fid = a.get("id") or ""
                    url = a.get("download_url") or ""
                    ver = a.get("version")
                    ver_s = f" v{ver}" if isinstance(ver, int) and ver > 1 else ""
                    cites.append(
                        f"{name}{ver_s} (file_id={fid}"
                        + (f", download={url}" if url else "")
                        + ")"
                    )
                envelope["download_hint"] = (
                    "Cite managed download URLs / file_id for the user — never "
                    "sandbox workspace paths. Latest versions: "
                    + "; ".join(cites)
                )
            quality_failures = [
                str(a.get("quality_error") or a.get("filename") or "artifact")
                for a in managed_artifacts
                if a.get("quality_passed") is False
            ]
            if not quality_failures:
                quality_failures = [
                    str(p.get("quality_error") or p.get("file_path") or "file")
                    for p in produced_files
                    if isinstance(p, dict) and p.get("quality_passed") is False
                ]
            if quality_failures:
                envelope["quality_passed"] = False
                envelope["quality_error"] = "; ".join(quality_failures)[:800]
            else:
                envelope["quality_passed"] = True
        preview_paths = _scan_image_preview_urls(envelope)
        if preview_paths:
            envelope["display_hint"] = (
                "Show generated images with preview URLs in markdown "
                "(`![caption](preview_url)`) or GenUI `Image` nodes — "
                "never embed `data:image/...;base64,...` in chat text. "
                f"Available: {', '.join(preview_paths)}"
            )

        from leagent.code.pipeline import record_operation

        record_operation(
            context,
            tool="code_execution",
            kind="execute",
            summary=f"{result.status} ({result.duration_ms}ms)",
            success=not is_error,
            artifact_id=artifact_id,
        )
        return envelope

    @staticmethod
    async def _prepare_artifact(
        source: str,
        params: dict[str, Any],
        context: "ToolContext",
        skip_syntax: bool,
    ) -> "CodeArtifact | None":
        """Build a CodeArtifact via the pipeline if available."""
        from leagent.code.pipeline import get_pipeline

        pipeline = get_pipeline(context)
        if pipeline is None:
            return None
        from leagent.code.artifacts import ArtifactKind

        timeout_val = params.get("timeout_sec")
        import_tier_val = params.get("import_tier")
        return await pipeline.prepare(
            kind=ArtifactKind.EXECUTE,
            source=source,
            language="python",
            origin_tool="code_execution",
            context=context,
            skip_validation=skip_syntax,
            metadata={
                "timeout_sec": timeout_val,
                "import_tier": import_tier_val,
                "has_inputs": bool(params.get("inputs")),
            },
        )

    def _get_workspace(self, context: ToolContext) -> Workspace:
        metadata = {
            "user_id": context.user_id or "",
            "session_id": context.session_id or "",
            "task_id": context.task_id or "",
        }
        return self._workspaces.get(
            user_id=context.user_id,
            session_id=context.session_id,
            metadata=metadata,
        )

    def _scan_roots_for(self, context: ToolContext) -> tuple[str, ...]:
        """Directories outside the workspace cwd whose new files should be reported.

        We expose the per-session uploads directory so files written there
        (e.g. ``/<upload_root>/<session_id>/report.pdf``) are surfaced in
        ``produced_files`` and can be ingested as session attachments by the
        controller. Without this, a script that writes outside its
        ``cwd`` would silently disappear from the chat workspace. Shared system
        temp roots are intentionally excluded: recursively diffing ``/tmp`` can
        attribute files created by unrelated concurrent processes to this turn.
        """
        roots: list[str] = []
        seen: set[str] = set()

        def _add(path: str | None) -> None:
            if not path:
                return
            try:
                resolved = str(Path(path).expanduser().resolve())
            except OSError:
                return
            if resolved in seen:
                return
            seen.add(resolved)
            roots.append(resolved)

        session_id = context.session_id
        if session_id:
            try:
                from leagent.services.session.paths import get_session_path_registry

                _add(str(get_session_path_registry().uploads_dir(session_id)))
            except Exception:  # noqa: BLE001
                logger.debug("scan_roots_settings_unavailable", exc_info=True)

        extra_ctx = getattr(context, "extra", None) or {}
        for key in ("session_uploads_dir", "session_upload_dir"):
            value = extra_ctx.get(key)
            if isinstance(value, str):
                _add(value)

        return tuple(roots)

    def _stage_files(
        self,
        workspace: Workspace,
        files: list[dict[str, Any]],
    ) -> None:
        import base64

        cfg = self._config
        if not files:
            return
        total = 0
        for entry in files:
            if not isinstance(entry, dict):
                raise ValueError("Each item in 'files' must be an object")
            rel_path = entry.get("path")
            content = entry.get("content")
            encoding = entry.get("encoding", "utf-8")
            if not rel_path or content is None:
                raise ValueError("Each file needs a 'path' and 'content'")
            if encoding == "base64":
                raw = base64.b64decode(content)
            elif encoding == "utf-8":
                raw = str(content).encode("utf-8")
            else:
                raise ValueError(f"Unsupported encoding: {encoding}")
            if len(raw) > cfg.max_inline_file_bytes:
                raise ValueError(
                    f"File '{rel_path}' exceeds {cfg.max_inline_file_bytes} bytes"
                )
            total += len(raw)
            if total > cfg.max_inline_total_bytes:
                raise ValueError(
                    f"Staged files exceed {cfg.max_inline_total_bytes} bytes total"
                )
            workspace.write_bytes(str(rel_path), raw)

    _LAST_SOURCE_NAME = "__last_source__.py"

    def _read_workspace_file(self, rel_path: str, context: ToolContext) -> str:
        """Read a file from the session workspace as source text."""
        workspace = self._get_workspace(context)
        target = workspace.path / rel_path
        try:
            resolved = target.resolve()
            resolved.relative_to(workspace.path.resolve())
        except (OSError, ValueError) as exc:
            raise ValueError(
                f"workspace_file {rel_path!r} escapes the workspace: {exc}"
            ) from exc
        if not resolved.is_file():
            raise ValueError(
                f"workspace_file {rel_path!r} does not exist in the session "
                f"workspace ({workspace.path}). Run with `source` first, "
                "then re-execute via `workspace_file`."
            )
        return resolved.read_text(encoding="utf-8", errors="replace")

    def _persist_source(self, source: str, context: ToolContext) -> str | None:
        """Write the executed source to ``__last_source__.py`` for incremental repair."""
        try:
            workspace = self._get_workspace(context)
            workspace.write_bytes(
                self._LAST_SOURCE_NAME,
                source.encode("utf-8"),
            )
            return self._LAST_SOURCE_NAME
        except Exception:  # noqa: BLE001
            logger.debug("persist_last_source_error", exc_info=True)
            return None

    def gc_workspaces(self) -> list[str]:
        """Expose the workspace GC for external schedulers."""
        return self._workspaces.gc()
