"""Out-of-process Python sandbox for the professional code-execution tier.

The workflow :class:`~leagent.workflow.nodes.builtin.script.ScriptNode`
and the high-trust script sub-agent built by
:func:`~leagent.agent.script_agent.build_script_execution_agent`
have very different threat models:

* The script node runs small trusted helpers inline. It uses
  :mod:`leagent.tools._sandbox.inproc`.
* The code-execution agent runs open-ended, potentially LLM-generated
  Python. That requires process-level isolation (fresh subprocess,
  sanitized environment, scratch cwd), which is what this package
  provides.

Nothing in this module uses Docker or external binaries: the design is
intentionally pure-stdlib so it is runnable on developer laptops and
constrained deployments alike. Safety comes from process isolation, a
minimal allowlist-based environment, strict wall-clock timeouts (parent
``asyncio.wait_for`` + child ``SIGALRM``), and session-scoped scratch
directories — not from kernel namespacing or ``resource``/rlimits.

.. note::

   The ``memory_bytes`` parameter on :class:`CodeExecutionTool` is
   accepted by the API schema but is **not currently enforced** in the
   subprocess. It is reserved for future rlimit-based enforcement.

Public surface:

* :class:`SubprocessSandbox` — the core runner with ``execute(...)``.
* :class:`SandboxResult`     — structured stdout/stderr/result envelope.
* :class:`Workspace`         — quota-managed scratch directory used as
  ``cwd`` for each invocation.
* :class:`WorkspaceManager`  — factory/cleaner for per-session workspaces.
"""

from __future__ import annotations

from .subprocess_sandbox import (
    SandboxResult,
    SandboxTimeoutError,
    SubprocessSandbox,
)
from .workspace import Workspace, WorkspaceManager

__all__ = [
    "SandboxResult",
    "SandboxTimeoutError",
    "SubprocessSandbox",
    "Workspace",
    "WorkspaceManager",
]
