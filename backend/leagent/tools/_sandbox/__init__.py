"""In-process script execution primitives.

:mod:`leagent.tools._sandbox.inproc` provides an **in-process** executor
for short helper scripts run inside the workflow process (used by
:class:`ScriptNode`). Timeout-guarded but otherwise unrestricted.

Path sandbox functionality has moved to :mod:`leagent.file.sandbox`.
"""

from __future__ import annotations

from .inproc import (
    ScriptExecutionError,
    ScriptResult,
    ScriptTimeoutError,
    execute_script,
)

__all__ = [
    "ScriptExecutionError",
    "ScriptResult",
    "ScriptTimeoutError",
    "execute_script",
]
