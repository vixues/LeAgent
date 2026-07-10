"""Tool result normalisation and error-recovery helpers.

This module hosts the two small utilities every agent path shares:

* :class:`ResultProcessor` — normalises tool outputs into the serialised
  string the LLM actually consumes (same algorithm
  :func:`leagent.agent.query._serialize_result` uses) and surfaces
  structured artefacts (files, artifact refs, produced files) for
  downstream telemetry.
* :class:`ErrorRecovery` — middleware that wraps a tool dispatch and
  retries on recoverable errors (timeouts, rate limits, validation
  glitches) using exception types when available, falling back to string
  matching for legacy paths. Pluggable handler registration is still
  supported for domain-specific recoveries.

Both components are deliberately independent of whichever loop is
driving the agent: they accept a bare :class:`ToolCall` plus the
tools-layer :class:`ToolResult` envelope and optionally an
:class:`AgentContext` (used for logging).

The :meth:`ErrorRecovery.as_middleware` factory returns a coroutine
that can be slotted into ``query._dispatch_tools`` so the
:class:`QueryEngine` path gets the same safety net the legacy ReAct
loop had.
"""

from __future__ import annotations

import asyncio
import json
import random
from typing import TYPE_CHECKING, Any, Awaitable, Callable

import structlog

from leagent.agent.base import AgentContext, ToolCall, ToolResult
from leagent.agent.query import ToolResultMessage
from leagent.exceptions.tool import (
    ToolExecutionError,
    ToolTimeoutError,
    ToolValidationError,
)
from leagent.tools.base import ToolResult as BaseToolResult

if TYPE_CHECKING:  # pragma: no cover
    from leagent.tools.executor import ToolExecutor

logger = structlog.get_logger(__name__)

# Cap serialised tool payloads sent back into the model transcript (tokens).
_LLM_TOOL_STRING_CAP = 96_000
_TRUNCATION_NOTICE = (
    "\n...[output truncated for context cap; narrow the query, "
    "use files_with_matches_only, max_matches, offset/limit, or a smaller path]..."
)


# ---------------------------------------------------------------------------
# Result normalisation
# ---------------------------------------------------------------------------


class ResultProcessor:
    """Normalise tool outputs into agent-friendly shapes.

    The helpers are stateless (``@staticmethod``) so they are safe to
    call from sync paths (``execute_sync`` stubs, tests) as well as the
    async query loop.
    """

    # Keys we hoist from ``ToolResult.data`` into a flat file list.
    _FILE_KEYS: tuple[str, ...] = (
        "file_path",
        "output_path",
        "path",
        "produced_file",
    )
    # Keys whose *values* are lists of file paths.
    _FILE_LIST_KEYS: tuple[str, ...] = (
        "files",
        "produced_files",
        "artifacts",
    )

    @staticmethod
    def normalize(result: Any) -> dict[str, Any]:
        """Coerce arbitrary return values into a uniform dict shape."""
        if result is None:
            return {"success": True, "data": None}
        if isinstance(result, dict):
            return result
        if isinstance(result, (list, tuple)):
            return {"success": True, "data": list(result), "count": len(result)}
        if isinstance(result, str):
            return {"success": True, "data": result, "length": len(result)}
        if isinstance(result, (int, float, bool)):
            return {"success": True, "data": result}
        if hasattr(result, "model_dump"):
            return result.model_dump()
        if hasattr(result, "__dict__"):
            return {"success": True, "data": vars(result)}
        return {"success": True, "data": str(result)}

    @staticmethod
    def summarize(result: ToolResult, max_length: int = 500) -> str:
        """Produce a human-readable blurb from a :class:`ToolResult`."""
        if not result.success:
            return f"Error: {result.error}"

        data = result.data
        if data is None:
            return "Completed successfully (no output)"
        if isinstance(data, str):
            return data if len(data) <= max_length else data[: max_length - 3] + "..."
        if isinstance(data, dict):
            keys = list(data.keys())
            if len(keys) <= 5:
                return f"Result with keys: {', '.join(keys)}"
            return f"Result with {len(keys)} keys: {', '.join(keys[:5])}..."
        if isinstance(data, list):
            return f"List with {len(data)} items"
        return str(data)[:max_length]

    @classmethod
    def extract_files(cls, result: ToolResult) -> list[str]:
        """Hoist any file-like artefacts out of the result envelope.

        Recognises:

        - Common single-file keys (``file_path``, ``output_path``, ``path``,
          ``produced_file``).
        - List-valued keys emitted by the ``code_execution`` /
          ``tools/_data`` pipelines (``files``, ``produced_files``,
          ``artifacts``).
        - ``ArtifactRef``-shaped dicts with a ``uri`` key (rendered as
          their URI string).
        """
        files: list[str] = []
        if not result.success or not result.data:
            return files

        data = result.data
        if isinstance(data, dict):
            for key in cls._FILE_KEYS:
                value = data.get(key)
                if isinstance(value, str) and value:
                    files.append(value)

            for key in cls._FILE_LIST_KEYS:
                value = data.get(key)
                if not isinstance(value, list):
                    continue
                for item in value:
                    if isinstance(item, str) and item:
                        files.append(item)
                    elif isinstance(item, dict):
                        uri = item.get("uri") or item.get("path")
                        if isinstance(uri, str) and uri:
                            files.append(uri)

            # Top-level ArtifactRef shape: {"uri": "...", ...}
            if isinstance(data.get("artifact"), dict):
                uri = data["artifact"].get("uri")
                if isinstance(uri, str):
                    files.append(uri)

        # Deduplicate while preserving order.
        seen: set[str] = set()
        unique: list[str] = []
        for f in files:
            if f not in seen:
                seen.add(f)
                unique.append(f)
        return unique

    @staticmethod
    def serialize_for_llm(base: BaseToolResult | ToolResult) -> str:
        """Flatten a ToolResult envelope into the string the LLM consumes.

        Shared with :func:`leagent.agent.query._serialize_result` so the
        legacy ReAct path and the QueryEngine path agree on the exact
        wording sent back to the model.
        """
        success = bool(getattr(base, "success", True))
        data = getattr(base, "data", None)
        error = getattr(base, "error", None)
        if not success:
            if isinstance(data, dict) and data:
                payload = {
                    "tool_ok": False,
                    "error": error or "Unknown error",
                    "detail": data,
                }
                try:
                    s = json.dumps(payload, ensure_ascii=False, default=str)
                except TypeError:
                    s = f"Error: {error or 'Unknown error'}"
                if len(s) > _LLM_TOOL_STRING_CAP:
                    return (
                        s[: _LLM_TOOL_STRING_CAP - len(_TRUNCATION_NOTICE)]
                        + _TRUNCATION_NOTICE
                    )
                return s
            if error:
                msg = f"Error: {error}"
                if len(msg) > _LLM_TOOL_STRING_CAP:
                    return (
                        msg[: _LLM_TOOL_STRING_CAP - len(_TRUNCATION_NOTICE)]
                        + _TRUNCATION_NOTICE
                    )
                return msg
            return "Error: Unknown error"
        if isinstance(data, str):
            s = data
            if len(s) > _LLM_TOOL_STRING_CAP:
                return s[: _LLM_TOOL_STRING_CAP - len(_TRUNCATION_NOTICE)] + _TRUNCATION_NOTICE
            return s
        try:
            s = json.dumps(data, ensure_ascii=False, default=str)
        except TypeError:
            s = str(data)
        if len(s) > _LLM_TOOL_STRING_CAP:
            return s[: _LLM_TOOL_STRING_CAP - len(_TRUNCATION_NOTICE)] + _TRUNCATION_NOTICE
        return s

    @classmethod
    def to_tool_result_message(
        cls,
        base: BaseToolResult,
        *,
        tool_call_id: str,
        name: str,
    ) -> ToolResultMessage:
        """Build the :class:`ToolResultMessage` the query loop appends."""
        return ToolResultMessage(
            tool_call_id=tool_call_id,
            name=name,
            content=cls.serialize_for_llm(base),
            success=bool(getattr(base, "success", True)),
        )


# ---------------------------------------------------------------------------
# Error recovery
# ---------------------------------------------------------------------------


RecoveryHandler = Callable[
    [BaseToolResult, ToolCall, AgentContext | None],
    "BaseToolResult | None | Awaitable[BaseToolResult | None]",
]


class ErrorRecovery:
    """Retry recoverable tool failures with targeted strategies.

    Usage:
        recovery = ErrorRecovery(executor)
        recovery.register_handler("connection_reset", my_handler)

        result = await recovery.attempt_recovery(
            base_result, tool_call=call, context=agent_ctx,
        )

    Or as a middleware inside the QueryEngine's ``_dispatch_tools``:

        dispatcher = recovery.as_middleware()
        base = await dispatcher(call, ctx)

    Recoverable classes (in priority order):

    1. :class:`ToolTimeoutError` → re-run with doubled timeout (once).
    2. Rate limiting (``RATE_LIMIT`` code or ``rate limit`` substring)
       → bounded exponential backoff (1s, 2s, 5s; capped at 3 attempts)
       with ±0.5s jitter.
    3. :class:`ToolValidationError` → no retry, return ``None`` so the
       caller surfaces the validation error to the LLM.
    4. ``not found`` → no retry.
    5. User-registered handlers (string-match on the error text, legacy
       path).
    """

    _MAX_RATE_LIMIT_ATTEMPTS: int = 3
    _RATE_LIMIT_DELAYS: tuple[float, ...] = (1.0, 2.0, 5.0)

    def __init__(self, executor: "ToolExecutor") -> None:
        self.executor = executor
        self._recovery_handlers: dict[str, RecoveryHandler] = {}

    def register_handler(
        self,
        error_type: str,
        handler: RecoveryHandler,
    ) -> None:
        """Register a handler keyed by a substring match on the error."""
        self._recovery_handlers[error_type.lower()] = handler

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    async def attempt_recovery(
        self,
        result: BaseToolResult | ToolResult,
        *,
        tool_call: ToolCall,
        context: AgentContext | None = None,
        exception: BaseException | None = None,
    ) -> BaseToolResult | None:
        """Attempt to recover from a failed tool execution.

        Returns the recovered :class:`BaseToolResult` on success, or
        ``None`` if recovery is not possible (or not desired).
        """
        success = bool(getattr(result, "success", True))
        if success:
            # Nothing to recover; return the envelope unchanged for
            # middleware-style call sites that chain on the result.
            return result if isinstance(result, BaseToolResult) else None

        # --- Exception-type dispatch ---------------------------------
        if isinstance(exception, ToolTimeoutError) or self._is_timeout(result):
            return await self._handle_timeout(tool_call, context)

        if isinstance(exception, ToolValidationError):
            return None  # validation errors don't benefit from a retry

        if self._is_rate_limit(result, exception):
            return await self._handle_rate_limit(tool_call, context)

        error_str = (getattr(result, "error", None) or "").lower()

        if "not found" in error_str:
            return None

        # --- Registered handlers (legacy fallback) -------------------
        for pattern, handler in self._recovery_handlers.items():
            if pattern in error_str:
                try:
                    produced = handler(result, tool_call, context)
                    if asyncio.iscoroutine(produced):
                        produced = await produced
                    return produced  # type: ignore[return-value]
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "recovery_handler_failed",
                        error_type=pattern,
                        error=str(exc),
                    )
        return None

    def as_middleware(self) -> Callable[
        [ToolCall, AgentContext | None],
        Awaitable[BaseToolResult],
    ]:
        """Build an async callable that runs a tool with recovery.

        The returned coroutine calls ``executor.run_tool(...)``; on a
        non-success envelope it runs :meth:`attempt_recovery` and
        returns the recovered result when available, otherwise the
        original.
        """

        async def _middleware(
            call: ToolCall,
            context: AgentContext | None = None,
        ) -> BaseToolResult:
            try:
                # Forward the LLM's tool_call id so downstream streaming
                # (tool_output_delta) correlates with the chat tool row.
                base = await self.executor.run_tool(
                    call.name, call.arguments, context,
                    call_id=call.id or None,
                )
            except ToolExecutionError as exc:
                recovered = await self.attempt_recovery(
                    BaseToolResult(success=False, error=str(exc)),
                    tool_call=call,
                    context=context,
                    exception=exc,
                )
                if recovered is not None:
                    return recovered
                raise

            if not getattr(base, "success", True):
                recovered = await self.attempt_recovery(
                    base, tool_call=call, context=context,
                )
                if recovered is not None:
                    return recovered
            return base

        return _middleware

    # ------------------------------------------------------------------
    # Dispatch helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_timeout(result: Any) -> bool:
        err = str(getattr(result, "error", None) or "").lower()
        metadata = getattr(result, "metadata", None) or {}
        code = str(metadata.get("code", "")).lower() if isinstance(metadata, dict) else ""
        return "timeout" in err or "timed out" in err or code == "tool_timeout"

    @staticmethod
    def _is_rate_limit(result: Any, exception: BaseException | None) -> bool:
        if isinstance(exception, ToolExecutionError):
            code = getattr(exception, "error_code", "") or ""
            if "RATE_LIMIT" in code.upper():
                return True
        err = str(getattr(result, "error", None) or "").lower()
        return "rate limit" in err or "rate_limit" in err or "429" in err

    _SUBAGENT_TOOLS = frozenset({"coding_agent", "script_agent"})

    async def _handle_timeout(
        self,
        tool_call: ToolCall,
        context: AgentContext | None,
    ) -> BaseToolResult | None:
        """Re-run once with a doubled timeout budget.

        Subagent-class tools (coding_agent, script_agent) manage their own
        internal recovery and should not be restarted from scratch.
        """
        if tool_call.name in self._SUBAGENT_TOOLS:
            logger.info("recovery_timeout_skip_subagent", tool=tool_call.name)
            return None
        logger.info("recovery_timeout_retry", tool=tool_call.name)
        timeout = int(getattr(self.executor, "default_timeout", 60) * 2)
        try:
            return await self.executor.run_tool(
                tool_call.name,
                tool_call.arguments,
                context,
                timeout=timeout,
                retries=1,
            )
        except TypeError:
            # Older executors without the keyword args — best-effort retry.
            return await self.executor.run_tool(
                tool_call.name, tool_call.arguments, context,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("recovery_timeout_failed", error=str(exc))
            return None

    async def _handle_rate_limit(
        self,
        tool_call: ToolCall,
        context: AgentContext | None,
    ) -> BaseToolResult | None:
        """Bounded exponential backoff with jitter."""
        for attempt in range(self._MAX_RATE_LIMIT_ATTEMPTS):
            delay = self._RATE_LIMIT_DELAYS[
                min(attempt, len(self._RATE_LIMIT_DELAYS) - 1)
            ]
            jitter = random.uniform(0, 0.5)
            logger.info(
                "recovery_rate_limit_wait",
                tool=tool_call.name,
                attempt=attempt + 1,
                delay=delay + jitter,
            )
            await asyncio.sleep(delay + jitter)
            try:
                base = await self.executor.run_tool(
                    tool_call.name, tool_call.arguments, context,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "recovery_rate_limit_retry_failed",
                    tool=tool_call.name,
                    error=str(exc),
                )
                continue
            if getattr(base, "success", False):
                return base
            if not self._is_rate_limit(base, None):
                return base
        return None


__all__ = ["ResultProcessor", "ErrorRecovery", "RecoveryHandler"]
