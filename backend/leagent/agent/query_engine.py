"""Session-scoped owner of the query loop.

``QueryEngine`` owns one :class:`ContextManager` per session. Each
``submit_message`` call delegates context assembly to
``context_manager.prepare_turn()`` and streams back SDK-shaped messages.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, AsyncIterator
from uuid import UUID, uuid4

from leagent.agent.deps import QueryDeps, production_deps
from leagent.tools.code.artifact import CodeArtifactRegistry
from leagent.tools.code.pipeline import _CONTEXT_REGISTRY_KEY
from leagent.agent.query import (
    AssistantMessage,
    QueryParams,
    ToolResultMessage,
    query,
)
from leagent.agent.tool_use_context import ToolUseContext
from leagent.agent.transitions import Terminal, TerminalReason
from leagent.context import ContextManager, FileState
from leagent.prompts import PromptBuilder, get_prompt_builder
from leagent.services.session.artifacts import (
    ArtifactRegistrar,
    attachment_dicts,
    strip_inline_base64_payloads,
)

if TYPE_CHECKING:
    from leagent.agent.hooks import HookManager
    from leagent.config.settings import ContextSettings
    from leagent.context import TurnContext
    from leagent.llm import LLMService
    from leagent.memory import AgentMemory
    from leagent.memory.agent_memory import RecallHandle
    from leagent.memory.working_scratchpad import WorkingScratchpad
    from leagent.prompts.types import BuiltPrompt
    from leagent.services.session import SessionManager
    from leagent.skills.manager import SkillsManager
    from leagent.tools.base import ToolPermissionContext
    from leagent.tools.executor import ToolExecutor
    from leagent.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# SDK message wrappers
# ---------------------------------------------------------------------------


@dataclass
class SDKMessage:
    type: str
    data: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class QueryEngineConfig:
    cwd: str = "."
    llm: "LLMService | None" = None
    tools: "ToolRegistry | None" = None
    executor: "ToolExecutor | None" = None
    agent_memory: "AgentMemory | None" = None
    hooks: "HookManager | None" = None
    deps: QueryDeps | None = None

    system_prompt: str = ""
    append_system_prompt: str = ""
    tools_deny_patterns: list[str] = field(default_factory=list)

    max_turns: int = 15
    max_tool_calls_per_turn: int = 10
    temperature: float | None = 0.1
    max_output_tokens: int | None = 4096
    model_tier: str = "tier1"
    model_provider: str | None = None
    model_name: str | None = None

    initial_messages: list[dict[str, Any]] = field(default_factory=list)
    abort_event: asyncio.Event | None = None

    session_id: UUID | None = None
    user_id: UUID | None = None
    agent_id: str = "default"

    tool_extra: dict[str, Any] = field(default_factory=dict)

    prompt_variant: str = "default_agent"
    prompt_template_variant: str = "default"
    prompt_builder: "PromptBuilder | None" = None
    session_manager: "SessionManager | None" = None
    working_scratchpad: "WorkingScratchpad | None" = None
    permission_context: "ToolPermissionContext | None" = None
    skills_manager: "SkillsManager | None" = None

    context_settings: "ContextSettings | None" = None

    context_manager: ContextManager | None = None
    file_state: FileState | None = None

    #: Optional async tap on every :class:`SDKMessage` from nested engines
    #: (e.g. coding sub-agent). Default ``None`` — chat layer may set for SSE.
    nested_sdk_consumer: Callable[[SDKMessage], Awaitable[None]] | None = None


# ---------------------------------------------------------------------------
# QueryEngine
# ---------------------------------------------------------------------------


class QueryEngine:
    """One conversation's worth of state and turn orchestration."""

    def __init__(self, config: QueryEngineConfig) -> None:
        self.config = config
        self.mutable_messages: list[dict[str, Any]] = list(config.initial_messages or [])
        self.abort_event: asyncio.Event = config.abort_event or asyncio.Event()
        self.total_usage: dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        self.permission_denials: list[dict[str, Any]] = []
        self.discovered_skill_names: set[str] = set()
        self.session_id: UUID = config.session_id or uuid4()
        self._deps: QueryDeps = config.deps or production_deps(config.llm)
        self._prompt_builder: PromptBuilder = (
            config.prompt_builder or get_prompt_builder()
        )
        self._last_built_prompt: "BuiltPrompt | None" = None
        self._artifact_registrar = ArtifactRegistrar(config.session_manager)
        self._ingested_produced_paths: set[str] = set()

        self._context: ContextManager = config.context_manager or ContextManager(
            cwd=config.cwd,
            settings=config.context_settings,
            tools=config.tools,
            permission_context=config.permission_context,
            skills_manager=config.skills_manager,
            agent_memory=config.agent_memory,
            session_manager=config.session_manager,
            working_scratchpad=config.working_scratchpad,
            prompt_registry=self._prompt_builder.registry,
            session_id=self.session_id,
            user_id=config.user_id,
            agent_id=config.agent_id,
            variant=config.prompt_variant,
            template_variant=config.prompt_template_variant,
            file_state=config.file_state,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def abort(self) -> None:
        self.abort_event.set()

    def reset(self) -> None:
        self.mutable_messages.clear()

    async def submit_message(
        self,
        prompt: str | dict[str, Any],
        *,
        uuid: UUID | None = None,
        is_meta: bool = False,
        append_user_turn: bool = True,
    ) -> AsyncIterator[SDKMessage]:
        self.discovered_skill_names.clear()
        turn_uuid = uuid or uuid4()

        if append_user_turn:
            user_msg = self._to_user_message(prompt, is_meta=is_meta)
            self.mutable_messages.append(user_msg)
            query_text = user_msg.get("content") if isinstance(user_msg.get("content"), str) else ""
        else:
            query_text = (
                prompt
                if isinstance(prompt, str)
                else str((prompt or {}).get("content") or "")
            ) or "Continue after the tool results above."

        prior_msgs = (
            self.mutable_messages[:-1] if append_user_turn else list(self.mutable_messages)
        )
        recall_anchor_text = ""
        for i in range(len(prior_msgs) - 1, -1, -1):
            m = prior_msgs[i]
            if m.get("role") != "user":
                continue
            c = m.get("content")
            if isinstance(c, str) and c.strip():
                recall_anchor_text = c.strip()
                break

        query_stripped = (query_text or "").strip()
        recall_handle: "RecallHandle | None" = None
        if self.config.agent_memory is not None and (query_stripped or recall_anchor_text):
            from leagent.memory.agent_memory import RecallHandle
            recall_handle = RecallHandle(self.config.agent_memory)
            recall_handle.start(
                query_stripped,
                recall_anchor=recall_anchor_text if not query_stripped else None,
                user_id=self.config.user_id,
                session_id=self.session_id,
                file_state=self._context.file_state,
            )

        # Surface the active code-project root (if any) to context
        # sources so prompt layers like project_memory and a small
        # active-project notice can render the path. Falls back
        # silently when ``tool_extra`` is empty.
        _project_roots_extra = self.config.tool_extra.get("project_roots")
        _project_roots_for_turn: list[str] = []
        if isinstance(_project_roots_extra, list):
            _project_roots_for_turn = [
                str(p) for p in _project_roots_extra if p
            ]

        append_base = self.config.append_system_prompt or ""
        append_extra_turn = append_base
        if self.config.skills_manager is not None:
            from leagent.skills.referenced_bundle import (
                build_referenced_skills_append_extra,
                iter_skill_ids_from_message,
                resolve_skill_by_token,
            )

            forced = build_referenced_skills_append_extra(
                query_text or "",
                self.config.skills_manager,
            )
            if forced:
                append_extra_turn = (
                    f"{append_base}\n\n{forced}" if append_base.strip() else forced
                )
            for sid in iter_skill_ids_from_message(query_text or ""):
                sk = resolve_skill_by_token(self.config.skills_manager, sid)
                if sk is not None:
                    self.discovered_skill_names.add(sk.name)

        from leagent.utils.cjk_font_discovery import build_cjk_generation_turn_extra

        cjk_generation_extra = build_cjk_generation_turn_extra(tools=self.config.tools)
        if cjk_generation_extra:
            append_extra_turn = (
                f"{append_extra_turn}\n\n{cjk_generation_extra}"
                if append_extra_turn.strip()
                else cjk_generation_extra
            )

        turn = await self._context.prepare_turn(
            query_text or "",
            task_id=turn_uuid,
            persona_override=self.config.system_prompt or "",
            append_extra=append_extra_turn,
            template_vars={},
            recall_handle=recall_handle,
            project_roots=_project_roots_for_turn,
        )

        self._last_built_prompt = turn.built_prompt
        system_prompt = turn.built_prompt.system_text

        messages_for_query = list(turn.attachment_messages) + list(self.mutable_messages)

        _tool_extra = dict(self.config.tool_extra)
        if _CONTEXT_REGISTRY_KEY not in _tool_extra:
            _tool_extra[_CONTEXT_REGISTRY_KEY] = CodeArtifactRegistry()
        if self.config.hooks is not None:
            _tool_extra["hooks"] = self.config.hooks

        tool_use_context = ToolUseContext(
            abort_event=self.abort_event,
            tools=self.config.tools,
            executor=self.config.executor,
            file_state_cache=self._context.file_state,
            recall_handle=recall_handle,
            hooks=self.config.hooks,
            session_id=self.session_id,
            user_id=self.config.user_id,
            task_id=turn_uuid,
            agent_id=self.config.agent_id,
            extra=_tool_extra,
        )

        tools_schema = (
            self.config.tools.get_tools_for_llm(
                deny_patterns=self.config.tools_deny_patterns or None,
                provider_format="openai",
            )
            if self.config.tools is not None
            else []
        )

        yield SDKMessage(
            type="system_init",
            data={
                "session_id": str(self.session_id),
                "turn_id": str(turn_uuid),
                "model_tier": self.config.model_tier,
                "model_provider": self.config.model_provider,
                "model_name": self.config.model_name,
                "tools": [t.get("function", {}).get("name") for t in tools_schema],
                "cwd": self.config.cwd,
                "prompt_fingerprint": turn.built_prompt.stable_hash,
            },
        )

        params = QueryParams(
            messages=messages_for_query,
            system_prompt=system_prompt,
            tools_schema=tools_schema or None,
            tool_use_context=tool_use_context,
            deps=self._deps,
            max_turns=self.config.max_turns,
            max_tool_calls_per_turn=self.config.max_tool_calls_per_turn,
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_output_tokens,
            model_tier=self.config.model_tier,
            model_provider=self.config.model_provider,
            model_name=self.config.model_name,
        )

        from leagent_core.telemetry.otel import get_tracer

        tracer = get_tracer("leagent.agent.query_engine")
        started = time.perf_counter()
        status = "success"
        with tracer.start_as_current_span("agent.query_turn") as span:
            if hasattr(span, "set_attribute"):
                span.set_attribute("agent.session_id", str(self.session_id))
                span.set_attribute("agent.turn_id", str(turn_uuid))
                span.set_attribute("agent.model_tier", self.config.model_tier)
                if self.config.model_provider:
                    span.set_attribute("agent.model_provider", self.config.model_provider)
                if self.config.model_name:
                    span.set_attribute("agent.model_name", self.config.model_name)
                span.set_attribute("agent.tools_count", len(tools_schema or []))
            try:
                async for item in query(params):
                    async for mapped in self._map_item(item):
                        yield mapped
            except Exception:
                status = "error"
                raise
            finally:
                if recall_handle is not None:
                    recall_handle.cancel()
                usage = tool_use_context.query_tracking.get("usage", {})
                self._accumulate_usage(usage)
                if hasattr(span, "set_attribute"):
                    span.set_attribute(
                        "agent.prompt_tokens",
                        int(usage.get("prompt_tokens", 0) or 0),
                    )
                    span.set_attribute(
                        "agent.completion_tokens",
                        int(usage.get("completion_tokens", 0) or 0),
                    )
                    span.set_attribute(
                        "agent.total_tokens",
                        int(usage.get("total_tokens", 0) or 0),
                    )
                try:
                    from leagent.utils.metrics import get_metrics

                    get_metrics().record_agent_task(
                        "chat_turn",
                        time.perf_counter() - started,
                        status,
                    )
                except Exception:  # noqa: BLE001
                    logger.debug("agent_prometheus_metrics_failed")
                # Episodic rows are written once per user turn by AgentController._record_episode
                # (after submit_message returns). Recording here too duplicated identical episodes.

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _map_item(self, item: Any) -> AsyncIterator[SDKMessage]:
        from leagent.agent.deps import ModelStreamEvent

        if isinstance(item, ModelStreamEvent):
            if item.content_delta:
                yield SDKMessage(
                    type="stream_delta",
                    data={"content": item.content_delta},
                )
            if item.reasoning_delta:
                yield SDKMessage(
                    type="stream_delta",
                    data={"reasoning_delta": item.reasoning_delta},
                )
            if item.tool_call_delta:
                yield SDKMessage(
                    type="tool_call_delta",
                    data=item.tool_call_delta,
                )
            return

        if isinstance(item, AssistantMessage):
            amo = item.to_openai()
            self.mutable_messages.append(amo)
            if item.tool_calls:
                yield SDKMessage(
                    type="assistant_tools",
                    data={
                        "content": amo.get("content") or "",
                        "tool_calls": amo.get("tool_calls"),
                        "model": item.model,
                        "usage": item.usage,
                        "reasoning_content": item.reasoning_content or "",
                    },
                )
                for tc in item.tool_calls:
                    yield SDKMessage(
                        type="tool_use",
                        data={
                            "id": tc.get("id"),
                            "name": tc.get("name"),
                            "input": tc.get("arguments", {}),
                        },
                    )
            else:
                yield SDKMessage(
                    type="assistant",
                    data={
                        "content": item.content,
                        "model": item.model,
                        "usage": item.usage,
                        "reasoning_content": item.reasoning_content or "",
                    },
                )
            return

        if isinstance(item, ToolResultMessage):
            attachments_msg = await self._register_workspace_attachments(item)
            self.mutable_messages.append(item.to_openai())
            self._track_artifact_error(item)
            if attachments_msg is not None:
                yield attachments_msg
            yield SDKMessage(
                type="tool_result",
                data={
                    "tool_use_id": item.tool_call_id,
                    "name": item.name,
                    "success": item.success,
                    "content": item.content[:2000],
                    "envelope": item.envelope,
                },
            )
            return

        if isinstance(item, Terminal):
            if item.reason == TerminalReason.AWAITING_USER_INPUT:
                tc = (item.meta or {}).get("tool_call") or {}
                tid = tc.get("id")
                if isinstance(tid, str) and tid.strip():
                    self.mutable_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tid.strip(),
                            "content": '{"_wa_pending": true}',
                        },
                    )
            tdata: dict[str, Any] = {
                "reason": item.reason.value,
                "session_id": str(self.session_id),
                "usage": dict(self.total_usage),
            }
            if item.reason == TerminalReason.COMPLETED:
                tdata["error"] = None
            elif item.reason == TerminalReason.AWAITING_USER_INPUT:
                tdata["error"] = None
                tdata["meta"] = item.meta
            else:
                tdata["error"] = item.meta.get("error")
                tdata["meta"] = item.meta
            yield SDKMessage(type="result", data=tdata)
            return

    def _to_user_message(self, prompt: str | dict[str, Any], *, is_meta: bool) -> dict[str, Any]:
        if isinstance(prompt, str):
            msg: dict[str, Any] = {"role": "user", "content": prompt}
        else:
            msg = {"role": "user", **prompt}
            msg.setdefault("content", "")
        if is_meta:
            msg.setdefault("metadata", {})["meta"] = True
        return msg

    def _accumulate_usage(self, usage: dict[str, Any]) -> None:
        for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
            self.total_usage[k] = self.total_usage.get(k, 0) + int(usage.get(k, 0) or 0)

    def _track_artifact_error(self, item: ToolResultMessage) -> None:
        """Feed artifact success/failure into the context manager's tracker."""
        tracker = self._context.artifact_tracker
        error_text = ""
        if not item.success:
            env = item.envelope
            if isinstance(env, dict):
                error_text = str(env.get("error") or "")
            if not error_text:
                error_text = item.content[:500] if item.content else "Unknown error"
        canvas_id = ""
        env = item.envelope
        if isinstance(env, dict):
            data = env.get("data")
            if isinstance(data, dict):
                canvas_id = str(data.get("canvas_id") or "")
        tracker.record_from_tool_result(
            tool_name=item.name,
            tool_call_id=item.tool_call_id,
            success=item.success,
            error_text=error_text,
            canvas_id=canvas_id,
        )

    async def _register_workspace_attachments(
        self,
        item: ToolResultMessage,
    ) -> SDKMessage | None:
        """Register tool-produced files and expose managed attachment payloads."""

        if not item.success:
            return None
        env = item.envelope if isinstance(item.envelope, dict) else {}
        registered = await self._artifact_registrar.register_tool_result(
            session_id=self.session_id,
            user_id=self.config.user_id,
            data=env.get("data"),
            metadata=dict(env.get("metadata") or {}),
            seen_paths=self._ingested_produced_paths,
        )
        attachments = attachment_dicts(registered)
        if not attachments:
            return None
        self._augment_tool_result_with_managed_artifacts(item, attachments)
        return SDKMessage(
            type="workspace_attachments",
            data={
                "session_id": str(self.session_id),
                "attachments": attachments,
                "paths": [item.path for item in registered],
            },
        )

    @staticmethod
    def _augment_tool_result_with_managed_artifacts(
        item: ToolResultMessage,
        attachments: list[dict[str, Any]],
    ) -> None:
        """Write managed preview URLs back into the tool result seen by the LLM."""

        if not attachments:
            return
        env = item.envelope if isinstance(item.envelope, dict) else {}
        data = env.get("data")
        if not isinstance(data, dict):
            data = {}
        data = strip_inline_base64_payloads(data)
        data["managed_artifacts"] = attachments
        env["data"] = data
        item.envelope = env

        try:
            parsed = json.loads(item.content) if item.content.strip().startswith("{") else {}
        except json.JSONDecodeError:
            parsed = {}
        if not isinstance(parsed, dict):
            parsed = {}
        parsed = strip_inline_base64_payloads(parsed)
        parsed["managed_artifacts"] = attachments
        item.content = json.dumps(parsed, ensure_ascii=False, default=str)

    # ------------------------------------------------------------------
    # Subagent forking
    # ------------------------------------------------------------------

    def fork(
        self,
        *,
        system_prompt: str | None = None,
        tools: "ToolRegistry | None" = None,
        prompt_variant: str | None = None,
        executor: "ToolExecutor | None" = None,
    ) -> QueryEngine:
        child_cfg = QueryEngineConfig(
            cwd=self.config.cwd,
            llm=self.config.llm,
            tools=tools or self.config.tools,
            executor=executor if executor is not None else self.config.executor,
            agent_memory=self.config.agent_memory,
            hooks=self.config.hooks,
            deps=self._deps,
            system_prompt=system_prompt or self.config.system_prompt,
            append_system_prompt=self.config.append_system_prompt,
            tools_deny_patterns=list(self.config.tools_deny_patterns),
            max_turns=self.config.max_turns,
            max_tool_calls_per_turn=self.config.max_tool_calls_per_turn,
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_output_tokens,
            model_tier=self.config.model_tier,
            model_provider=self.config.model_provider,
            model_name=self.config.model_name,
            session_id=self.session_id,
            user_id=self.config.user_id,
            agent_id=f"{self.config.agent_id}/fork",
            prompt_variant=prompt_variant or self.config.prompt_variant,
            prompt_template_variant=self.config.prompt_template_variant,
            prompt_builder=self._prompt_builder,
            session_manager=self.config.session_manager,
            working_scratchpad=self.config.working_scratchpad,
            permission_context=self.config.permission_context,
            context_manager=self._context.clone(),
            nested_sdk_consumer=self.config.nested_sdk_consumer,
        )
        return QueryEngine(child_cfg)
