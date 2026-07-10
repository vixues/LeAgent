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
from collections import OrderedDict
from collections.abc import AsyncIterator  # noqa: TC003
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4  # noqa: TC003

import structlog

from leagent.agent.base import (
    AgentConfig,
    AgentContext,
    AgentResponse,
    AgentState,
    ConversationContext,
    ConversationMessage,
    ExecutionStep,
    NoOpStreamHandler,
    QueuedStreamHandler,
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
from leagent.file.attachment_context import build_tool_extra_for_attachment_paths
from leagent.services.session.artifacts import (
    ArtifactRegistrar,
    attachment_dicts,
    coerce_tool_result_data,
    extract_produced_path_candidates,
)
from leagent.tools.base import ToolPermissionContext
from leagent.tools.context import build_tool_context

if TYPE_CHECKING:
    from leagent.agent.hooks import HookManager
    from leagent.agent.planner import TaskPlanner
    from leagent.llm import LLMService
    from leagent.memory import AgentMemory
    from leagent.runtime import AgentDefinition
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
        executor: ToolExecutor,
        *,
        planner: TaskPlanner | None = None,
        agent_memory: AgentMemory | None = None,
        session_manager: SessionManager | None = None,
        workflow_engine: WorkflowEngine | None = None,
        hook_manager: HookManager | None = None,
        config: AgentConfig | None = None,
        permission_context: ToolPermissionContext | None = None,
        checkpoint_store: Any = None,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.agent_memory = agent_memory
        self.session_manager = session_manager
        self.planner = planner  # Dormant: Plan-Execute path not wired; reserved for future kernel integration.
        self.executor = executor
        self.workflow_engine = workflow_engine
        self.config = config or AgentConfig()
        self._hooks = hook_manager
        self._permission_context = permission_context or ToolPermissionContext()
        self._abort_event = asyncio.Event()
        self._ingested_produced_paths: set[str] = set()
        # Last durable checkpoint id stamped by the kernel on a turn pause
        # (awaiting_user_input); linked into resumable_state so the chat
        # "continue" path can prefer a durable resume.
        self._last_checkpoint_id: str | None = None
        # Memory-formation gate for the current turn, driven by the active
        # AgentDefinition's MemoryPolicy.formation (set per turn).
        self._memory_formation_enabled = True

        # Unified runtime: AgentController is a thin HTTP/session
        # orchestration shell over AgentRuntime. The runtime owns engine
        # materialisation from a declarative AgentDefinition.
        from leagent.runtime import AgentRuntime, RuntimeContext

        self._runtime_context = RuntimeContext(
            llm=llm,
            tools=tools,
            executor=executor,
            agent_memory=agent_memory,
            session_manager=session_manager,
            hook_manager=hook_manager,
            permission_context=self._permission_context,
            checkpoint_store=checkpoint_store,
        )
        self._runtime = AgentRuntime(self._runtime_context)

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
        execution_run_id: str | None = None,
        runtime_profile: str | None = None,
    ) -> AgentResponse:
        """Execute the agent for a user request.

        ``project_roots`` is the optional code-project binding for this
        turn. When set, every absolute path is folded into
        ``ToolContext.extra['project_roots']`` so the path sandbox and
        the ``project_*`` / ``coding_agent`` tools accept it without
        widening any global env.

        ``authorized_roots`` lists session-scoped directory grants from
        ``POST …/authorized-paths`` (same sandbox semantics as project roots).

        ``runtime_profile`` selects long-running budgets for coding work
        (``coding_long`` / ``coding_extended``). When omitted but
        ``project_roots`` is set, ``coding_long`` is applied.

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
                    self._tag_user_message_image_paths(
                        conversation, attachments,
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
                    execution_run_id=execution_run_id,
                    runtime_profile=runtime_profile,
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
            response = context.to_response(error=str(e))
            response.terminal_reason = "error"
            await handler.on_complete(response)
            if self._hooks:
                await self._hooks.dispatch_error(context, e)
            return response
        except Exception as e:
            logger.exception("agent_unexpected_error", task_id=str(context.task_id))
            response = context.to_response(error=str(e))
            response.terminal_reason = "error"
            await handler.on_complete(response)
            if self._hooks:
                await self._hooks.dispatch_error(context, e)
            return response
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
        execution_run_id: str | None = None,
        runtime_profile: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Execute agent with streaming events."""
        queue_maxsize = 512
        try:
            from leagent.config.settings import get_settings as _gs

            queue_maxsize = max(1, int(_gs().agent.stream_queue_maxsize))
        except Exception:  # noqa: BLE001
            pass
        queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue(maxsize=queue_maxsize)

        async def _put_stream_event(event: StreamEvent | None) -> None:
            await queue.put(event)
            try:
                from leagent.utils.metrics import get_metrics

                get_metrics().record_stream_queue_depth("agent_stream", queue.qsize())
            except Exception:
                logger.debug("stream_queue_metrics_failed", exc_info=True)

        stream_handler = QueuedStreamHandler(
            session_id=session_id,
            put_event=_put_stream_event,
        )

        async def run_agent() -> None:
            try:
                await self.run(
                    user_input,
                    session_id,
                    user_id=user_id,
                    attachments=attachments,
                    project_roots=project_roots,
                    authorized_roots=authorized_roots,
                    stream_handler=stream_handler,
                    skip_append_user=skip_append_user,
                    persisted_user_message_id=persisted_user_message_id,
                    agent_task_id=agent_task_id,
                    execution_run_id=execution_run_id,
                    runtime_profile=runtime_profile,
                )
            except Exception as exc:
                logger.exception(
                    "run_stream_background_failed",
                    session_id=str(session_id),
                )
                await stream_handler.on_error(exc)

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
                except TimeoutError:
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
    # Helpers
    # ------------------------------------------------------------------

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

    async def _playbook_ids_for_session(self, session_id: UUID) -> list[str]:
        """Collect playbook ids from chat message extensions in the session."""
        import json

        from leagent.prompts.playbooks import playbook_ids_from_message_extensions

        if self.session_manager is None:
            return []
        try:
            state = await self.session_manager.load(session_id)
        except Exception as exc:  # noqa: BLE001
            logger.debug("playbook_ids_session_load_failed", error=str(exc))
            return []
        if state is None:
            return []

        ordered: list[str] = []
        seen: set[str] = set()
        for message in state.messages:
            raw_ext = getattr(message, "extensions", None)
            if not raw_ext:
                continue
            try:
                ext = json.loads(raw_ext) if isinstance(raw_ext, str) else raw_ext
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(ext, dict):
                continue
            for pid in playbook_ids_from_message_extensions(ext):
                if pid not in seen:
                    seen.add(pid)
                    ordered.append(pid)
        return ordered

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

                # Content-based ID reuse: match by (role, content) so that
                # stub injection / trim index shifts do not cause historical
                # messages to receive new UUIDs (which then leak as duplicate
                # rows in the messages table).
                from collections import defaultdict

                _content_id_map: dict[tuple[str, str], list[UUID]] = defaultdict(list)
                for pm in previous:
                    _content_id_map[(pm.role, pm.content)].append(pm.id)

                session_messages: list[SessionMessage] = []
                for i, msg in enumerate(conversation.messages):
                    msg_id: UUID | None = None
                    role_str = str(msg.role)
                    content_str = str(msg.content or "")

                    if (
                        persisted_uid is not None
                        and append_idx is not None
                        and i == append_idx
                        and role_str == "user"
                    ):
                        msg_id = persisted_uid

                    if msg_id is None:
                        key = (role_str, content_str)
                        candidates = _content_id_map.get(key)
                        if candidates:
                            msg_id = candidates.pop(0)

                    if msg_id is None and i < len(previous) and previous[i].role == role_str:
                        msg_id = previous[i].id

                    session_messages.append(
                        SessionMessage(
                            id=msg_id or uuid4(),
                            role=role_str,
                            content=content_str,
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
        context: AgentContext,
        conversation: ConversationContext,
    ) -> None:
        """Persist a lightweight snapshot so the user can resume with 'continue'."""
        try:
            from leagent.db import get_database_service

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
                # Link the durable SDK checkpoint (if any) so the continue
                # path can prefer a full-history resume over the partial blob.
                "checkpoint_id": self._last_checkpoint_id,
            }

            db = get_database_service()
            async with db.session() as session:
                from leagent.db.models.message import ChatSession
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
    def _tag_user_message_image_paths(
        conversation: ConversationContext,
        attachments: list[str] | None,
    ) -> None:
        """Record image attachment paths on the last user message for multi-turn vision."""
        if not attachments or not conversation.messages:
            return
        try:
            from leagent.agent.content_parts import is_image_path

            image_paths = [
                p for p in attachments
                if isinstance(p, str) and p and is_image_path(p)
            ]
            if image_paths:
                conversation.messages[-1].attachment_paths = image_paths
        except Exception:  # noqa: BLE001 - tagging is best-effort
            logger.debug("user_message_image_tag_failed", exc_info=True)

    def _openai_seed_messages_from_conversation(
        self,
        conversation: ConversationContext,
        *,
        skip_user_trim: bool,
    ) -> list[dict[str, Any]]:
        # Capability-aware multi-turn vision: rebuild inline image blocks for
        # recent user turns the active model can see, strip them otherwise. The
        # image-path marker stays internal to this builder (popped by rebuild)
        # so it never reaches a provider.
        msgs: list[dict[str, Any]] = []
        for m in conversation.messages:
            if m.role not in ("user", "assistant", "tool"):
                continue
            oai = m.to_openai_format()
            if m.role == "user" and m.attachment_paths:
                from leagent.agent.content_parts import ATTACHMENT_IMAGE_PATHS_KEY

                oai[ATTACHMENT_IMAGE_PATHS_KEY] = list(m.attachment_paths)
            msgs.append(oai)
        try:
            from leagent.agent.content_parts import rebuild_vision_history
            from leagent.agent.multimodal import model_supports_image_input

            catalog = getattr(self.llm, "model_registry", None)
            supports_image = model_supports_image_input(
                provider=self.config.model_provider,
                model=self.config.model_name,
                catalog=catalog,
            )
            msgs = rebuild_vision_history(msgs, supports_image=supports_image)
        except Exception as exc:  # noqa: BLE001 - vision rebuild is best-effort
            logger.debug("vision_history_rebuild_failed", error=str(exc))
        if skip_user_trim or not msgs:
            return msgs
        if msgs[-1].get("role") == "user":
            return msgs[:-1]
        return msgs

    def _per_turn_definition(self, deny_patterns: list[str]) -> AgentDefinition:
        """Derive the per-turn :class:`AgentDefinition` from controller config.

        Starts from the registered base definition for the active
        ``prompt_variant`` and overlays the dynamic, request-scoped values
        the controller owns (model routing, deny patterns, memory toggle,
        turn budget).
        """
        base = self._runtime.resolve(
            getattr(self.config, "prompt_variant", "default_agent") or "default_agent"
        )
        self._memory_formation_enabled = bool(
            base.memory.formation and self.config.enable_memory
        )
        return base.with_overrides(
            model=base.model.model_copy(
                update={
                    "provider": self.config.model_provider,
                    "model": self.config.model_name,
                    "temperature": self.config.temperature,
                }
            ),
            tools=base.tools.model_copy(update={"deny": list(deny_patterns)}),
            memory=base.memory.model_copy(update={"enabled": self.config.enable_memory}),
            max_turns=self.config.max_iterations,
            max_tool_calls_per_turn=self.config.max_tool_calls_per_turn,
        )

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
        execution_run_id: str | None = None,
        runtime_profile: str | None = None,
    ) -> AgentResponse:
        """Delegate the think-act loop to the new ``QueryEngine``.

        This is now the default execution path. The controller keeps
        hooks, permissions, workflow matching, and conversation
        persistence around the engine so every existing consumer
        (API/WebSocket/CLI) observes the same ``StreamHandler`` events
        and ``AgentResponse`` shape it did before.
        """
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

        profile_for_turn = (runtime_profile or "").strip() or None
        if not profile_for_turn and tool_extra.get("project_roots"):
            profile_for_turn = "coding_long"
        if profile_for_turn:
            from leagent.agent.runtime_profile import runtime_budget_tool_extra

            tool_extra.update(runtime_budget_tool_extra(profile_for_turn))

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

        if execution_run_id:
            tool_extra["run_id"] = execution_run_id

        session_playbook_ids = await self._playbook_ids_for_session(context.session_id)
        if session_playbook_ids:
            existing = list(tool_extra.get("playbook_ids") or [])
            for pid in session_playbook_ids:
                if pid not in existing:
                    existing.append(pid)
            tool_extra["playbook_ids"] = existing

        if self.session_manager is not None:
            try:
                session_todos = await self.session_manager.get_todos(context.session_id)
                if session_todos:
                    tool_extra["todos"] = self.session_manager.todos_as_tool_dicts(
                        session_todos
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("session_todos_load_failed", error=str(exc))

        # Set the skills manager on the shared runtime context (lazy import
        # to avoid an import cycle at module load).
        from leagent.skills.manager import get_skills_manager

        self._runtime_context.skills_manager = get_skills_manager()

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

        # Materialise the engine from a declarative AgentDefinition via the
        # unified runtime. The controller no longer hand-builds QueryEngine.
        definition = self._per_turn_definition(tools_deny_patterns)
        engine = self._runtime.build_engine(
            definition,
            session_id=context.session_id,
            user_id=context.user_id,
            cwd=engine_cwd,
            tool_extra=tool_extra,
            abort_event=self._abort_event,
            initial_messages=self._openai_seed_messages_from_conversation(
                conversation,
                skip_user_trim=skip_user_append,
            ),
            append_system_prompt=append_extra,
        )

        AgentController._update_task_phase(
            context.session_id, context.task_id, "llm",
        )
        streaming_phase_marked = False

        response_text = ""
        reasoning_acc = ""

        formatted_attachments = normalized_attachments if normalized_attachments else attachments
        query_input = self._format_user_message(
            user_input,
            formatted_attachments,
            authorized_roots=authorized_roots,
        )
        try:
            from leagent.agent.multimodal import prepare_user_message_with_attachments

            catalog = getattr(self.llm, "model_registry", None)
            query_input = prepare_user_message_with_attachments(
                query_input,
                merged_attachments,
                provider=self.config.model_provider,
                model=self.config.model_name,
                catalog=catalog,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("multimodal_message_build_failed", error=str(exc))
        resume_hint = "Continue after the tool results above."
        turn_message_start = len(conversation.messages)

        # Single think-act path: drive the SDK kernel run loop instead of
        # consuming ``engine.submit_message`` directly. ``AgentEvent`` shares
        # the exact ``{type, data}`` shape of the former ``SDKMessage`` so the
        # StreamHandler mapping (and therefore the SSE wire contract) is
        # unchanged, while chat now gains a ``RunState`` + turn-pause
        # checkpointing and single-site tool hooks.
        from leagent.sdk.kernel.loop import run_loop
        from leagent.sdk.kernel.state import RunState

        run_state = RunState(
            session_id=str(context.session_id or ""),
            agent_name=definition.name,
        )
        async for event in run_loop(
            engine,
            resume_hint if skip_user_append else query_input,
            run_state=run_state,
            checkpoint_store=self._runtime.checkpoint_store,
            hooks=self._hooks,
            hook_context=context,
            append_user_turn=not skip_user_append,
        ):
            if context.is_cancelled or self._abort_event.is_set():
                engine.abort()
                break

            mtype = event.type
            data = event.data

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
                # ``on_tool_call`` / ``on_tool_result`` hooks are dispatched
                # from the single kernel site (see ``run_loop``); the controller
                # only drives the SSE handler + step bookkeeping here.
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
            elif mtype == "steer":
                # Mid-turn user steer injected at a tool-batch boundary:
                # persist it in the conversation as a regular user message.
                steer_text = str(data.get("content") or "")
                if steer_text:
                    conversation.append_user_message(steer_text)
            elif mtype == "result":
                reason = str(data.get("reason", "completed"))
                checkpoint_id = data.get("checkpoint_id")
                usage = data.get("usage", {}) or {}
                if reason == TerminalReason.AWAITING_USER_INPUT.value:
                    meta = data.get("meta") or {}
                    tool_call = meta.get("tool_call") or {}
                    questions = meta.get("questions") or []
                    self._last_checkpoint_id = checkpoint_id
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
                            "checkpoint_id": checkpoint_id,
                        },
                    )
                    _tid = str(tool_call.get("id") or "").strip()
                    if _tid:
                        conversation.append_tool_result(
                            _tid,
                            str(tool_call.get("name") or ASK_USER_TOOL_NAME),
                            ASK_USER_PENDING_TOOL_JSON,
                        )
                    response = context.finalize_turn(
                        text=response_text,
                        reason=reason,
                        conversation=conversation,
                        turn_message_start=turn_message_start,
                        usage=usage,
                        checkpoint_id=checkpoint_id,
                        partial=True,
                        metadata={
                            "awaiting_user_input": True,
                            "tool_call": tool_call,
                            "questions": questions,
                            "assistant_tool_calls": last_tcs,
                            "checkpoint_id": checkpoint_id,
                        },
                    )
                    await handler.on_complete(response)
                    return response

                response = context.finalize_turn(
                    text=response_text,
                    reason=reason,
                    conversation=conversation,
                    turn_message_start=turn_message_start,
                    error=data.get("error"),
                    usage=usage,
                    checkpoint_id=checkpoint_id,
                )
                await handler.on_complete(response)
                return response

        response = context.finalize_turn(
            text=response_text,
            reason=TerminalReason.COMPLETED.value,
            conversation=conversation,
            turn_message_start=turn_message_start,
        )
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
        from leagent.file.primitives import is_path_inside

        try:
            resolved = path.expanduser().resolve()
            return is_path_inside(resolved, (root,))
        except OSError:
            return False

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
        if not self._memory_formation_enabled:
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
            art_run: dict[str, Any] = {}
            for step in context.steps:
                if step.type == StepType.TOOL_CALL and step.tool_call:
                    tool_names.append(step.tool_call.name)
                if step.type == StepType.TOOL_RESULT and step.tool_result:
                    if step.tool_result.success:
                        tool_successes += 1
                    else:
                        tool_failures += 1
                    # Capture the latest scored art-workflow run so procedural
                    # memory records its quality_score / refine count / graph
                    # digest — production feedback the planner can recall.
                    extracted = self._extract_art_run(step.tool_result)
                    if extracted:
                        art_run = extracted

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
                extra={"art_run": art_run} if art_run else {},
            )
            await self.agent_memory.observe_turn(obs)
        except Exception as exc:  # noqa: BLE001
            logger.warning("episode_record_failed", error=str(exc))

    def _extract_art_run(self, tool_result: Any) -> dict[str, Any]:
        """Pull scored art-run telemetry from a workflow_run tool result."""
        try:
            data = self._coerce_tool_result_data(getattr(tool_result, "data", None))
        except Exception:  # noqa: BLE001
            return {}
        if not isinstance(data, dict):
            return {}
        outputs = data.get("outputs")
        if not isinstance(outputs, dict) or outputs.get("quality_score") is None:
            return {}
        run: dict[str, Any] = {}
        try:
            run["quality_score"] = float(outputs.get("quality_score"))
        except (TypeError, ValueError):
            return {}
        passed = outputs.get("quality_passed")
        if isinstance(passed, bool):
            run["quality_passed"] = passed
        for key in ("refine_iteration", "graph_digest", "graph_hash"):
            val = outputs.get(key)
            if val is not None:
                run[key] = val
        if data.get("execution_id"):
            run["execution_id"] = str(data["execution_id"])
        return run

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

