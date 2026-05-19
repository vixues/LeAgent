"""In-process Python sandbox for workflow ScriptNode.

Executes short Python snippets inside the host process. The timeout
mechanism (wall-clock via asyncio + thread) is retained as a liveness
bound. All import restrictions and RestrictedPython compilation have
been removed — standard ``compile()`` and ``__import__`` are used.
"""

from __future__ import annotations

import asyncio
import builtins
import io
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Iterable


class ScriptExecutionError(RuntimeError):
    """Raised when a script fails to compile or raises at runtime."""


class ScriptTimeoutError(ScriptExecutionError):
    """Raised when a script exceeds its allotted wall-clock budget."""


_DEFAULT_STDOUT_LIMIT = 64 * 1024  # 64 KB
_DEFAULT_TIMEOUT_SEC = 5.0


@dataclass
class ScriptResult:
    """Structured result returned by :func:`execute_script`."""

    stdout: str = ""
    result: Any = None
    locals: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    truncated_stdout: bool = False


def _build_globals(
    inputs: dict[str, Any] | None,
    stdout_buffer: io.StringIO,
) -> dict[str, Any]:
    captured_print_lines = stdout_buffer

    def _captured_print(*args: Any, sep: str = " ", end: str = "\n", **_kw: Any) -> None:
        captured_print_lines.write(sep.join(str(a) for a in args) + end)

    env: dict[str, Any] = {"__builtins__": builtins.__dict__.copy()}
    env["__builtins__"]["print"] = _captured_print

    if inputs:
        reserved = {"__builtins__"}
        for key, value in inputs.items():
            if key in reserved:
                raise ScriptExecutionError(
                    f"Input name '{key}' is reserved or invalid for the script sandbox"
                )
            env[key] = value
    return env


def _compile_script(source: str) -> Any:
    try:
        return compile(source, "<script>", "exec")
    except SyntaxError as exc:
        raise ScriptExecutionError(f"Script compile error: {exc}") from exc


def _safe_set_result(fut: asyncio.Future[Any], value: Any) -> None:
    if not fut.done():
        fut.set_result(value)


def _safe_set_exception(fut: asyncio.Future[Any], exc: BaseException) -> None:
    if not fut.done():
        fut.set_exception(exc)


def _run_sync(
    source: str,
    env: dict[str, Any],
    buffer: io.StringIO,
    *,
    stdout_limit: int,
) -> tuple[str, Any, dict[str, Any], bool]:
    code = _compile_script(source)
    local_ns: dict[str, Any] = {}
    exec(code, env, local_ns)  # noqa: S102
    stdout_text = buffer.getvalue()
    truncated = False
    if len(stdout_text) > stdout_limit:
        stdout_text = stdout_text[:stdout_limit]
        truncated = True
    result = local_ns.get("result")
    return stdout_text, result, local_ns, truncated


async def execute_script(
    source: str,
    *,
    inputs: dict[str, Any] | None = None,
    timeout_sec: float = _DEFAULT_TIMEOUT_SEC,
    allow_modules: Iterable[str] = (),
    stdout_limit: int = _DEFAULT_STDOUT_LIMIT,
) -> ScriptResult:
    """Compile and run ``source`` inside the in-process sandbox.

    All imports are allowed. The ``allow_modules`` parameter is accepted
    for API compatibility but has no effect.

    Setting a top-level variable named ``result`` selects the returned
    payload; otherwise :attr:`ScriptResult.result` is ``None``.

    Raises :class:`ScriptTimeoutError` when wall-clock exceeds
    ``timeout_sec``, and :class:`ScriptExecutionError` for compile/runtime
    errors.
    """
    if not isinstance(source, str) or not source.strip():
        raise ScriptExecutionError("Script source must be a non-empty string")

    stdout_buffer = io.StringIO()
    env = _build_globals(inputs, stdout_buffer)
    started_at = time.monotonic()
    loop = asyncio.get_running_loop()
    future: asyncio.Future[tuple[str, Any, dict[str, Any], bool]] = loop.create_future()

    def _runner() -> None:
        try:
            out = _run_sync(source, env, stdout_buffer, stdout_limit=stdout_limit)
        except ScriptExecutionError as exc:
            loop.call_soon_threadsafe(_safe_set_exception, future, exc)
        except Exception as exc:  # noqa: BLE001
            loop.call_soon_threadsafe(
                _safe_set_exception, future,
                ScriptExecutionError(f"Script runtime error: {exc}"),
            )
        else:
            loop.call_soon_threadsafe(_safe_set_result, future, out)

    thread = threading.Thread(
        target=_runner,
        name="leagent-script-sandbox",
        daemon=True,
    )
    thread.start()

    try:
        stdout, result, locals_ns, truncated = await asyncio.wait_for(
            future, timeout=timeout_sec,
        )
    except asyncio.TimeoutError as exc:
        raise ScriptTimeoutError(
            f"Script exceeded {timeout_sec:g}s wall-clock budget"
        ) from exc
    except ScriptExecutionError:
        raise

    duration_ms = int((time.monotonic() - started_at) * 1000)
    cleaned_locals = {
        k: v
        for k, v in locals_ns.items()
        if not k.startswith("_") and k != "__builtins__"
    }
    return ScriptResult(
        stdout=stdout,
        result=result,
        locals=cleaned_locals,
        duration_ms=duration_ms,
        truncated_stdout=truncated,
    )
