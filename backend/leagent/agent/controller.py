"""AgentController: Main orchestration logic with ReAct and Plan-Execute hybrid modes.

Upgraded to align with the reference architecture patterns:
- Abort signal propagation via ToolContext.abort_signal
- Permission checks before every tool dispatch
- Concurrency-safe partitioning (parallel for safe tools, sequential for serial)
- Tool result budget enforcement via BaseTool.max_result_size_chars
- Pre-LLM context compaction with hook support
- Enabled-tool filtering before schema generation
"""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import suppress
import json
from collections import OrderedDict
from dataclasses import dataclass
from collections.abc import AsyncIterator  # noqa: TC003
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4  # noqa: TC003

import structlog

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
from leagent.agent.query import (
    ASK_USER_PENDING_TOOL_JSON,
    ASK_USER_TOOL_NAME,
    _inject_pending_ask_user_tool_stubs,
    inject_missing_tool_result_stubs,
)
from leagent.agent.transitions import TerminalReason
from leagent.exceptions.base import LeAgentError
from leagent.exceptions.llm import LLMServiceError
from leagent.prompts import PromptContext, get_prompt_builder
from leagent.services.session.artifacts import (
    ArtifactRegistrar,
    attachment_dicts,
    coerce_tool_result_data,
    extract_produced_path_candidates,
)
from leagent.tools.base import ToolPermissionContext, check_tool_permission
from leagent.tools.context import build_tool_context
from leagent.tools.executor import parse_tool_arguments_str, strict_json_loads_error
from leagent.tools.session_attachment_context import build_tool_extra_for_attachment_paths

if TYPE_CHECKING:
    from leagent.agent.hooks import HookManager
    from leagent.agent.planner import TaskPlanner
    from leagent.llm import LLMService
    from leagent.memory import AgentMemory
    from leagent.services.session import SessionManager
    from leagent.tools import ToolRegistry
    from leagent.tools.executor import ToolExecutor
    from leagent.workflow import WorkflowExecutor as WorkflowEngine

logger = structlog.get_logger(__name__)


@dataclass
class AgentRunTaskRecord:
    """In-process metadata for one concurrent agent HTTP/stream run."""

    task_id: UUID
    session_id: UUID
    user_id: UUID | None
    started_at: datetime
    updated_at: datetime
    phase: str = "starting"
    tool_name: str | None = None
    status: str = "running"


class AgentController:
    """Main agent controller orchestrating the think-act-observe loop.

    Supports three execution modes:
    1. ReAct: Pure reactive reasoning with tool calls
    2. Plan-Execute: Upfront planning followed by execution
    3. Hybrid: Automatic selection based on task complexity
    """

    _session_tasks: dict[UUID, dict[UUID, asyncio.Event]] = {}
    _session_task_records: dict[UUID, dict[UUID, AgentRunTaskRecord]] = {}

    @classmethod
    def _register_session_task(
        cls,
        session_id: UUID,
        task_id: UUID,
        abort_event: asyncio.Event,
        user_id: UUID | None,
    ) -> None:
        now = datetime.utcnow()
        cls._session_tasks.setdefault(session_id, {})[task_id] = abort_event
        cls._session_task_records.setdefault(session_id, {})[task_id] = AgentRunTaskRecord(
            task_id=task_id,
            session_id=session_id,
            user_id=user_id,
            started_at=now,
            updated_at=now,
            phase="starting",
            tool_name=None,
            status="running",
        )

    @classmethod
    def _unregister_session_task(cls, session_id: UUID, task_id: UUID) -> None:
        sess = cls._session_tasks.get(session_id)
        if sess and task_id in sess:
            sess.pop(task_id)
            if not sess:
                cls._session_tasks.pop(session_id, None)
        recs = cls._session_task_records.get(session_id)
        if recs and task_id in recs:
            recs.pop(task_id)
            if not recs:
                cls._session_task_records.pop(session_id, None)

    @classmethod
    def _update_task_phase(
        cls,
        session_id: UUID,
        task_id: UUID,
        phase: str,
        tool_name: str | None = None,
    ) -> None:
        recs = cls._session_task_records.get(session_id)
        if not recs:
            return
        rec = recs.get(task_id)
        if rec is None:
            return
        rec.phase = phase
        rec.updated_at = datetime.utcnow()
        if tool_name is not None:
            rec.tool_name = tool_name

    @classmethod
    def cancel_session(cls, session_id: UUID) -> bool:
        """Signal abort on every in-flight task for this session."""
        tasks = cls._session_tasks.get(session_id)
        if not tasks:
            return False
        for ev in list(tasks.values()):
            ev.set()
        cls._session_tasks.pop(session_id, None)
        cls._session_task_records.pop(session_id, None)
        return True

    @classmethod
    def cancel_task(cls, session_id: UUID, task_id: UUID) -> bool:
        """Abort a single agent task within a session."""
        sess = cls._session_tasks.get(session_id)
        if not sess:
            return False
        ev = sess.get(task_id)
        if ev is None:
            return False
        ev.set()
        sess.pop(task_id, None)
        if not sess:
            cls._session_tasks.pop(session_id, None)
        recs = cls._session_task_records.get(session_id)
        if recs and task_id in recs:
            recs.pop(task_id)
            if not recs:
                cls._session_task_records.pop(session_id, None)
        return True

    @classmethod
    def list_agent_tasks_for_session(cls, session_id: UUID) -> list[AgentRunTaskRecord]:
        """Return snapshots of running agent tasks for ``session_id`` (this process only)."""
        recs = cls._session_task_records.get(session_id)
        if not recs:
            return []
        return sorted(recs.values(), key=lambda r: r.started_at)

    @classmethod
    def is_session_active(cls, session_id: UUID) -> bool:
        return bool(cls._session_tasks.get(session_id))

    def __init__(
        self,
        llm: LLMService,
        tools: ToolRegistry,
        planner: TaskPlanner,
        executor: ToolExecutor,
        *,
        agent_memory: AgentMemory | None = None,
        session_manager: SessionManager | None = None,
        workflow_engine: WorkflowEngine | None = None,
        hook_manager: HookManager | None = None,
        config: AgentConfig | None = None,
        permission_context: ToolPermissionContext | None = None,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.agent_memory = agent_memory
        self.session_manager = session_manager
        self.planner = planner
        self.executor = executor
        self.workflow_engine = workflow_engine
        self.config = config or AgentConfig()
        self._hooks = hook_manager
        self._permission_context = permission_context or ToolPermissionContext()
        self._abort_event = asyncio.Event()
        self._ingested_produced_paths: set[str] = set()

    def abort(self) -> None:
        """Signal abort to the running agent loop."""
        self._abort_event.set()

    def _build_tool_context(self, context: AgentContext):
        """Build a real :class:`ToolContext` from the running agent context.

        Used for permission checks so per-tool rules see the real
        ``user_id`` / ``session_id`` / ``task_id`` plus the shared service
        handles (DB, cache, file store, LLM) — same shape the tool receives
        during actual execution.
        """
        service_manager = getattr(self.executor, "service_manager", None)
        return build_tool_context(
            service_manager=service_manager,
            user_id=context.user_id,
            session_id=context.session_id,
            task_id=context.task_id,
            abort_signal=self._abort_event,
            extra={"agent_context": context},
        )

    async def run(
        self,
        user_input: str,
        session_id: UUID,
        *,
        user_id: UUID | None = None,
        attachments: list[str] | None = None,
        project_roots: list[str] | None = None,
        authorized_roots: list[str] | None = None,
        stream_handler: StreamHandler | None = None,
        skip_append_user: bool = False,
        persisted_user_message_id: UUID | None = None,
        agent_task_id: UUID | None = None,
    ) -> AgentResponse:
        """Execute the agent for a user request.

        ``project_roots`` is the optional code-project binding for this
        turn. When set, every absolute path is folded into
        ``ToolContext.extra['project_roots']`` so the path sandbox and
        the ``project_*`` / ``coding_agent`` tools accept it without
        widening any global env.

        ``authorized_roots`` lists session-scoped directory grants from
        ``POST …/authorized-paths`` (same sandbox semantics as project roots).

        ``agent_task_id`` optional stable id for this run (SSE ``agent_task`` / cancel).
        """
        handler = stream_handler or NoOpStreamHandler()
        self._abort_event.clear()
        self._ingested_produced_paths.clear()
        context = await self._create_context(session_id, user_id, task_id=agent_task_id)
        AgentController._register_session_task(
            session_id, context.task_id, self._abort_event, user_id,
        )
        context.start_time = datetime.utcnow()
        conversation = ConversationContext(session_id=session_id)

        try:
            from leagent.agent.current import bind_current_agent_controller

            with bind_current_agent_controller(self):
                self._persisted_user_message_id = persisted_user_message_id
                self._last_appended_user_index = None
                if self._hooks:
                    await self._hooks.dispatch_start(context, user_input)

                await context.transition_to(AgentState.THINKING)

                conversation = await self._load_conversation(session_id)
                context.conversation = conversation
                if not skip_append_user:
                    conversation.append_user_message(
                        self._format_user_message(
                            user_input,
                            attachments,
                            authorized_roots=authorized_roots,
                        )
                    )
                    self._last_appended_user_index = len(conversation.messages) - 1

                workflow_match = await self._match_workflow(user_input)
                if workflow_match:
                    wf_response = await self._run_workflow(workflow_match, context, handler)
                    if self._hooks:
                        await self._hooks.dispatch_complete(context, wf_response)
                    return wf_response

                if not self.config.use_query_engine:
                    logger.warning(
                        "legacy_agent_modes_deprecated",
                        mode=str(self.config.mode),
                    )
                result = await self._run_via_query_engine(
                    user_input,
                    conversation,
                    context,
                    handler,
                    attachments=attachments,
                    project_roots=project_roots,
                    authorized_roots=authorized_roots,
                    skip_user_append=skip_append_user,
                )

                if self._hooks:
                    await self._hooks.dispatch_complete(context, result)
                return result

        except asyncio.CancelledError:
            logger.warning("agent_cancelled", task_id=str(context.task_id))
            await self._save_resumable_state(
                session_id, user_input, context, conversation,
            )
            if self._hooks:
                await self._hooks.dispatch_cancel(context)
            return context.to_response(error="Execution cancelled")
        except LeAgentError as e:
            logger.error("agent_error", task_id=str(context.task_id), error=str(e))
            await handler.on_error(e)
            if self._hooks:
                await self._hooks.dispatch_error(context, e)
            return context.to_response(error=str(e))
        except Exception as e:
            logger.exception("agent_unexpected_error", task_id=str(context.task_id))
            await handler.on_error(e)
            if self._hooks:
                await self._hooks.dispatch_error(context, e)
            return context.to_response(error=f"Unexpected error: {e}")
        finally:
            if self._abort_event.is_set():
                await self._save_resumable_state(
                    session_id, user_input, context, conversation,
                )
            AgentController._unregister_session_task(session_id, context.task_id)
            await context.transition_to(AgentState.IDLE)
            await self._save_conversation(session_id, conversation)
            self._persisted_user_message_id = None
            self._last_appended_user_index = None
            await self._record_episode(session_id, user_input, context)

    async def run_stream(
        self,
        user_input: str,
        session_id: UUID,
        *,
        user_id: UUID | None = None,
        attachments: list[str] | None = None,
        project_roots: list[str] | None = None,
        authorized_roots: list[str] | None = None,
        skip_append_user: bool = False,
        persisted_user_message_id: UUID | None = None,
        agent_task_id: UUID | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Execute agent with streaming events."""
        queue_maxsize = 512
        try:
            from leagent.config.settings import get_settings as _gs

            queue_maxsize = max(1, int(_gs().agent.stream_queue_maxsize))
        except Exception:  # noqa: BLE001
            pass
        queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue(maxsize=queue_maxsize)
        stream_session_id = session_id

        async def _put_stream_event(event: StreamEvent | None) -> None:
            await queue.put(event)
            try:
                from leagent.utils.metrics import get_metrics

                get_metrics().record_stream_queue_depth("agent_stream", queue.qsize())
            except Exception:
                logger.debug("stream_queue_metrics_failed", exc_info=True)

        class QueueHandler:
            async def on_thinking(self, thought: str) -> None:
                await _put_stream_event(StreamEvent(type="thinking", data={"thought": thought}))

            async def on_tool_call(self, tool_call: ToolCall) -> None:
                await _put_stream_event(
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
                await _put_stream_event(StreamEvent(type="tool_call_delta", data=dict(payload)))

            async def on_nested_agent_preview(self, payload: dict[str, Any]) -> None:
                await _put_stream_event(StreamEvent(type="nested_agent_preview", data=dict(payload)))

            async def on_tool_result(self, result: ToolResult) -> None:
                await _put_stream_event(
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
                await _put_stream_event(
                    StreamEvent(
                        type="workspace_attachments",
                        data={
                            "session_id": str(stream_session_id),
                            "attachments": items,
                        },
                    )
                )

            async def on_token(self, token: str) -> None:
                await _put_stream_event(StreamEvent(type="token", data={"token": token}))

            async def on_user_input_request(self, payload: dict[str, Any]) -> None:
                await _put_stream_event(StreamEvent(type="user_input_request", data=payload))

            async def on_complete(self, response: AgentResponse) -> None:
                await _put_stream_event(
                    StreamEvent(
                        type="complete",
                        data={
                            "text": response.text,
                            "files": response.files,
                            "success": response.success,
                            "partial": response.partial,
                            "metadata": dict(response.metadata or {}),
                            "token_usage": dict(response.token_usage) if response.token_usage else None,
                        },
                    )
                )
                await _put_stream_event(None)

            async def on_error(self, error: Exception) -> None:
                await _put_stream_event(
                    StreamEvent(type="error", data={"error": str(error)})
                )
                await _put_stream_event(None)

        async def run_agent() -> None:
            try:
                await self.run(
                    user_input,
                    session_id,
                    user_id=user_id,
                    attachments=attachments,
                    project_roots=project_roots,
                    authorized_roots=authorized_roots,
                    stream_handler=QueueHandler(),
                    skip_append_user=skip_append_user,
                    persisted_user_message_id=persisted_user_message_id,
                    agent_task_id=agent_task_id,
                )
            except Exception:
                await queue.put(None)

        task = asyncio.create_task(run_agent())

        drain_timeout = 300.0
        try:
            from leagent.config.settings import get_settings as _gs
            drain_timeout = float(_gs().agent.stream_drain_timeout_sec)
        except Exception:  # noqa: BLE001
            pass

        saw_terminal_sentinel = False
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=drain_timeout)
                except asyncio.TimeoutError:
                    logger.warning(
                        "stream_drain_timeout",
                        session_id=str(session_id),
                        timeout_sec=drain_timeout,
                    )
                    self.abort()
                    yield StreamEvent(
                        type="error",
                        data={"error": f"No response for {int(drain_timeout)}s — stream aborted"},
                    )
                    break
                if event is None:
                    saw_terminal_sentinel = True
                    break
                try:
                    from leagent.utils.metrics import get_metrics

                    get_metrics().record_stream_queue_depth("agent_stream", queue.qsize())
                except Exception:
                    logger.debug("stream_queue_metrics_failed", exc_info=True)
                yield event
        finally:
            if saw_terminal_sentinel and not task.done():
                with suppress(asyncio.CancelledError, Exception):
                    await task
            elif not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await task

    # ------------------------------------------------------------------
    # ReAct loop
    # ------------------------------------------------------------------

    async def _run_react(
        self,
        conversation: ConversationContext,
        context: AgentContext,
        handler: StreamHandler,
        query: str = "",
    ) -> AgentResponse:
        """Pure ReAct (Reason-Act-Observe) loop with permission checks and partitioning."""
        system_prompt = await self._build_system_prompt(context, query=query)
        conversation.system_prompt = system_prompt

        while context.iteration < self.config.max_iterations:
            if context.is_cancelled or self._abort_event.is_set():
                break

            context.iteration += 1
            logger.debug(
                "react_iteration",
                task_id=str(context.task_id),
                iteration=context.iteration,
            )

            await context.transition_to(AgentState.THINKING)
            llm_response = await self._call_llm(conversation, context)

            tool_calls = await self._extract_tool_calls(
                llm_response,
                session_id=str(context.session_id),
            )

            if tool_calls:
                await context.transition_to(AgentState.EXECUTING)
                thought_text = llm_response.get("content", "")

                conversation.append_assistant_message(
                    thought_text,
                    tool_calls=[tc.model_dump() for tc in tool_calls],
                )

                capped_calls = tool_calls[: self.config.max_tool_calls_per_turn]

                # Partition into concurrent-safe and serial groups
                concurrent_safe: list[ToolCall] = []
                serial: list[ToolCall] = []
                for tc in capped_calls:
                    tool = self.tools.find_by_name(tc.name) if self.tools else None
                    if tool and getattr(tool, "is_concurrency_safe", False):
                        concurrent_safe.append(tc)
                    else:
                        serial.append(tc)

                async def _dispatch_tool(
                    tool_call: ToolCall,
                    thought_snapshot: str = thought_text,
                ) -> ToolResult:
                    # Permission check before execution
                    tool = self.tools.find_by_name(tool_call.name) if self.tools else None
                    if tool:
                        perm_ctx = self._build_tool_context(context)
                        perm = check_tool_permission(
                            tool,
                            tool_call.arguments,
                            self._permission_context,
                            tool_context=perm_ctx,
                        )
                        if not perm.allowed:
                            res = ToolResult(
                                tool_call_id=tool_call.id,
                                name=tool_call.name,
                                success=False,
                                error=f"Permission denied: {perm.reason}",
                            )
                            conversation.append_tool_result(tool_call.id, tool_call.name, res.content)
                            context.record_step(ExecutionStep(type=StepType.TOOL_RESULT, tool_result=res))
                            return res
                        if perm.updated_params:
                            tool_call.arguments = perm.updated_params

                    await handler.on_tool_call(tool_call)
                    if self._hooks:
                        await self._hooks.dispatch_tool_call(context, tool_call)
                    context.record_step(
                        ExecutionStep(
                            type=StepType.TOOL_CALL,
                            tool_call=tool_call,
                            thought=thought_snapshot,
                        )
                    )
                    base_res = await self.executor.run_tool(
                        tool_call.name, tool_call.arguments, context
                    )
                    res = ToolResult.from_base(
                        base_res, tool_call_id=tool_call.id, name=tool_call.name,
                    )
                    await handler.on_tool_result(res)
                    await self._ingest_produced_path_for_workspace(
                        context, res, context.session_id, context.user_id, handler
                    )
                    if self._hooks:
                        await self._hooks.dispatch_tool_result(context, tool_call, res)
                    context.record_step(
                        ExecutionStep(type=StepType.TOOL_RESULT, tool_result=res, duration_ms=res.duration_ms)
                    )
                    conversation.append_tool_result(tool_call.id, tool_call.name, res.content)
                    return res

                if concurrent_safe:
                    await asyncio.gather(*[_dispatch_tool(tc) for tc in concurrent_safe])

                for tool_call in serial:
                    if context.is_cancelled or self._abort_event.is_set():
                        break
                    await _dispatch_tool(tool_call)
            else:
                final_text = llm_response.get("content", "")
                conversation.append_assistant_message(final_text)

                context.record_step(
                    ExecutionStep(type=StepType.ANSWER, content=final_text)
                )

                response = context.to_response(text=final_text)
                await handler.on_complete(response)
                return response

        response = context.to_response(
            text="I've reached the maximum number of steps. Here's what I've done so far.",
        )
        response.partial = True
        await handler.on_complete(response)
        return response

    # ------------------------------------------------------------------
    # Plan-Execute loop
    # ------------------------------------------------------------------

    async def _run_plan_execute(
        self,
        conversation: ConversationContext,
        context: AgentContext,
        handler: StreamHandler,
    ) -> AgentResponse:
        """Plan-Execute mode: create plan upfront, then execute steps."""
        await context.transition_to(AgentState.THINKING)
        await handler.on_thinking("Creating execution plan...")

        user_task = conversation.messages[-1].content if conversation.messages else ""

        plan = await self.planner.plan(user_task, context, abort_event=self._abort_event)
        context.current_plan = plan

        plan_summary = json.dumps(
            {"goal": plan.goal, "steps": [{"id": s.id, "description": s.description} for s in plan.steps]},
            ensure_ascii=False,
            indent=2,
        )

        context.record_step(
            ExecutionStep(
                type=StepType.THOUGHT,
                thought=f"Created plan with {len(plan.steps)} steps",
                content=plan_summary,
            )
        )

        if self._hooks:
            await self._hooks.dispatch_plan_created(context, plan)

        conversation.append_assistant_message(
            f"I've created a {len(plan.steps)}-step plan:\n{plan_summary}"
        )

        await context.transition_to(AgentState.EXECUTING)

        from leagent.agent.planner import schedule_ready

        while not plan.is_complete and context.iteration < self.config.max_iterations:
            if context.is_cancelled or self._abort_event.is_set():
                break

            ready = schedule_ready(plan)
            if not ready:
                break
            context.iteration += 1
            active_plan = plan

            # Dispatch all ready steps concurrently: steps without a
            # tool are resolved inline; tool-bearing steps go through
            # the executor (permission check + run). Failures kick a
            # single replan and the loop restarts with the adjusted plan.
            async def _run_step(
                step: PlanStep,
                plan_snapshot: ExecutionPlan = active_plan,
            ) -> tuple[PlanStep, ToolResult | None]:
                await handler.on_thinking(
                    f"Executing step {step.id}: {step.description}"
                )
                if not step.tool:
                    plan_snapshot.mark_step_completed(step.id)
                    return step, None

                tool = self.tools.find_by_name(step.tool) if self.tools else None
                if tool is not None:
                    perm_ctx = self._build_tool_context(context)
                    perm = check_tool_permission(
                        tool,
                        step.params,
                        self._permission_context,
                        tool_context=perm_ctx,
                    )
                    if not perm.allowed:
                        plan_snapshot.mark_step_failed(step.id, f"Permission denied: {perm.reason}")
                        return step, ToolResult(
                            tool_call_id="",
                            name=step.tool,
                            success=False,
                            error=f"Permission denied: {perm.reason}",
                        )

                tool_call = ToolCall(name=step.tool, arguments=step.params)
                await handler.on_tool_call(tool_call)

                base_result = await self.executor.run_tool(
                    step.tool, step.params, context,
                )
                result = ToolResult.from_base(
                    base_result, tool_call_id=tool_call.id, name=step.tool,
                )
                await handler.on_tool_result(result)
                await self._ingest_produced_path_for_workspace(
                    context, result, context.session_id, context.user_id, handler
                )

                if result.success:
                    plan_snapshot.mark_step_completed(step.id, result.data)
                    context.record_step(
                        ExecutionStep(type=StepType.TOOL_RESULT, tool_result=result)
                    )
                else:
                    plan_snapshot.mark_step_failed(step.id, result.error or "Unknown error")
                return step, result

            outcomes = await asyncio.gather(*(_run_step(s) for s in ready))

            # If any step failed, attempt replan once before the next wave.
            failed = [(s, r) for s, r in outcomes if r is not None and not r.success]
            if failed:
                failed_step, failed_result = failed[0]
                revised = await self.planner.replan(
                    plan,
                    failed_step,
                    (failed_result.error if failed_result else "") or "Unknown error",
                    abort_event=self._abort_event,
                )
                if revised is not None:
                    from leagent.agent.planner import TaskPlanner
                    plan = TaskPlanner.merge_replan(plan, revised)
                    context.current_plan = plan
                    context.record_step(
                        ExecutionStep(
                            type=StepType.REPLAN,
                            content=(
                                f"Replanned due to error in step "
                                f"{failed_step.id}: {failed_result.error if failed_result else ''}"
                            ),
                        )
                    )

        final_text = await self._generate_summary(plan, context)
        response = context.to_response(text=final_text)
        await handler.on_complete(response)
        return response

    # ------------------------------------------------------------------
    # Hybrid
    # ------------------------------------------------------------------

    async def _run_hybrid(
        self,
        user_input: str,
        conversation: ConversationContext,
        context: AgentContext,
        handler: StreamHandler,
    ) -> AgentResponse:
        """Hybrid mode: use planning for complex tasks, ReAct for simple ones."""
        complexity = await self._estimate_complexity(user_input, context)

        if complexity >= self.config.plan_threshold:
            logger.info("hybrid_using_plan_execute", task_id=str(context.task_id), complexity=complexity)
            return await self._run_plan_execute(conversation, context, handler)
        else:
            logger.info("hybrid_using_react", task_id=str(context.task_id), complexity=complexity)
            return await self._run_react(conversation, context, handler, query=user_input)

    # ------------------------------------------------------------------
    # LLM interaction
    # ------------------------------------------------------------------

    async def _call_llm(
        self,
        conversation: ConversationContext,
        context: AgentContext,
    ) -> dict[str, Any]:
        """Call LLM with context compaction and enabled-tool filtering."""
        await self._maybe_compact(conversation, context)

        messages = conversation.to_messages()

        # Only send schemas for enabled, non-denied tools
        if self.tools:
            tool_schemas = self.tools.get_tools_for_llm(
                deny_patterns=self._permission_context.always_deny_rules,
                provider_format="openai",
            )
        else:
            tool_schemas = []

        try:
            response = await self.llm.chat(
                messages=messages,
                tools=tool_schemas if tool_schemas else None,
                tool_choice="auto" if tool_schemas else None,
                temperature=self.config.temperature,
                model_tier=self.config.model_tier,
            )
            return response
        except LLMServiceError:
            if self.config.model_tier == "tier1":
                logger.warning("tier1_failed_falling_back", task_id=str(context.task_id))
                response = await self.llm.chat(
                    messages=messages,
                    tools=tool_schemas if tool_schemas else None,
                    tool_choice="auto" if tool_schemas else None,
                    temperature=self.config.temperature,
                    model_tier="tier2",
                )
                return response
            raise

    async def _maybe_compact(self, conversation: ConversationContext, context: AgentContext) -> None:
        """Apply context compression if the conversation is getting large."""
        if self._hooks:
            with contextlib.suppress(Exception):
                await self._hooks.dispatch_pre_compact(context)

        try:
            from leagent.services.compact.service import CompactService
            compact_svc = CompactService(llm_service=self.llm)
            await compact_svc.maybe_compact(conversation)
        except Exception as e:
            logger.debug("compact_skipped", error=str(e))

        if self._hooks:
            with contextlib.suppress(Exception):
                await self._hooks.dispatch_post_compact(context)

    async def _extract_tool_calls(
        self,
        llm_response: dict[str, Any],
        *,
        session_id: str | None = None,
    ) -> list[ToolCall]:
        """Extract tool calls from LLM response (supports both OpenAI and Anthropic formats)."""
        from leagent.agent.deps import (
            _ingest_session_id,
            _try_blob_streaming_ingest,
            _try_direct_content_ingest,
            _try_salvage_truncated_ui_tree,
        )

        ingest_sid = _ingest_session_id(session_id)
        # OpenAI format
        tool_calls_raw = llm_response.get("tool_calls", [])

        # Anthropic format: content blocks with type=tool_use
        if not tool_calls_raw:
            content_blocks = llm_response.get("content", [])
            if isinstance(content_blocks, list):
                for block in content_blocks:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_calls_raw.append({
                            "id": block.get("id", ""),
                            "function": {
                                "name": block.get("name", ""),
                                "arguments": block.get("input", {}),
                            },
                        })

        if not tool_calls_raw:
            return []

        tool_calls = []
        for tc in tool_calls_raw:
            func = tc.get("function", {})
            name = func.get("name", "")
            args_str = func.get("arguments", "{}")
            if isinstance(args_str, dict):
                arguments = args_str
            elif isinstance(args_str, str):
                parsed = parse_tool_arguments_str(args_str)
                if parsed is not None:
                    arguments = parsed
                else:
                    ingested = await _try_blob_streaming_ingest(
                        name,
                        args_str,
                        session_id=ingest_sid,
                    )
                    if ingested is not None:
                        arguments = ingested
                    elif (
                        content_ingested := await _try_direct_content_ingest(
                            name,
                            args_str,
                            session_id=ingest_sid,
                        )
                    ) is not None:
                        arguments = content_ingested
                    elif (
                        salvaged := _try_salvage_truncated_ui_tree(name, args_str)
                    ) is not None:
                        arguments = salvaged
                    else:
                        strict_err = strict_json_loads_error(args_str)
                        logger.warning(
                            "tool_call_parse_error",
                            error=str(strict_err)
                            if strict_err
                            else "unrecoverable_tool_arguments",
                            args_len=len(args_str),
                            json_lineno=getattr(strict_err, "lineno", None),
                            json_colno=getattr(strict_err, "colno", None),
                            json_pos=getattr(strict_err, "pos", None),
                            raw=tc,
                        )
                        arguments = {"__raw__": args_str}
            else:
                arguments = {}

            tool_calls.append(
                ToolCall(
                    id=tc.get("id", ""),
                    name=name,
                    arguments=arguments if isinstance(arguments, dict) else {},
                )
            )

        return tool_calls

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    async def _build_system_prompt(self, context: AgentContext, query: str = "") -> str:
        """Delegate to :class:`PromptBuilder` for the default agent variant.

        The controller no longer owns persona text, tool listing, file
        access policy, or memory recall formatting — the builder does.
        We still run recall at this call site because the legacy ReAct /
        plan-execute paths consume the final string directly (unlike the
        QueryEngine path which threads a ``RecallHandle`` through).
        """
        builder = get_prompt_builder()
        prompt_variant = getattr(self.config, "prompt_variant", "default_agent") or "default_agent"
        ctx = PromptContext(
            variant=prompt_variant,
            query=query or "",
            cwd=".",
            tools=self.tools,
            permission_context=self._permission_context,
            agent_memory=self.agent_memory if self.config.enable_memory else None,
            session_manager=self.session_manager,
            session_id=context.session_id,
            user_id=context.user_id,
            agent_id=getattr(self.config, "agent_name", "default") or "default",
            append_extra=getattr(self.config, "extra_system_prompt", "") or "",
        )
        built = await builder.build(ctx)
        return built.system_text

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _estimate_complexity(self, user_input: str, context: AgentContext) -> int:
        """Estimate task complexity (1-10) for mode selection.

        Delegates to :meth:`TaskPlanner.estimate_complexity` so the
        ReAct/Plan-Execute routing heuristic lives next to the rest of
        the planning knowledge.
        """
        if self.planner is not None:
            return self.planner.estimate_complexity(user_input)
        # Fallback when an agent runs without a planner (rare).
        return 5 if len(user_input) > 200 else 2

    async def _generate_summary(self, plan: ExecutionPlan, context: AgentContext) -> str:
        completed = [s for s in plan.steps if s.status == "completed"]
        failed = [s for s in plan.steps if s.status == "failed"]

        if not completed and not failed:
            return "No steps were executed."

        summary_parts = [f"Goal: {plan.goal}\n"]

        if completed:
            summary_parts.append(f"Completed {len(completed)} steps:")
            for step in completed:
                summary_parts.append(f"  - {step.description}")

        if failed:
            summary_parts.append(f"\nFailed {len(failed)} steps:")
            for step in failed:
                summary_parts.append(f"  - {step.description}: {step.error}")

        return "\n".join(summary_parts)

    async def _create_context(
        self,
        session_id: UUID,
        user_id: UUID | None,
        *,
        task_id: UUID | None = None,
    ) -> AgentContext:
        kw: dict[str, Any] = {
            "session_id": session_id,
            "user_id": user_id,
            "agent_memory": self.agent_memory,
            "tools": self.tools,
            "llm": self.llm,
            "config": self.config,
        }
        if task_id is not None:
            kw["task_id"] = task_id
        return AgentContext(**kw)

    async def _load_conversation(self, session_id: UUID) -> ConversationContext:
        """Load the running transcript for ``session_id`` from the session store.

        The :class:`SessionManager` is now the sole source of truth; the
        legacy short-term memory helper has been removed. If the manager
        is unavailable (degraded mode) we return a fresh
        :class:`ConversationContext` so the agent can still run, it just
        won't have history.
        """
        if self.session_manager is None:
            return ConversationContext(session_id=session_id)
        try:
            state = await self.session_manager.load(session_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("session_load_failed", error=str(exc))
            return ConversationContext(session_id=session_id)
        if state is None:
            return ConversationContext(session_id=session_id)

        conversation = ConversationContext(session_id=session_id)
        tool_call_names: dict[str, str] = {}
        for message in state.messages:
            role = message.role
            if role == "user":
                conversation.append_user_message(message.content)
            elif role == "assistant":
                conversation.append_assistant_message(
                    message.content,
                    tool_calls=message.tool_calls,
                    reasoning_content=getattr(message, "reasoning_content", None),
                )
                for tc in message.tool_calls or []:
                    tc_id = tc.get("id", "")
                    tc_name = tc.get("name") or tc.get("function", {}).get("name", "")
                    if tc_id and tc_name:
                        tool_call_names[tc_id] = tc_name
            elif role == "tool":
                tool_name = tool_call_names.get(message.tool_call_id or "", "")
                conversation.append_tool_result(
                    message.tool_call_id or "",
                    tool_name,
                    message.content,
                )
        return conversation

    async def _save_conversation(
        self, session_id: UUID, conversation: ConversationContext
    ) -> None:
        """Persist the latest transcript through the :class:`SessionManager`.

        :meth:`ConversationContext.trim` already clamps the length so we
        simply replace the authoritative message list — the session store
        handles durability + Redis refresh.
        """
        if self.session_manager is None:
            return
        try:
            conversation.trim()
            from leagent.services.session import SessionMessage

            _dict_msgs = [m.to_openai_format() for m in conversation.messages]
            _inject_pending_ask_user_tool_stubs(_dict_msgs)
            inject_missing_tool_result_stubs(_dict_msgs)
            conversation.messages = [
                ConversationMessage(
                    role=str(d.get("role") or "user"),
                    content=str(d.get("content") or ""),
                    name=d.get("name"),
                    tool_call_id=d.get("tool_call_id"),
                    tool_calls=d.get("tool_calls"),
                    reasoning_content=d.get("reasoning_content"),
                )
                for d in _dict_msgs
            ]

            persisted_uid = getattr(self, "_persisted_user_message_id", None)
            append_idx = getattr(self, "_last_appended_user_index", None)

            async with self.session_manager.locked(session_id) as state:
                previous = list(state.messages)
                session_messages: list[SessionMessage] = []
                for i, msg in enumerate(conversation.messages):
                    msg_id = None
                    if i < len(previous) and previous[i].role == str(msg.role):
                        msg_id = previous[i].id
                    if (
                        persisted_uid is not None
                        and append_idx is not None
                        and i == append_idx
                        and str(msg.role) == "user"
                    ):
                        msg_id = persisted_uid
                    session_messages.append(
                        SessionMessage(
                            id=msg_id or uuid4(),
                            role=str(msg.role),
                            content=str(msg.content or ""),
                            tool_call_id=getattr(msg, "tool_call_id", None),
                            tool_calls=getattr(msg, "tool_calls", None),
                            reasoning_content=getattr(msg, "reasoning_content", None),
                        )
                    )
                state.replace_messages(session_messages)
        except Exception as exc:  # noqa: BLE001
            logger.warning("session_save_failed", error=str(exc))

    async def _save_resumable_state(
        self,
        session_id: UUID,
        user_input: str,
        context: "AgentContext",
        conversation: "ConversationContext",
    ) -> None:
        """Persist a lightweight snapshot so the user can resume with 'continue'."""
        try:
            from leagent.services.chat.service import ChatService
            from leagent.services.database import get_database_service

            partial_response = ""
            for msg in reversed(conversation.messages):
                if getattr(msg, "role", "") == "assistant":
                    partial_response = str(getattr(msg, "content", "") or "")
                    break

            resumable = {
                "user_message": user_input,
                "partial_response": partial_response[:2000],
                "turn_index": context.iteration,
                "interrupted": True,
            }

            db = get_database_service()
            async with db.session() as session:
                from leagent.services.database.models.message import ChatSession
                chat_session = await session.get(ChatSession, session_id)
                if chat_session:
                    import json as _json
                    existing_meta = {}
                    if chat_session.session_metadata:
                        try:
                            existing_meta = _json.loads(chat_session.session_metadata)
                        except (TypeError, ValueError):
                            existing_meta = {}
                    existing_meta["resumable_state"] = resumable
                    chat_session.session_metadata = _json.dumps(existing_meta)
                    session.add(chat_session)
        except Exception as exc:  # noqa: BLE001
            logger.debug("save_resumable_state_failed", error=str(exc))

    # ------------------------------------------------------------------
    # QueryEngine-backed execution path
    # ------------------------------------------------------------------

    @staticmethod
    def _openai_seed_messages_from_conversation(
        conversation: ConversationContext,
        *,
        skip_user_trim: bool,
    ) -> list[dict[str, Any]]:
        msgs = [
            m.to_openai_format()
            for m in conversation.messages
            if m.role in ("user", "assistant", "tool")
        ]
        if skip_user_trim or not msgs:
            return msgs
        if msgs[-1].get("role") == "user":
            return msgs[:-1]
        return msgs

    async def _run_via_query_engine(
        self,
        user_input: str,
        conversation: ConversationContext,
        context: AgentContext,
        handler: StreamHandler,
        *,
        attachments: list[str] | None = None,
        project_roots: list[str] | None = None,
        authorized_roots: list[str] | None = None,
        skip_user_append: bool = False,
    ) -> AgentResponse:
        """Delegate the think-act loop to the new ``QueryEngine``.

        This is now the default execution path. The controller keeps
        hooks, permissions, workflow matching, and conversation
        persistence around the engine so every existing consumer
        (API/WebSocket/CLI) observes the same ``StreamHandler`` events
        and ``AgentResponse`` shape it did before.
        """
        from leagent.agent.query_engine import QueryEngine, QueryEngineConfig

        append_extra = getattr(self.config, "extra_system_prompt", "") or ""

        # Keep forwarding attachment storage paths so tools can access files,
        # and provide ID/name lookup maps to support deterministic resolution.
        session_attachment_paths: list[str] = []
        session_attachments: list[Any] = []
        if self.session_manager is not None:
            try:
                session_attachments = await self.session_manager.list_attachments(
                    context.session_id
                )
                session_attachment_paths = [
                    att.storage_path for att in session_attachments if att.storage_path
                ]
            except Exception as exc:  # noqa: BLE001
                logger.warning("session_attachments_load_failed", error=str(exc))

        tool_extra: dict[str, Any] = {}
        merged_attachments = list(session_attachment_paths)
        if attachments:
            for path in attachments:
                if path not in merged_attachments:
                    merged_attachments.append(path)
        tool_extra.update(
            build_tool_extra_for_attachment_paths(session_attachments, merged_attachments),
        )
        normalized_attachments = tool_extra.get("attachments") or []

        # Code-project binding for this turn (folder in project mode).
        # Folded into the same ``project_roots`` key the path sandbox
        # already understands, so every project_* tool and the coding
        # agent see the directory without widening any global config.
        if project_roots:
            existing_roots = list(tool_extra.get("project_roots") or [])
            for raw in project_roots:
                if not raw:
                    continue
                if raw not in existing_roots:
                    existing_roots.append(raw)
            if existing_roots:
                tool_extra["project_roots"] = existing_roots

        if authorized_roots:
            existing_auth = list(tool_extra.get("authorized_roots") or [])
            for raw in authorized_roots:
                if not raw:
                    continue
                if raw not in existing_auth:
                    existing_auth.append(raw)
            if existing_auth:
                tool_extra["authorized_roots"] = existing_auth

        async def _emit_nested_preview(payload: dict[str, Any]) -> None:
            await handler.on_nested_agent_preview(payload)

        tool_extra["nested_preview_emit"] = _emit_nested_preview

        from leagent.skills.manager import get_skills_manager

        # When the request carries a code-project binding, run the
        # engine with cwd anchored to the project root so the L4
        # ``project_memory`` source naturally discovers AGENTS.md /
        # memory.md inside the project, and so the LLM can read the
        # project_path off ``QueryEngine.cwd`` without us forking a
        # dedicated coding sub-agent up front.
        engine_cwd = "."
        primary_project_root = next(
            (p for p in (tool_extra.get("project_roots") or []) if isinstance(p, str) and p),
            None,
        )
        if primary_project_root:
            engine_cwd = primary_project_root

        tools_deny_patterns = list(getattr(self.config, "tools_deny_patterns", []) or [])
        if primary_project_root is None and "project_*" not in tools_deny_patterns:
            tools_deny_patterns.append("project_*")

        engine_config = QueryEngineConfig(
            cwd=engine_cwd,
            llm=self.llm,
            tools=self.tools,
            executor=self.executor,
            agent_memory=self.agent_memory,
            hooks=self._hooks,
            append_system_prompt=append_extra,
            max_turns=self.config.max_iterations,
            max_tool_calls_per_turn=self.config.max_tool_calls_per_turn,
            temperature=self.config.temperature,
            tools_deny_patterns=tools_deny_patterns,
            model_tier=self.config.model_tier,
            model_provider=self.config.model_provider,
            model_name=self.config.model_name,
            user_id=context.user_id,
            session_id=context.session_id,
            abort_event=self._abort_event,
            tool_extra=tool_extra,
            session_manager=self.session_manager,
            permission_context=self._permission_context,
            prompt_variant=getattr(self.config, "prompt_variant", "default_agent") or "default_agent",
            skills_manager=get_skills_manager(),
            initial_messages=self._openai_seed_messages_from_conversation(
                conversation,
                skip_user_trim=skip_user_append,
            ),
        )
        engine = QueryEngine(engine_config)

        AgentController._update_task_phase(
            context.session_id, context.task_id, "llm",
        )
        streaming_phase_marked = False

        response_text = ""
        reasoning_acc = ""
        final_usage: dict[str, int] = {}

        formatted_attachments = normalized_attachments if normalized_attachments else attachments
        query_input = self._format_user_message(
            user_input,
            formatted_attachments,
            authorized_roots=authorized_roots,
        )
        resume_hint = "Continue after the tool results above."
        submit_kw: dict[str, Any] = {"append_user_turn": not skip_user_append}
        turn_message_start = len(conversation.messages)
        async for sdk_msg in engine.submit_message(
            resume_hint if skip_user_append else query_input,
            **submit_kw,
        ):
            if context.is_cancelled or self._abort_event.is_set():
                engine.abort()
                break

            mtype = sdk_msg.type
            data = sdk_msg.data

            if mtype == "stream_delta":
                if not streaming_phase_marked:
                    AgentController._update_task_phase(
                        context.session_id, context.task_id, "streaming",
                    )
                    streaming_phase_marked = True
                token = data.get("content", "")
                if isinstance(token, str) and token:
                    response_text += token
                    await handler.on_token(token)
                rd = data.get("reasoning_delta")
                if isinstance(rd, str) and rd:
                    reasoning_acc += rd
                    await handler.on_thinking(reasoning_acc)
            elif mtype == "tool_call_delta":
                if isinstance(data, dict):
                    await handler.on_tool_call_delta(data)
            elif mtype == "tool_use":
                tc = ToolCall(
                    id=data.get("id", ""),
                    name=data.get("name", ""),
                    arguments=data.get("input") or {},
                )
                AgentController._update_task_phase(
                    context.session_id,
                    context.task_id,
                    "tool",
                    tool_name=tc.name or None,
                )
                await handler.on_tool_call(tc)
                if self._hooks:
                    await self._hooks.dispatch_tool_call(context, tc)
                context.record_step(
                    ExecutionStep(type=StepType.TOOL_CALL, tool_call=tc)
                )
            elif mtype == "tool_result":
                res = self._tool_result_from_query_sdk(
                    data if isinstance(data, dict) else {}
                )
                await handler.on_tool_result(res)
                context.record_step(
                    ExecutionStep(type=StepType.TOOL_RESULT, tool_result=res)
                )
                conversation.append_tool_result(res.tool_call_id, res.name, res.content)
            elif mtype == "workspace_attachments":
                attachments_payload = data.get("attachments") if isinstance(data, dict) else None
                if isinstance(attachments_payload, list):
                    await handler.on_workspace_attachments(
                        [item for item in attachments_payload if isinstance(item, dict)]
                    )
                paths_payload = data.get("paths") if isinstance(data, dict) else None
                if isinstance(paths_payload, list):
                    for path in paths_payload:
                        if isinstance(path, str) and path:
                            context.add_output_file(path)
            elif mtype == "assistant_tools":
                text = str(data.get("content") or "")
                if text:
                    response_text = text
                tcs = data.get("tool_calls")
                rc = data.get("reasoning_content")
                reasoning = rc if isinstance(rc, str) and rc.strip() else None
                if isinstance(tcs, list):
                    conversation.append_assistant_message(
                        text, tool_calls=tcs, reasoning_content=reasoning
                    )
            elif mtype == "assistant":
                text = data.get("content") or ""
                if text and text not in response_text:
                    response_text = text
                rc = data.get("reasoning_content")
                reasoning = rc if isinstance(rc, str) and rc.strip() else None
                conversation.append_assistant_message(text, reasoning_content=reasoning)
            elif mtype == "result":
                final_usage = data.get("usage", {}) or {}
                reason = data.get("reason", "completed")
                if reason == TerminalReason.AWAITING_USER_INPUT.value:
                    meta = data.get("meta") or {}
                    tool_call = meta.get("tool_call") or {}
                    questions = meta.get("questions") or []
                    last_tcs: list[dict[str, Any]] | None = None
                    if conversation.messages:
                        last = conversation.messages[-1]
                        if last.role == "assistant":
                            last_tcs = last.tool_calls
                    await handler.on_user_input_request(
                        {
                            "tool_call": tool_call,
                            "questions": questions,
                            "assistant_tool_calls": last_tcs,
                        },
                    )
                    _tid = str(tool_call.get("id") or "").strip()
                    if _tid:
                        conversation.append_tool_result(
                            _tid,
                            str(tool_call.get("name") or ASK_USER_TOOL_NAME),
                            ASK_USER_PENDING_TOOL_JSON,
                        )
                    response = context.to_response()
                    response.text = response_text
                    response.partial = True
                    response.metadata = {
                        "awaiting_user_input": True,
                        "tool_call": tool_call,
                        "questions": questions,
                        "assistant_tool_calls": last_tcs,
                    }
                    if final_usage:
                        with contextlib.suppress(Exception):
                            tu = {
                                "prompt_tokens": int(final_usage.get("prompt_tokens", 0) or 0),
                                "completion_tokens": int(
                                    final_usage.get("completion_tokens", 0) or 0,
                                ),
                                "total_tokens": int(final_usage.get("total_tokens", 0) or 0),
                                "reasoning_tokens": int(final_usage.get("reasoning_tokens", 0) or 0),
                            }
                            for _ck in ("prompt_cache_hit_tokens", "prompt_cache_miss_tokens"):
                                if _ck in final_usage:
                                    tu[_ck] = int(final_usage.get(_ck, 0) or 0)
                            response.token_usage = tu
                    await handler.on_complete(response)
                    return response
                if reason != "completed" and data.get("error"):
                    err = data.get("error")
                    await handler.on_error(RuntimeError(str(err)))

        context.record_step(ExecutionStep(type=StepType.ANSWER, content=response_text))
        response = context.to_response()
        response.text = response_text
        if final_usage:
            with contextlib.suppress(Exception):
                tu = {
                    "prompt_tokens": int(final_usage.get("prompt_tokens", 0) or 0),
                    "completion_tokens": int(final_usage.get("completion_tokens", 0) or 0),
                    "total_tokens": int(final_usage.get("total_tokens", 0) or 0),
                    "reasoning_tokens": int(final_usage.get("reasoning_tokens", 0) or 0),
                }
                for _ck in ("prompt_cache_hit_tokens", "prompt_cache_miss_tokens"):
                    if _ck in final_usage:
                        tu[_ck] = int(final_usage.get(_ck, 0) or 0)
                response.token_usage = tu
        meta = dict(response.metadata or {})
        merged_tc_by_id: dict[str, dict[str, Any]] = {}
        last_reasoning: str | None = None
        for msg in conversation.messages[turn_message_start:]:
            if msg.role != "assistant":
                continue
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    if isinstance(tc, dict):
                        tid = str(tc.get("id") or "").strip()
                        if tid:
                            merged_tc_by_id[tid] = tc
            rc = getattr(msg, "reasoning_content", None)
            if isinstance(rc, str) and rc.strip():
                last_reasoning = rc.strip()
        if merged_tc_by_id:
            meta["assistant_tool_calls"] = list(merged_tc_by_id.values())
        if last_reasoning:
            meta["reasoning_content"] = last_reasoning
        response.metadata = meta
        await handler.on_complete(response)
        return response

    def _tool_result_from_query_sdk(self, data: dict[str, Any]) -> ToolResult:
        """Reconstruct a :class:`ToolResult` from :class:`QueryEngine` tool_result data."""
        env = data.get("envelope")
        if isinstance(env, dict):
            try:
                base = SimpleNamespace(
                    success=bool(env.get("success", True)),
                    data=env.get("data"),
                    error=env.get("error"),
                    metadata=dict(env.get("metadata") or {}),
                    duration_ms=int(env.get("duration_ms", 0) or 0),
                )
                return ToolResult.from_base(
                    base,
                    tool_call_id=str(data.get("tool_use_id", "")),
                    name=str(data.get("name", "")),
                )
            except Exception:  # noqa: BLE001
                logger.debug("query_sdk_envelope_reconstruct_failed", exc_info=True)
        tool_content = str(data.get("content", ""))
        is_success = bool(data.get("success", True))
        if is_success:
            return ToolResult(
                tool_call_id=str(data.get("tool_use_id", "")),
                name=str(data.get("name", "")),
                success=True,
                data=tool_content,
            )
        error_text = tool_content
        if error_text.startswith("Error: "):
            error_text = error_text[7:]
        return ToolResult(
            tool_call_id=str(data.get("tool_use_id", "")),
            name=str(data.get("name", "")),
            success=False,
            error=error_text or "Unknown error",
        )

    async def _ingest_produced_path_for_workspace(
        self,
        context: AgentContext,
        res: ToolResult,
        session_id: UUID,
        user_id: UUID | None,
        handler: Any,
    ) -> None:
        """When a tool writes a file, register it as a session attachment and notify the UI."""
        if not res.success or self.session_manager is None:
            return
        registrar = ArtifactRegistrar(self.session_manager)
        registered = await registrar.register_tool_result(
            session_id=session_id,
            user_id=user_id,
            data=res.data,
            metadata=res.metadata,
            seen_paths=self._ingested_produced_paths,
        )
        for item in registered:
            context.add_output_file(item.path)

        attachments = attachment_dicts(registered)
        if not attachments:
            return
        ingest = getattr(handler, "on_workspace_attachments", None)
        if ingest is not None:
            await ingest(attachments)

    @staticmethod
    def _coerce_tool_result_data(raw: Any) -> dict[str, Any]:
        """Normalise ``ToolResult.data`` to a dict for path extraction."""
        return coerce_tool_result_data(raw)

    _SINGLE_PATH_KEYS = (
        "file_path",
        "path",
        "output_path",
        "saved_path",
        "saved_to",
        "destination",
        "output_file",
        "target_path",
        "download_path",
    )

    def _produced_file_candidates(
        self,
        res: ToolResult,
    ) -> list[tuple[str, str | None, str | None]]:
        """Collect file paths emitted by tools into ``(path, name, root)`` triples."""
        candidates = extract_produced_path_candidates(res.data, metadata=res.metadata)
        return [(c.path, c.display_name, c.allowed_root) for c in candidates]

    @staticmethod
    def _resolved_workspace_root(raw: str | None) -> Path | None:
        if not raw:
            return None
        try:
            return Path(raw).expanduser().resolve()
        except OSError:
            return None

    @staticmethod
    def _path_is_inside(path: Path, root: Path) -> bool:
        try:
            resolved = path.expanduser().resolve()
            return resolved == root or resolved.is_relative_to(root)
        except OSError:
            return False

    async def _match_workflow(self, user_input: str) -> dict[str, Any] | None:
        if not self.workflow_engine:
            return None
        try:
            return await self.workflow_engine.match(user_input)
        except Exception as e:
            logger.debug("workflow_match_error", error=str(e))
            return None

    async def _run_workflow(
        self,
        workflow_match: dict[str, Any],
        context: AgentContext,
        handler: StreamHandler,
    ) -> AgentResponse:
        if not self.workflow_engine:
            return context.to_response(error="Workflow engine not configured")

        AgentController._update_task_phase(
            context.session_id, context.task_id, "workflow",
        )

        try:
            await context.transition_to(AgentState.EXECUTING)
            workflow_id = workflow_match.get("workflow_id", "")
            inputs = workflow_match.get("inputs", {})

            await handler.on_thinking(f"Running workflow: {workflow_id}")

            result = await self.workflow_engine.execute(
                workflow_id=workflow_id,
                inputs=inputs,
                context_vars={
                    "session_id": str(context.session_id),
                    "user_id": str(context.user_id) if context.user_id else "",
                },
            )

            text = result.get("output", str(result))
            context.record_step(ExecutionStep(type=StepType.ANSWER, content=text))
            response = context.to_response(text=text)
            await handler.on_complete(response)
            return response
        except Exception as e:
            logger.exception("workflow_execution_error", workflow=workflow_match)
            return context.to_response(error=f"Workflow execution failed: {e}")

    def _episode_paths_from_steps(self, steps: list[ExecutionStep]) -> list[str]:
        """Paths touched or returned by tools this turn (for episodic recall)."""
        seen: OrderedDict[str, None] = OrderedDict()
        project_path_tools = frozenset(
            {
                "project_write",
                "project_edit",
                "project_apply_patch",
                "project_read",
            }
        )
        for s in steps:
            if s.type == StepType.TOOL_CALL and s.tool_call:
                name = s.tool_call.name
                args = s.tool_call.arguments or {}
                if name in project_path_tools or name in (
                    "coding_agent",
                    "script_agent",
                    "code_execution",
                ):
                    for key in ("path", "project_path"):
                        p = args.get(key)
                        if isinstance(p, str) and p.strip():
                            seen.setdefault(p.strip(), None)
                            break
            if s.type == StepType.TOOL_RESULT and s.tool_result:
                tr = s.tool_result
                data = self._coerce_tool_result_data(tr.data)
                changed = data.get("changed_files")
                if isinstance(changed, list):
                    for p in changed:
                        if isinstance(p, str) and p.strip():
                            seen.setdefault(p.strip(), None)
                for key in ("produced_files", "files"):
                    lst = data.get(key)
                    if not isinstance(lst, list):
                        continue
                    for item in lst:
                        if isinstance(item, str) and item.strip():
                            seen.setdefault(item.strip(), None)
                        elif isinstance(item, dict):
                            for sk in self._SINGLE_PATH_KEYS:
                                v = item.get(sk)
                                if isinstance(v, str) and v.strip():
                                    seen.setdefault(v.strip(), None)
        return list(seen.keys())[:64]

    async def _record_episode(
        self, session_id: UUID, user_input: str, context: AgentContext
    ) -> None:
        """Persist turn memory via the formation policy in :class:`AgentMemory`.

        Delegates to :meth:`AgentMemory.observe_turn`, which scores the
        turn across multiple signals and writes episodic, procedural,
        and/or semantic memory as appropriate.
        """
        if not self.config.enable_memory or self.agent_memory is None:
            return
        try:
            from leagent.memory.formation import TriggerKind, TurnObservation

            answer_steps = [s for s in context.steps if s.type == StepType.ANSWER]
            if not answer_steps:
                return
            answer_text = str(answer_steps[-1].content or "")
            if not answer_text:
                return

            tool_names: list[str] = []
            tool_successes = 0
            tool_failures = 0
            for step in context.steps:
                if step.type == StepType.TOOL_CALL and step.tool_call:
                    tool_names.append(step.tool_call.name)
                if step.type == StepType.TOOL_RESULT and step.tool_result:
                    if step.tool_result.success:
                        tool_successes += 1
                    else:
                        tool_failures += 1

            paths = self._episode_paths_from_steps(context.steps)
            tags = [f"path:{p}" for p in paths[:48]]

            obs = TurnObservation(
                session_id=session_id,
                user_id=context.user_id,
                trigger=TriggerKind.TURN_COMPLETE,
                user_text=user_input[:400].strip(),
                assistant_text=answer_text[:800].strip(),
                tool_names=tool_names,
                tool_success_count=tool_successes,
                tool_failure_count=tool_failures,
                total_steps=len(context.steps),
                tags=tags,
            )
            await self.agent_memory.observe_turn(obs)
        except Exception as exc:  # noqa: BLE001
            logger.warning("episode_record_failed", error=str(exc))

    def _format_user_message(
        self,
        content: str,
        attachments: list[str] | None,
        *,
        authorized_roots: list[str] | None = None,
    ) -> str:
        parts = [content]
        if attachments:
            attachment_info = "\n\nAttached files:\n"
            for path in attachments:
                attachment_info += f"- {path}\n"
            parts.append(attachment_info)
        if authorized_roots:
            root_info = "\n\nAuthorized folders for this chat:\n"
            for path in authorized_roots:
                root_info += f"- {path}\n"
            if len(authorized_roots) == 1:
                root_info += (
                    "When the user says \"this folder\", interpret it as the authorized folder above.\n"
                )
            else:
                root_info += (
                    "If the user says \"this folder\" and the target is ambiguous, ask which folder they mean.\n"
                )
            parts.append(root_info)
        return "".join(parts)


class ModelRouter:
    """Routes requests to appropriate LLM tier based on task characteristics."""

    TIER1_TRIGGERS = ["plan", "analyze", "report", "compare", "evaluate", "reason", "complex"]
    TIER2_TRIGGERS = ["classify", "extract", "summarize", "format", "translate", "tag", "simple"]

    def route(self, task_description: str, message_history: list[dict] | None = None) -> str:
        task_lower = task_description.lower()

        for keyword in self.TIER2_TRIGGERS:
            if keyword in task_lower:
                return "tier2"

        for keyword in self.TIER1_TRIGGERS:
            if keyword in task_lower:
                return "tier1"

        if message_history:
            total_chars = sum(len(m.get("content", "")) for m in message_history)
            estimated_tokens = total_chars // 3
            if estimated_tokens > 8000:
                return "tier1"

        return "tier1"
