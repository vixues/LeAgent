"""Base tool framework for LeAgent.

Provides foundational abstractions for all tools: registration, schema validation,
execution lifecycle, permission checks, result-size budgeting, and error handling.

Modeled after the reference Tool.ts / buildTool() architecture with Python idioms.
"""

from __future__ import annotations

import asyncio
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, Callable, Literal

import jsonschema
import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from leagent.core.config import Settings
    from leagent.services.llm.client import LLMClient

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ToolCategory(str, Enum):
    """Tool category for organisation and filtering."""

    DOC = "doc"
    WEB = "web"
    DATA = "data"
    GEN = "gen"
    IMAGE = "image"
    CHART = "chart"
    INTEGRATION = "integration"
    UTIL = "util"
    CANVAS = "canvas"
    WORKFLOW = "workflow"
    CODE = "code"
    SKILLS = "skills"


class ToolCapability(str, Enum):
    """Fine-grained capability flags for policy-based tool filtering."""

    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    NETWORK = "network"
    CODE_EXEC = "code_exec"
    SHELL = "shell"
    DATABASE = "database"
    LLM_CALL = "llm_call"
    DANGEROUS = "dangerous"


# ---------------------------------------------------------------------------
# Result envelope
# ---------------------------------------------------------------------------


@dataclass
class ToolResult:
    """Uniform result envelope for every tool execution."""

    success: bool
    data: Any = None
    error: str | None = None
    duration_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }

    @classmethod
    def ok(cls, data: Any, duration_ms: int = 0, **metadata: Any) -> ToolResult:
        return cls(success=True, data=data, duration_ms=duration_ms, metadata=metadata)

    @classmethod
    def fail(
        cls,
        error: str,
        duration_ms: int = 0,
        *,
        data: Any = None,
        **metadata: Any,
    ) -> ToolResult:
        """Return a failed envelope.

        Optional ``data`` holds structured detail (stderr payloads, tool-native
        dicts, …) surfaced to the LLM via :func:`leagent.agent.query._serialize_result`.
        """
        return cls(
            success=False,
            error=error,
            data=data,
            duration_ms=duration_ms,
            metadata=dict(metadata),
        )


@dataclass
class ToolProgressEvent:
    """Progress event emitted by streaming tools."""

    type: str  # "output", "status", "file_produced", "error"
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.monotonic)


class NonRetryableToolError(Exception):
    """Raised for deterministic tool errors that retrying cannot fix."""


# ---------------------------------------------------------------------------
# Validation result (mirrors reference ValidationResult)
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Result of input validation before execution."""

    valid: bool
    message: str = ""
    error_code: int = 0


# ---------------------------------------------------------------------------
# Progress callback type (mirrors reference ToolCallProgress)
# ---------------------------------------------------------------------------

ToolProgressCallback = Callable[[dict[str, Any]], None]


# ---------------------------------------------------------------------------
# Tool context
# ---------------------------------------------------------------------------


@dataclass
class ToolContext:
    """Shared context passed to every tool invocation.

    Carries all dependencies a tool might need: DB sessions, storage clients,
    user identity, abort signals, and an extensible ``extra`` dict.

    ``extra["attachments"]`` may contain a list of absolute file paths
    that are authorised for the current request (populated by the chat
    endpoint from the user-uploaded files).

    ``extra["authorized_roots"]`` lists extra directory roots the user
    explicitly granted for this chat session (path sandbox, same rules as
    ``project_roots``).
    """

    user_id: str | None
    session_id: str | None
    task_id: str | None = None
    settings: "Settings | None" = None
    db: "AsyncSession | None" = None
    cache: Any = None
    file_store: Any = None
    llm: "LLMClient | None" = None
    temp_dir: str | None = None
    abort_signal: asyncio.Event | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def with_task(self, task_id: str) -> ToolContext:
        return ToolContext(
            user_id=self.user_id,
            session_id=self.session_id,
            task_id=task_id,
            settings=self.settings,
            db=self.db,
            cache=self.cache,
            file_store=self.file_store,
            llm=self.llm,
            temp_dir=self.temp_dir,
            abort_signal=self.abort_signal,
            extra=self.extra.copy(),
        )

    @property
    def is_aborted(self) -> bool:
        return self.abort_signal is not None and self.abort_signal.is_set()


# ---------------------------------------------------------------------------
# BaseTool
# ---------------------------------------------------------------------------


class BaseTool(ABC):
    """Abstract base for all tools.

    Class-level attributes mirror the reference Tool<> interface:
    - ``aliases``: alternative names for backwards-compat lookup
    - ``search_hint``: keyword phrase for ToolSearch matching
    - ``is_concurrency_safe``: whether parallel dispatch is safe
    - ``is_read_only`` / ``is_destructive``: safety classification
    - ``max_result_size_chars``: output budget before disk persistence
    - ``interrupt_behavior``: what happens on user interrupt
    """

    name: str = ""
    aliases: list[str] = []
    description: str = ""
    category: ToolCategory = ToolCategory.UTIL
    version: str = "1.0.0"
    timeout_sec: int = 60
    max_retries: int = 2
    requires_gpu: bool = False
    search_hint: str = ""

    # Safety / permission properties (fail-closed defaults matching reference)
    is_enabled: bool = True
    is_concurrency_safe: bool = False
    is_read_only: bool = False
    is_destructive: bool = False
    capabilities: set[ToolCapability] = set()
    interrupt_behavior: Literal["cancel", "block"] = "block"
    max_result_size_chars: int = 100_000

    # Path sandbox: top-level param keys that hold filesystem paths.
    # ``path_params`` are validated for read access; ``output_path_params``
    # additionally allow creating new files under the sandbox.
    path_params: tuple[str, ...] = ()
    output_path_params: tuple[str, ...] = ()

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """JSON Schema for tool parameters."""
        ...

    @abstractmethod
    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        """Execute the tool. Subclasses must implement this."""
        ...

    async def stream(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> AsyncIterator[ToolProgressEvent]:
        """Optional streaming execution for long-running tools.

        Default implementation delegates to execute() and yields a single
        completion event. Override in subclasses that support incremental output.
        """
        result = await self.execute(params, context)
        yield ToolProgressEvent(type="complete", data={"result": result})

    # -- Raw argument recovery ---------------------------------------------

    def recover_raw_args(self, raw: str) -> dict[str, Any] | None:
        """Attempt to recover structured parameters from a malformed JSON string.

        When the LLM emits tool-call arguments that fail ``json.loads``,
        the executor stores the raw string under ``{"__raw__": raw}`` and
        calls this method on the tool to attempt tool-specific recovery
        (e.g. extracting a ``source`` field from broken JSON).

        The default implementation returns ``None`` (no recovery).
        Tools with large string fields that commonly break JSON escaping
        should override this to extract their primary payload.
        """
        return None

    # -- Validation (mirrors reference validateInput) ----------------------

    def validate_params(self, params: dict[str, Any]) -> tuple[bool, str | None]:
        """Validate parameters against the JSON schema."""
        try:
            jsonschema.validate(instance=params, schema=self.parameters)
            return True, None
        except jsonschema.ValidationError as e:
            return False, str(e.message)
        except jsonschema.SchemaError as e:
            logger.error("Invalid tool schema", tool=self.name, error=str(e))
            return False, f"Invalid tool schema: {e.message}"

    async def validate_input(self, params: dict[str, Any], context: ToolContext) -> ValidationResult:
        """Semantic input validation beyond JSON schema.

        Override in subclasses for tool-specific checks (e.g. file existence,
        path safety). Called after schema validation, before execution.
        """
        return ValidationResult(valid=True)

    # -- Path sandbox enforcement ------------------------------------------

    def _enforce_path_sandbox(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> None:
        """Validate that all declared path params fall within the sandbox.

        When the sandbox resolves a relative path (e.g. a bare filename)
        to an absolute path inside the sandbox, the param is **rewritten
        in-place** so the tool's ``execute`` method sees the resolved
        path and can open the file without further guesswork.

        Override in subclasses that have nested or non-standard path
        parameters (e.g. ``files[].path``, ``attachments[].path``).

        Raises :class:`PermissionError` on escape.
        """
        from leagent.tools._sandbox.paths import PathSandbox

        request_id = context.extra.get("request_id", context.session_id or "")

        for key in self.path_params:
            val = params.get(key)
            if val and isinstance(val, str):
                resolved = PathSandbox.resolve_safe(
                    val,
                    context=context,
                    allow_create=False,
                    tool_name=self.name,
                    request_id=str(request_id),
                )
                params[key] = str(resolved)

        for key in self.output_path_params:
            val = params.get(key)
            if val and isinstance(val, str):
                resolved = PathSandbox.resolve_safe(
                    val,
                    context=context,
                    allow_create=True,
                    tool_name=self.name,
                    request_id=str(request_id),
                )
                params[key] = str(resolved)

    # -- Result coercion (semantic success vs transport success) ----------

    def coerce_tool_result(self, raw: Any, *, duration_ms: int, attempt: int) -> ToolResult:
        """Map a successful ``execute()`` return value to a :class:`ToolResult`.

        Override in tools whose natural payload uses in-band status fields
        (e.g. ``code_execution``'s ``status != "ok"``) so :attr:`ToolResult.success`
        matches semantic outcome.
        """
        return ToolResult.ok(raw, duration_ms=duration_ms, attempts=attempt)

    # -- Main entry point --------------------------------------------------

    async def run(
        self,
        params: dict[str, Any],
        context: ToolContext,
        *,
        on_progress: ToolProgressCallback | None = None,
    ) -> ToolResult:
        """Execute with validation, retries, timeout, and result-size capping."""
        start_time = time.monotonic()

        # 1. Schema validation
        is_valid, error_msg = self.validate_params(params)
        if not is_valid:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.warning("Parameter validation failed", tool=self.name, error=error_msg)
            return ToolResult.fail(f"Invalid parameters: {error_msg}", duration_ms=duration_ms)

        # 2. Path sandbox enforcement
        has_sandbox = (
            self.path_params
            or self.output_path_params
            or type(self)._enforce_path_sandbox is not BaseTool._enforce_path_sandbox
        )
        if has_sandbox:
            try:
                self._enforce_path_sandbox(params, context)
            except PermissionError as exc:
                duration_ms = int((time.monotonic() - start_time) * 1000)
                logger.warning("Path sandbox denied", tool=self.name, error=str(exc))
                return ToolResult.fail(str(exc), duration_ms=duration_ms)

        # 3. Semantic validation
        vr = await self.validate_input(params, context)
        if not vr.valid:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            logger.warning("Input validation failed", tool=self.name, message=vr.message)
            return ToolResult.fail(f"Validation error: {vr.message}", duration_ms=duration_ms)

        # 4. Execute with retries
        last_error: str | None = None
        attempts_used = 0

        for attempt in range(1, self.max_retries + 2):
            attempts_used = attempt
            if context.is_aborted:
                duration_ms = int((time.monotonic() - start_time) * 1000)
                return ToolResult.fail("Execution aborted", duration_ms=duration_ms)

            try:
                result = await asyncio.wait_for(
                    self.execute(params, context),
                    timeout=self.timeout_sec,
                )
                duration_ms = int((time.monotonic() - start_time) * 1000)

                # 4. Result-size budget enforcement
                result = self._enforce_result_budget(result)

                coerced = self.coerce_tool_result(result, duration_ms=duration_ms, attempt=attempt)
                if coerced.success:
                    logger.info(
                        "Tool executed successfully",
                        tool=self.name,
                        duration_ms=duration_ms,
                        attempt=attempt,
                    )
                else:
                    logger.warning(
                        "Tool reported semantic failure",
                        tool=self.name,
                        duration_ms=duration_ms,
                        attempt=attempt,
                        error=coerced.error,
                    )
                return coerced

            except asyncio.TimeoutError:
                last_error = f"Tool execution timed out after {self.timeout_sec}s"
                logger.warning("Tool execution timed out", tool=self.name, timeout_sec=self.timeout_sec, attempt=attempt)

            except NonRetryableToolError as e:
                msg = str(e).strip()
                last_error = msg if msg else f"{type(e).__name__} ({e!r})"
                logger.warning(
                    "Tool execution failed without retry",
                    tool=self.name,
                    error=last_error,
                    attempt=attempt,
                )
                break

            except Exception as e:
                msg = str(e).strip()
                last_error = msg if msg else f"{type(e).__name__} ({e!r})"
                logger.error("Tool execution failed", tool=self.name, error=last_error, attempt=attempt, exc_info=True)

            if attempt <= self.max_retries:
                backoff = 2 ** attempt
                logger.info("Retrying tool execution", tool=self.name, backoff_sec=backoff)
                await asyncio.sleep(backoff)

        duration_ms = int((time.monotonic() - start_time) * 1000)
        return ToolResult.fail(last_error or "Unknown error", duration_ms=duration_ms, attempts=attempts_used or 1)

    def _enforce_result_budget(self, result: Any) -> Any:
        """Truncate oversized results to stay within max_result_size_chars."""
        if self.max_result_size_chars == float("inf"):
            return result

        if isinstance(result, str) and len(result) > self.max_result_size_chars:
            return result[: self.max_result_size_chars] + "\n... [truncated]"

        if isinstance(result, dict):
            serialized = json.dumps(result, ensure_ascii=False, default=str)
            if len(serialized) > self.max_result_size_chars:
                result["_truncated"] = True
                result["_original_size"] = len(serialized)

        return result

    # -- Permission check --------------------------------------------------

    def check_permissions(self, params: dict[str, Any], context: ToolContext) -> tuple[bool, str | None]:
        """Tool-specific permission check. Default: allow."""
        return True, None

    # -- Name matching (mirrors reference toolMatchesName) -----------------

    def matches_name(self, name: str) -> bool:
        """Check if this tool matches the given name or any alias."""
        return self.name == name or name in (self.aliases or [])

    # -- Activity description (mirrors reference getActivityDescription) ---

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        """Human-readable present-tense description for spinner display."""
        return None

    # -- Path accessor (mirrors reference getPath) -------------------------

    def get_path(self, params: dict[str, Any]) -> str | None:
        """Return the file path this tool operates on, if applicable."""
        return params.get("file_path") or params.get("path")

    # -- Schema generation -------------------------------------------------

    def to_openai_schema(self) -> dict[str, Any]:
        """OpenAI function-calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_anthropic_schema(self) -> dict[str, Any]:
        """Anthropic tool_use format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }

    def to_generic_schema(self) -> dict[str, Any]:
        """Provider-agnostic schema with search metadata."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "search_hint": self.search_hint,
            "category": self.category.value,
            "is_read_only": self.is_read_only,
            "is_concurrency_safe": self.is_concurrency_safe,
        }

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.name!r}, category={self.category.value!r})>"


# ---------------------------------------------------------------------------
# SyncTool — wraps synchronous execute in a thread pool
# ---------------------------------------------------------------------------


class SyncTool(BaseTool):
    """Base class for tools with synchronous execute implementations."""

    @abstractmethod
    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> Any:
        ...

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.execute_sync, params, context)


# ---------------------------------------------------------------------------
# Tool permission system
# ---------------------------------------------------------------------------


@dataclass
class PermissionResult:
    """Result of a permission check."""

    allowed: bool
    reason: str | None = None
    updated_params: dict[str, Any] | None = None


@dataclass
class ToolPermissionContext:
    """Context for evaluating tool permissions.

    Mirrors the reference ToolPermissionContext with a simplified Python model.
    """

    mode: Literal["default", "auto", "bypass"] = "default"
    always_allow_rules: list[str] = field(default_factory=list)
    always_deny_rules: list[str] = field(default_factory=list)
    always_ask_rules: list[str] = field(default_factory=list)
    bypass_permissions: bool = False
    avoid_permission_prompts: bool = False
    confirm_destructive: bool = False


def check_tool_permission(
    tool: BaseTool,
    params: dict[str, Any],
    context: ToolPermissionContext,
    tool_context: ToolContext | None = None,
) -> PermissionResult:
    """Multi-layer permission check (deny → allow → bypass → tool-specific).

    ``tool_context`` should be the same :class:`ToolContext` the tool will
    execute under, so per-tool checks can consult ``user_id`` / ``session_id``
    (e.g. per-user rate limits, scoped ACLs). If omitted, a minimal anonymous
    context is constructed as a fallback.
    """
    import fnmatch

    if context.bypass_permissions:
        return PermissionResult(allowed=True)

    for pattern in context.always_deny_rules:
        if fnmatch.fnmatch(tool.name, pattern):
            return PermissionResult(allowed=False, reason=f"Tool '{tool.name}' is in deny list")

    for pattern in context.always_allow_rules:
        if fnmatch.fnmatch(tool.name, pattern):
            return PermissionResult(allowed=True)

    for pattern in context.always_ask_rules:
        if fnmatch.fnmatch(tool.name, pattern):
            return PermissionResult(
                allowed=False,
                reason=(
                    f"Tool '{tool.name}' requires explicit user approval "
                    "(always_ask_rules / configure always_allow to bypass)"
                ),
            )

    if (
        context.confirm_destructive
        and not context.bypass_permissions
        and not context.avoid_permission_prompts
        and getattr(tool, "is_destructive", False)
    ):
        return PermissionResult(
            allowed=False,
            reason=f"Destructive tool '{tool.name}' blocked pending operator policy",
        )

    ctx = tool_context or ToolContext(user_id=None, session_id=None)
    allowed, reason = tool.check_permissions(params, ctx)
    return PermissionResult(allowed=allowed, reason=reason)


# ---------------------------------------------------------------------------
# build_tool() factory (mirrors reference buildTool())
# ---------------------------------------------------------------------------


def build_tool(definition: type[BaseTool]) -> BaseTool:
    """Instantiate a tool with validated safe defaults (fail-closed)."""
    instance = definition()
    if not hasattr(instance, "is_enabled"):
        instance.is_enabled = True  # type: ignore[attr-defined]
    if not hasattr(instance, "is_concurrency_safe"):
        instance.is_concurrency_safe = False  # type: ignore[attr-defined]
    if not hasattr(instance, "is_read_only"):
        instance.is_read_only = False  # type: ignore[attr-defined]
    if not hasattr(instance, "is_destructive"):
        instance.is_destructive = False  # type: ignore[attr-defined]
    return instance
