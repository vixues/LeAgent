"""Base agent classes: state management, configuration, and execution context."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable
from uuid import UUID, uuid4

import structlog
from pydantic import BaseModel, Field

from leagent.agent.transitions import TerminalReason

if TYPE_CHECKING:
    from leagent.llm import LLMService
    from leagent.memory import AgentMemory
    from leagent.tools import ToolRegistry

logger = structlog.get_logger(__name__)


class AgentState(StrEnum):
    """Current operational state of the agent.

    State transitions:
        IDLE -> THINKING -> EXECUTING -> IDLE (on completion)
                        |-> WAITING (for human/external input)
                        |-> ERROR (on failure)
    """

    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    WAITING = "waiting"
    ERROR = "error"


class AgentMode(StrEnum):
    """Agent execution mode determining planning behavior."""

    REACT = "react"
    PLAN_EXECUTE = "plan_execute"
    HYBRID = "hybrid"


class StepType(StrEnum):
    """Type of execution step."""

    THOUGHT = "thought"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    OBSERVATION = "observation"
    ANSWER = "answer"
    ERROR = "error"
    REPLAN = "replan"


class ToolCall(BaseModel):
    """Represents a single tool invocation request."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)

    def __repr__(self) -> str:
        return f"ToolCall(id={self.id[:8]}, name={self.name})"


class ToolResult(BaseModel):
    """Result of a tool execution."""

    tool_call_id: str
    name: str
    success: bool = True
    data: Any = None
    error: str | None = None
    duration_ms: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def content(self) -> str:
        """Serialize result for LLM consumption."""
        if not self.success:
            return f"Error: {self.error or 'Unknown error'}"
        if self.data is None:
            return ""
        if isinstance(self.data, str):
            return self.data
        if isinstance(self.data, dict):
            import json

            return json.dumps(self.data, ensure_ascii=False, indent=2, default=str)
        return str(self.data)

    @classmethod
    def from_base(
        cls,
        base: Any,
        *,
        tool_call_id: str,
        name: str,
    ) -> ToolResult:
        """Build an agent-layer :class:`ToolResult` from a tools-layer envelope.

        ``base`` is expected to be a :class:`leagent.tools.base.ToolResult`
        dataclass; a loose ``Any`` type keeps this file free of import cycles.
        Commonly-used artefact keys (``file_path``, ``row_count`` …) are
        hoisted from ``data`` into ``metadata`` so downstream consumers can
        rely on them without re-parsing.
        """
        data = getattr(base, "data", None)
        metadata = dict(getattr(base, "metadata", None) or {})
        if isinstance(data, dict):
            for key in (
                "file_path",
                "path",
                "output_path",
                "row_count",
                "page_count",
                "artifact",
            ):
                if key in data and key not in metadata:
                    metadata[key] = data[key]
            if "file_path" not in metadata:
                for k in ("file_path", "path", "output_path"):
                    v = data.get(k)
                    if v:
                        metadata["file_path"] = str(v)
                        break
        return cls(
            tool_call_id=tool_call_id,
            name=name,
            success=bool(getattr(base, "success", False)),
            data=data,
            error=getattr(base, "error", None),
            duration_ms=int(getattr(base, "duration_ms", 0) or 0),
            metadata=metadata,
        )


class ExecutionStep(BaseModel):
    """A single step in the agent's reasoning/execution trace."""

    id: UUID = Field(default_factory=uuid4)
    type: StepType
    content: str = ""
    tool_call: ToolCall | None = None
    tool_result: ToolResult | None = None
    thought: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    duration_ms: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    """Complete response from an agent run."""

    session_id: UUID
    task_id: UUID = Field(default_factory=uuid4)
    text: str = ""
    steps: list[ExecutionStep] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    partial: bool = False
    error: str | None = None
    total_duration_ms: int = 0
    token_usage: dict[str, int] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    terminal_reason: str = "completed"
    checkpoint_id: str | None = None

    @property
    def success(self) -> bool:
        return not self.partial and self.error is None

    @property
    def tool_calls_count(self) -> int:
        return sum(1 for s in self.steps if s.type == StepType.TOOL_CALL)

    def apply_usage(self, usage: dict[str, Any] | None) -> None:
        """Merge provider token counters onto this response."""
        if not usage:
            return
        with contextlib.suppress(Exception):
            tu = {
                "prompt_tokens": int(usage.get("prompt_tokens", 0) or 0),
                "completion_tokens": int(usage.get("completion_tokens", 0) or 0),
                "total_tokens": int(usage.get("total_tokens", 0) or 0),
                "reasoning_tokens": int(usage.get("reasoning_tokens", 0) or 0),
            }
            for cache_key in ("prompt_cache_hit_tokens", "prompt_cache_miss_tokens"):
                if cache_key in usage:
                    tu[cache_key] = int(usage.get(cache_key, 0) or 0)
            self.token_usage = tu

    def to_stream_events(self) -> list[StreamEvent]:
        """Wire events emitted when a turn finishes (SSE / ``run_stream``)."""
        events: list[StreamEvent] = []
        if self.error:
            events.append(
                StreamEvent(
                    type="error",
                    data={
                        "error": self.error,
                        "terminal_reason": self.terminal_reason,
                    },
                )
            )
        events.append(
            StreamEvent(
                type="complete",
                data={
                    "text": self.text,
                    "files": self.files,
                    "success": self.success,
                    "partial": self.partial,
                    "metadata": dict(self.metadata or {}),
                    "token_usage": dict(self.token_usage) if self.token_usage else None,
                    "terminal_reason": self.terminal_reason,
                    "checkpoint_id": self.checkpoint_id,
                },
            )
        )
        return events


class StreamEvent(BaseModel):
    """Event emitted during streaming agent execution."""

    type: str
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


@runtime_checkable
class StreamHandler(Protocol):
    """Protocol for handling streaming events during agent execution."""

    async def on_thinking(self, thought: str) -> None:
        """Called when agent produces a thought."""
        ...

    async def on_tool_call(self, tool_call: ToolCall) -> None:
        """Called when agent requests a tool invocation."""
        ...

    async def on_tool_call_delta(self, payload: dict[str, Any]) -> None:
        """Streaming JSON fragment while the model builds tool arguments (UI only)."""
        ...

    async def on_nested_agent_preview(self, payload: dict[str, Any]) -> None:
        """Sub-agent (e.g. coding_agent child) tool-call delta for workspace live preview."""
        ...

    async def on_tool_result(self, result: ToolResult) -> None:
        """Called when a tool returns a result."""
        ...

    async def on_user_input_request(self, payload: dict[str, Any]) -> None:
        """Emitted when the query loop pauses for ask_user (UI collects answers)."""
        ...

    async def on_token(self, token: str) -> None:
        """Called for each token during streaming generation."""
        ...

    async def on_complete(self, response: AgentResponse) -> None:
        """Called when agent completes execution."""
        ...

    async def on_error(self, error: Exception) -> None:
        """Called when an unexpected error occurs outside the query loop."""
        ...


class NoOpStreamHandler:
    """Default no-op stream handler."""

    async def on_thinking(self, thought: str) -> None:
        pass

    async def on_tool_call(self, tool_call: ToolCall) -> None:
        pass

    async def on_tool_call_delta(self, payload: dict[str, Any]) -> None:
        pass

    async def on_nested_agent_preview(self, payload: dict[str, Any]) -> None:
        pass

    async def on_tool_result(self, result: ToolResult) -> None:
        pass

    async def on_user_input_request(self, payload: dict[str, Any]) -> None:
        pass

    async def on_token(self, token: str) -> None:
        pass

    async def on_complete(self, response: AgentResponse) -> None:
        pass

    async def on_error(self, error: Exception) -> None:
        pass


class QueuedStreamHandler:
    """StreamHandler that enqueues :class:`StreamEvent` s for :meth:`AgentController.run_stream`.

    Turn termination always flows through :meth:`on_complete`; the handler
    delegates wire-format derivation to :meth:`AgentResponse.to_stream_events`.
    """

    def __init__(
        self,
        *,
        session_id: UUID,
        put_event: Callable[[StreamEvent | None], Awaitable[None]],
    ) -> None:
        self._session_id = session_id
        self._put_event = put_event

    async def on_thinking(self, thought: str) -> None:
        await self._put_event(StreamEvent(type="thinking", data={"thought": thought}))

    async def on_tool_call(self, tool_call: ToolCall) -> None:
        await self._put_event(
            StreamEvent(
                type="tool_call",
                data={
                    "id": tool_call.id,
                    "name": tool_call.name,
                    "arguments": tool_call.arguments,
                },
            )
        )

    async def on_tool_call_delta(self, payload: dict[str, Any]) -> None:
        await self._put_event(StreamEvent(type="tool_call_delta", data=dict(payload)))

    async def on_nested_agent_preview(self, payload: dict[str, Any]) -> None:
        await self._put_event(StreamEvent(type="nested_agent_preview", data=dict(payload)))

    async def on_tool_result(self, result: ToolResult) -> None:
        await self._put_event(
            StreamEvent(
                type="tool_result",
                data={
                    "tool_call_id": result.tool_call_id,
                    "name": result.name,
                    "success": result.success,
                    "content": result.content[:1000],
                    "data": result.data if isinstance(result.data, (dict, list)) else None,
                    "error": result.error,
                    "duration_ms": result.duration_ms,
                    "metadata": result.metadata,
                },
            )
        )

    async def on_workspace_attachments(self, items: list[dict[str, Any]]) -> None:
        if not items:
            return
        await self._put_event(
            StreamEvent(
                type="workspace_attachments",
                data={
                    "session_id": str(self._session_id),
                    "attachments": items,
                },
            )
        )

    async def on_token(self, token: str) -> None:
        await self._put_event(StreamEvent(type="token", data={"token": token}))

    async def on_user_input_request(self, payload: dict[str, Any]) -> None:
        await self._put_event(StreamEvent(type="user_input_request", data=payload))

    async def on_complete(self, response: AgentResponse) -> None:
        for event in response.to_stream_events():
            await self._put_event(event)
        await self._put_event(None)

    async def on_error(self, error: Exception) -> None:
        await self._put_event(
            StreamEvent(
                type="error",
                data={"error": str(error), "terminal_reason": "error"},
            )
        )
        await self._put_event(None)


@dataclass
class AgentConfig:
    """Configuration for agent behavior.

    Attributes:
        max_iterations: Maximum number of think-act cycles before giving up.
        max_tool_calls_per_turn: Limit parallel tool calls in a single turn.
        default_timeout_sec: Global timeout for the entire agent run.
        mode: Execution mode (ReAct, Plan-Execute, or Hybrid).
        enable_planning: Whether to create explicit plans for complex tasks.
        plan_threshold: Complexity threshold that triggers planning.
        enable_memory: Whether to use memory for context retrieval.
        enable_streaming: Whether to stream responses token-by-token.
        temperature: LLM sampling temperature.
        verbose: Enable verbose logging of internal state.
    """

    max_iterations: int = 15
    max_tool_calls_per_turn: int = 10
    default_timeout_sec: int = 300
    mode: AgentMode = AgentMode.HYBRID
    enable_planning: bool = True
    plan_threshold: int = 3
    enable_memory: bool = True
    enable_streaming: bool = True
    temperature: float = 0.1
    model_provider: str | None = None
    model_name: str | None = None
    verbose: bool = False
    agent_name: str = "default"
    prompt_variant: str = "default_agent"
    extra_system_prompt: str = ""
    # Deprecated compatibility flag. ``AgentController`` now always routes
    # requests through ``QueryEngine``; setting this False only emits a warning.
    use_query_engine: bool = True


@dataclass
class AgentContext:
    """Execution context providing access to services and state.

    This is the central context object passed throughout the agent
    execution lifecycle, providing access to:
    - Memory system (short-term, working, long-term)
    - Tool registry and execution
    - LLM service
    - Session and task state
    """

    task_id: UUID = field(default_factory=uuid4)
    session_id: UUID = field(default_factory=uuid4)
    user_id: UUID | None = None

    agent_memory: AgentMemory | None = None
    tools: ToolRegistry | None = None
    llm: LLMService | None = None

    config: AgentConfig = field(default_factory=AgentConfig)
    state: AgentState = AgentState.IDLE

    steps: list[ExecutionStep] = field(default_factory=list)
    output_files: list[str] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)

    current_plan: ExecutionPlan | None = None
    conversation: ConversationContext | None = None
    iteration: int = 0
    start_time: datetime | None = None

    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _cancelled: bool = False

    def __post_init__(self) -> None:
        self._lock = asyncio.Lock()

    async def transition_to(self, new_state: AgentState) -> None:
        """Thread-safe state transition with logging."""
        async with self._lock:
            old_state = self.state
            self.state = new_state
            logger.debug(
                "agent_state_transition",
                task_id=str(self.task_id),
                old_state=old_state.value,
                new_state=new_state.value,
            )

    def record_step(self, step: ExecutionStep) -> None:
        """Record an execution step."""
        self.steps.append(step)
        logger.debug(
            "agent_step_recorded",
            task_id=str(self.task_id),
            step_type=step.type.value,
            step_id=str(step.id),
        )

    def add_output_file(self, file_path: str) -> None:
        """Register a file produced during execution."""
        if file_path not in self.output_files:
            self.output_files.append(file_path)

    def get_variable(self, key: str, default: Any = None) -> Any:
        """Retrieve a context variable."""
        return self.variables.get(key, default)

    def set_variable(self, key: str, value: Any) -> None:
        """Set a context variable."""
        self.variables[key] = value

    def cancel(self) -> None:
        """Request cancellation of the current execution."""
        self._cancelled = True
        logger.info("agent_cancellation_requested", task_id=str(self.task_id))

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    @property
    def elapsed_ms(self) -> int:
        """Milliseconds elapsed since start."""
        if self.start_time is None:
            return 0
        return int((datetime.utcnow() - self.start_time).total_seconds() * 1000)

    def to_response(self, text: str = "", error: str | None = None) -> AgentResponse:
        """Build an AgentResponse from current context state."""
        return AgentResponse(
            session_id=self.session_id,
            task_id=self.task_id,
            text=text,
            steps=self.steps.copy(),
            files=self.output_files.copy(),
            partial=self.iteration >= self.config.max_iterations,
            error=error,
            total_duration_ms=self.elapsed_ms,
            metadata={"iteration": self.iteration},
        )

    def finalize_turn(
        self,
        *,
        text: str,
        reason: str,
        conversation: ConversationContext,
        turn_message_start: int,
        error: Any | None = None,
        usage: dict[str, Any] | None = None,
        checkpoint_id: str | None = None,
        partial: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> AgentResponse:
        """Build the canonical turn outcome after a kernel ``result`` frame."""
        self.record_step(ExecutionStep(type=StepType.ANSWER, content=text))
        response = self.to_response(text=text)
        response.terminal_reason = reason
        response.checkpoint_id = checkpoint_id
        response.partial = partial

        if metadata is not None:
            response.metadata = metadata
        else:
            err_text = str(error).strip() if error is not None else ""
            if err_text and reason != TerminalReason.COMPLETED.value:
                response.error = err_text
            response.metadata = conversation.turn_metadata(turn_message_start)

        response.apply_usage(usage)
        return response


class PlanStep(BaseModel):
    """A single step in an execution plan."""

    id: int
    description: str
    tool: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[int] = Field(default_factory=list)
    status: str = "pending"
    result: Any = None
    error: str | None = None


class ExecutionPlan(BaseModel):
    """Structured execution plan for complex tasks."""

    id: UUID = Field(default_factory=uuid4)
    goal: str
    steps: list[PlanStep] = Field(default_factory=list)
    expected_output: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_steps: list[int] = Field(default_factory=list)

    @property
    def current_step(self) -> PlanStep | None:
        """Get the next pending step."""
        for step in self.steps:
            if step.status == "pending":
                deps_met = all(d in self.completed_steps for d in step.depends_on)
                if deps_met:
                    return step
        return None

    @property
    def is_complete(self) -> bool:
        return all(s.status in ("completed", "skipped") for s in self.steps)

    @property
    def progress(self) -> float:
        if not self.steps:
            return 1.0
        done = sum(1 for s in self.steps if s.status in ("completed", "skipped"))
        return done / len(self.steps)

    def mark_step_completed(self, step_id: int, result: Any = None) -> None:
        """Mark a step as completed."""
        for step in self.steps:
            if step.id == step_id:
                step.status = "completed"
                step.result = result
                self.completed_steps.append(step_id)
                break

    def mark_step_failed(self, step_id: int, error: str) -> None:
        """Mark a step as failed."""
        for step in self.steps:
            if step.id == step_id:
                step.status = "failed"
                step.error = error
                break

    def get_step(self, step_id: int) -> PlanStep | None:
        """Get a step by ID."""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def get_ready_steps(self) -> list[PlanStep]:
        """Get all steps whose dependencies are met."""
        ready = []
        for step in self.steps:
            if step.status != "pending":
                continue
            if all(d in self.completed_steps for d in step.depends_on):
                ready.append(step)
        return ready


class ConversationMessage(BaseModel):
    """A message in the conversation context."""

    role: str
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    reasoning_content: str | None = None

    def to_openai_format(self) -> dict[str, Any]:
        """Convert to OpenAI API message format."""
        msg: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            msg["name"] = self.name
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        if self.reasoning_content:
            msg["reasoning_content"] = self.reasoning_content
        return msg


class ConversationContext(BaseModel):
    """Manages conversation history with windowing and serialization."""

    session_id: UUID = Field(default_factory=uuid4)
    messages: list[ConversationMessage] = Field(default_factory=list)
    system_prompt: str = ""
    max_turns: int = 20
    max_tokens: int = 16000

    def append_user_message(self, content: str) -> None:
        self.messages.append(ConversationMessage(role="user", content=content))

    def append_assistant_message(
        self,
        content: str,
        tool_calls: list[dict[str, Any]] | None = None,
        *,
        reasoning_content: str | None = None,
    ) -> None:
        self.messages.append(
            ConversationMessage(
                role="assistant",
                content=content,
                tool_calls=tool_calls,
                reasoning_content=reasoning_content,
            )
        )

    def append_tool_result(self, tool_call_id: str, name: str, content: str) -> None:
        self.messages.append(
            ConversationMessage(
                role="tool",
                content=content,
                name=name,
                tool_call_id=tool_call_id,
            )
        )

    def turn_metadata(self, since_index: int) -> dict[str, Any]:
        """Assistant tool-call and reasoning metadata for the current turn."""
        merged_tc_by_id: dict[str, dict[str, Any]] = {}
        last_reasoning: str | None = None
        for msg in self.messages[since_index:]:
            if msg.role != "assistant":
                continue
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    if isinstance(tc, dict):
                        tid = str(tc.get("id") or "").strip()
                        if tid:
                            merged_tc_by_id[tid] = tc
            if isinstance(msg.reasoning_content, str) and msg.reasoning_content.strip():
                last_reasoning = msg.reasoning_content.strip()
        meta: dict[str, Any] = {}
        if merged_tc_by_id:
            meta["assistant_tool_calls"] = list(merged_tc_by_id.values())
        if last_reasoning:
            meta["reasoning_content"] = last_reasoning
        return meta

    def to_messages(self, include_system: bool = True) -> list[dict[str, Any]]:
        """Convert to list of OpenAI-format messages."""
        result: list[dict[str, Any]] = []
        if include_system and self.system_prompt:
            result.append({"role": "system", "content": self.system_prompt})
        for msg in self.messages:
            result.append(msg.to_openai_format())
        return result

    def trim(self, max_turns: int | None = None, max_tokens: int | None = None) -> None:
        """Trim conversation to fit within limits while preserving structure."""
        max_turns = max_turns or self.max_turns
        max_tokens = max_tokens or self.max_tokens

        if len(self.messages) <= max_turns * 2:
            return

        pairs_to_keep = max_turns
        kept: list[ConversationMessage] = []
        i = len(self.messages) - 1
        count = 0

        while i >= 0 and count < pairs_to_keep * 2:
            kept.insert(0, self.messages[i])
            i -= 1
            count += 1

        self.messages = kept

    @property
    def token_estimate(self) -> int:
        """Rough token count estimate."""
        total = len(self.system_prompt) // 3
        for msg in self.messages:
            total += len(msg.content) // 3
        return total

    def serialize(self) -> str:
        """Serialize to JSON string for caching."""
        return self.model_dump_json()

    @classmethod
    def deserialize(cls, data: str) -> ConversationContext:
        """Deserialize from JSON string."""
        return cls.model_validate_json(data)
