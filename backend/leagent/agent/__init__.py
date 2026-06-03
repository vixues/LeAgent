"""Agent core package.

This module provides the core agent functionality for LeAgent:

* Base types for state, configuration, and execution context.
* :class:`AgentController` — the orchestration front door (workflow
  matching, hooks, permissions) that delegates to :class:`QueryEngine`
  by default.
* :class:`QueryEngine` — the session-scoped owner of the agentic turn
  loop (ported from the reference ``QueryEngine.ts``).
* :class:`TaskPlanner` — plan decomposition for the Plan-Execute path.
* :class:`ToolExecutor` — unified tool dispatcher (re-exported from the
  tools layer).
* :class:`ResultProcessor` / :class:`ErrorRecovery` — tool-result
  normalisation and retry middleware.
* :func:`fork_subagent` / :class:`AgentTool` — sub-agent delegation
  built on :meth:`QueryEngine.fork`.
* Lifecycle hooks and the ``ScriptAgentTool`` factory.

Example:
    from leagent.agent import AgentController, AgentConfig, TaskPlanner
    from leagent.agent import QueryEngine, fork_subagent
"""

from leagent.agent.base import (
    AgentConfig,
    AgentContext,
    AgentMode,
    AgentResponse,
    AgentState,
    ConversationContext,
    ConversationMessage,
    ExecutionPlan,
    ExecutionStep,
    NoOpStreamHandler,
    PlanStep,
    StepType,
    StreamEvent,
    StreamHandler,
    ToolCall,
    ToolResult,
)
from leagent.agent.controller import AgentController
from leagent.agent.executor import (
    ErrorRecovery,
    RecoveryHandler,
    ResultProcessor,
    ToolExecutor,
)
from leagent.agent.hooks import (
    AgentHook,
    HookManager,
    LoggingHook,
    MetricsHook,
    RateLimitError,
    RateLimitHook,
    TaskHistoryHook,
    create_default_hooks,
)
from leagent.agent.planner import (
    TaskPlanner,
    build_dependency_graph,
    get_parallel_groups,
    schedule_ready,
    topological_sort,
)
from leagent.agent.query_engine import QueryEngine, QueryEngineConfig, SDKMessage
from leagent.agent.subagent import AgentTool, fork_subagent
from leagent.agent.tool_use_context import ToolUseContext
from leagent.agent.transitions import (
    Continue,
    ContinueReason,
    Terminal,
    TerminalReason,
)

__all__ = [
    # Base types
    "AgentState",
    "AgentMode",
    "StepType",
    "ToolCall",
    "ToolResult",
    "ExecutionStep",
    "AgentResponse",
    "StreamEvent",
    "StreamHandler",
    "NoOpStreamHandler",
    "AgentConfig",
    "AgentContext",
    "PlanStep",
    "ExecutionPlan",
    "ConversationMessage",
    "ConversationContext",
    # Controller
    "AgentController",
    # QueryEngine
    "QueryEngine",
    "QueryEngineConfig",
    "SDKMessage",
    "ToolUseContext",
    "Terminal",
    "TerminalReason",
    "Continue",
    "ContinueReason",
    # Planner
    "TaskPlanner",
    "build_dependency_graph",
    "topological_sort",
    "get_parallel_groups",
    "schedule_ready",
    # Executor / recovery
    "ToolExecutor",
    "ResultProcessor",
    "ErrorRecovery",
    "RecoveryHandler",
    # Sub-agents
    "fork_subagent",
    "AgentTool",
    # Hooks
    "AgentHook",
    "HookManager",
    "LoggingHook",
    "MetricsHook",
    "TaskHistoryHook",
    "RateLimitHook",
    "RateLimitError",
    "create_default_hooks",
]
