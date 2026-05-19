"""Primitives for executing Python code in-process and resolving tool paths.

Two execution tiers exist:

* :mod:`leagent.tools._sandbox.inproc` — an **in-process** executor for
  short helper scripts run inside the workflow process (used by
  :class:`ScriptNode`). Timeout-guarded but otherwise unrestricted.

* :mod:`leagent.services.code_execution` (wired via
  :mod:`leagent.tools.code.execution`) — an **out-of-process**
  subprocess executor. Used by the ``CodeExecutionAgent`` for
  open-ended code execution.

Only :mod:`inproc` lives in this package because it must be importable
by the workflow engine without pulling in service-layer dependencies.
"""

from __future__ import annotations

from .inproc import (
    ScriptExecutionError,
    ScriptResult,
    ScriptTimeoutError,
    execute_script,
)
from .paths import PathSandbox, reset_roots

__all__ = [
    "PathSandbox",
    "ScriptExecutionError",
    "ScriptResult",
    "ScriptTimeoutError",
    "execute_script",
    "reset_roots",
]
