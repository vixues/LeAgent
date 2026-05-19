"""Agent-layer re-exports.

Historically ``leagent.agent.executor`` housed a bespoke tool
dispatcher. It has since been collapsed into the single
:class:`leagent.tools.executor.ToolExecutor` used by every entrypoint
(agents, subagents, plan-execute loops, workflow nodes). This module
survives purely as a stable import surface so downstream code keeps
working.

What lives here now:

* The unified tool-layer dispatcher
  (:class:`ToolExecutor`, :class:`ExecutionResult`,
  :class:`AggregatedResult`, :class:`ExecutorToolCall`,
  :func:`get_executor`).
* The agent-side result / recovery helpers
  (:class:`ResultProcessor`, :class:`ErrorRecovery`).
* The canonical :class:`ToolUseContext` and the new
  :class:`QueryEngine` / :func:`query` entry points.
* The sub-agent fork surface (:func:`fork_subagent`,
  :class:`AgentTool`).
* Tool-layer error types (:class:`ToolExecutionError`,
  :class:`ToolTimeoutError`, :class:`ToolValidationError`).

.. note::
    Prefer importing from the canonical modules in new code:
    ``leagent.tools.executor`` for dispatching,
    ``leagent.agent.query_engine`` for the turn loop,
    ``leagent.agent.subagent`` for sub-agent forking,
    ``leagent.agent.recovery`` for result / error helpers.
    The aliases in this module are kept only to avoid breaking
    existing ``from leagent.agent.executor import X`` lines.
"""

from __future__ import annotations

from leagent.agent.query import QueryParams, query
from leagent.agent.query_engine import QueryEngine, QueryEngineConfig, SDKMessage
from leagent.agent.recovery import ErrorRecovery, RecoveryHandler, ResultProcessor
from leagent.agent.subagent import AgentTool, fork_subagent
from leagent.agent.tool_use_context import ToolUseContext
from leagent.agent.transitions import (
    Continue,
    ContinueReason,
    Terminal,
    TerminalReason,
)
from leagent.exceptions.tool import (
    ToolExecutionError,
    ToolTimeoutError,
    ToolValidationError,
)
from leagent.tools.executor import (
    AggregatedResult,
    ExecutionResult,
    ToolCall as ExecutorToolCall,
    ToolExecutor,
    get_executor,
)

__all__ = [
    # Dispatch
    "ToolExecutor",
    "ExecutionResult",
    "AggregatedResult",
    "ExecutorToolCall",
    "get_executor",
    # Recovery / normalisation
    "ResultProcessor",
    "ErrorRecovery",
    "RecoveryHandler",
    # Query loop surface
    "QueryEngine",
    "QueryEngineConfig",
    "SDKMessage",
    "QueryParams",
    "query",
    "ToolUseContext",
    "Terminal",
    "TerminalReason",
    "Continue",
    "ContinueReason",
    # Sub-agent delegation
    "fork_subagent",
    "AgentTool",
    # Errors
    "ToolExecutionError",
    "ToolTimeoutError",
    "ToolValidationError",
]
