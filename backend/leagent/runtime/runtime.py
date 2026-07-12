"""Unified Agent Runtime.

``AgentRuntime`` is the single, SDK-governed entry point for executing an
agent. It resolves a declarative :class:`AgentDefinition` (by name, instance,
or builder), materialises a concrete ``QueryEngineConfig`` from the definition
+ a :class:`RuntimeContext` + per-call session arguments, drives the
session-scoped :class:`~leagent.agent.query_engine.QueryEngine` loop, and
yields a unified :class:`AgentEvent` stream (or an aggregate
:class:`AgentResult`).

Every caller (chat API, background tasks, cron, CLI, workflow nodes,
sub-agent delegation) goes through this facade instead of hand-constructing
``QueryEngine``/``QueryEngineConfig``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from leagent.agent.runtime_profile import resolve_runtime_budget
from leagent.runtime.builder import AgentBuilder
from leagent.runtime.context import RuntimeContext
from leagent.runtime.definition import AgentDefinition
from leagent.sdk.events import AgentEvent, AgentEventType, AgentResult
from leagent.runtime.registry import AgentRegistry, get_agent_registry
from leagent.utils.logging import get_logger

if TYPE_CHECKING:
    import asyncio
    from collections.abc import AsyncIterator
    from uuid import UUID

    from leagent.agent.query_engine import QueryEngine, QueryEngineConfig
    from leagent.sdk.session import AgentSession
    from leagent.services.service_manager import ServiceManager
    from leagent.tools.registry import ToolRegistry

logger = get_logger(__name__)

AgentRef = "str | AgentDefinition | AgentBuilder"


class AgentRuntime:
    """Execute agents described by :class:`AgentDefinition`."""

    def __init__(
        self,
        ctx: RuntimeContext,
        *,
        registry: AgentRegistry | None = None,
        checkpoint_store: Any = None,
    ) -> None:
        self._ctx = ctx
        self._registry = registry or get_agent_registry()
        self._checkpoint_store = checkpoint_store

    @property
    def context(self) -> RuntimeContext:
        return self._ctx

    @property
    def registry(self) -> AgentRegistry:
        return self._registry

    @property
    def checkpoint_store(self) -> Any:
        """Pluggable checkpoint/session store (Codex RolloutRecorder analogue).

        Resolution order: explicit constructor arg → ``RuntimeContext`` →
        a lazily-created in-memory default so turn-pause checkpointing works
        out of the box. Swap in a DB/Redis-backed store for durable resume.
        """
        if self._checkpoint_store is None:
            self._checkpoint_store = getattr(self._ctx, "checkpoint_store", None)
        if self._checkpoint_store is None:
            from leagent.sdk.kernel.checkpoint import InMemoryCheckpointStore

            self._checkpoint_store = InMemoryCheckpointStore()
        return self._checkpoint_store

    @classmethod
    def from_service_manager(
        cls,
        sm: ServiceManager,
        *,
        registry: AgentRegistry | None = None,
        **ctx_kwargs: Any,
    ) -> AgentRuntime:
        ctx = RuntimeContext.from_service_manager(sm, **ctx_kwargs)
        return cls(ctx, registry=registry)

    # ------------------------------------------------------------------
    # Definition resolution
    # ------------------------------------------------------------------

    def resolve(self, agent: Any) -> AgentDefinition:
        """Resolve a name / definition / builder to an :class:`AgentDefinition`."""
        if isinstance(agent, AgentDefinition):
            return agent
        if isinstance(agent, AgentBuilder):
            return agent.build()
        if isinstance(agent, str):
            found = self._registry.try_get(agent)
            if found is not None:
                return found
            # Unknown name → fall back to a default-variant definition so the
            # runtime never hard-fails on an ad hoc agent id.
            logger.warning("agent_definition_fallback", agent=agent)
            return AgentDefinition(name=agent)
        raise TypeError(f"Cannot resolve agent reference of type {type(agent)!r}")

    # ------------------------------------------------------------------
    # Engine materialisation
    # ------------------------------------------------------------------

    def build_engine(
        self,
        agent: Any,
        *,
        session_id: UUID | None = None,
        user_id: UUID | None = None,
        cwd: str = ".",
        tool_extra: dict[str, Any] | None = None,
        abort_event: asyncio.Event | None = None,
        initial_messages: list[dict[str, Any]] | None = None,
        append_system_prompt: str = "",
        nested_sdk_consumer: Any = None,
        overrides: dict[str, Any] | None = None,
        context_manager: Any = None,
    ) -> QueryEngine:
        """Materialise a :class:`QueryEngine` for ``agent``."""
        from leagent.agent.query_engine import QueryEngine

        definition = self.resolve(agent)
        if overrides:
            definition = definition.with_overrides(**overrides)
        config = self._materialize_config(
            definition,
            session_id=session_id,
            user_id=user_id,
            cwd=cwd,
            tool_extra=tool_extra,
            abort_event=abort_event,
            initial_messages=initial_messages,
            append_system_prompt=append_system_prompt,
            nested_sdk_consumer=nested_sdk_consumer,
            context_manager=context_manager,
        )
        return QueryEngine(config)

    def _materialize_config(
        self,
        definition: AgentDefinition,
        *,
        session_id: UUID | None,
        user_id: UUID | None,
        cwd: str,
        tool_extra: dict[str, Any] | None,
        abort_event: asyncio.Event | None,
        initial_messages: list[dict[str, Any]] | None,
        append_system_prompt: str,
        nested_sdk_consumer: Any,
        context_manager: Any,
    ) -> QueryEngineConfig:
        from leagent.agent.query_engine import QueryEngineConfig

        ctx = self._ctx
        budget = resolve_runtime_budget(definition.runtime_profile)
        max_turns = definition.max_turns or budget.max_turns
        max_tcpt = definition.max_tool_calls_per_turn or budget.max_tool_calls_per_turn

        # Tool policy: allow-list builds a scoped registry + executor; deny-list
        # maps onto the per-turn deny patterns.
        tools_registry = ctx.tools
        executor = ctx.executor
        if definition.tools.allow and tools_registry is not None:
            tools_registry = tools_registry.scoped(
                allow=definition.tools.allow, match="glob", replace=True
            )
            from leagent.tools.executor import ToolExecutor

            executor = ToolExecutor(
                registry=tools_registry,
                service_manager=getattr(ctx.executor, "service_manager", None),
                permission_context=ctx.permission_context,
            )

        # Memory policy: a disabled memory policy detaches AgentMemory so no
        # recall is fetched for this agent's turns.
        agent_memory = ctx.agent_memory if definition.memory.enabled else None

        # Hook policy: if the definition declares hook names, narrow the shared
        # manager to that named subset (per-agent hook selection).
        hook_manager = ctx.hook_manager
        if definition.hooks and hook_manager is not None:
            hook_manager = hook_manager.filter_by_names(definition.hooks)

        merged_append = "\n\n".join(
            p for p in (definition.append_system_prompt, append_system_prompt) if p and p.strip()
        )

        config = QueryEngineConfig(
            cwd=cwd,
            llm=ctx.llm,
            tools=tools_registry,
            executor=executor,
            agent_memory=agent_memory,
            hooks=hook_manager,
            system_prompt=definition.system_prompt or "",
            append_system_prompt=merged_append,
            tools_deny_patterns=list(definition.tools.deny),
            tools_max_tools=definition.tools.max_tools or 25,
            max_turns=max_turns,
            max_tool_calls_per_turn=max_tcpt,
            temperature=definition.model.temperature,
            max_output_tokens=definition.model.max_output_tokens,
            model_provider=definition.model.provider,
            model_name=definition.model.model,
            model_task=definition.model.task,
            initial_messages=list(initial_messages or []),
            abort_event=abort_event,
            session_id=session_id,
            user_id=user_id,
            agent_id=definition.name,
            tool_extra=dict(tool_extra or {}),
            prompt_variant=definition.prompt_variant,
            prompt_template_variant=definition.prompt_template_variant,
            context_recipe=definition.resolved_recipe(),
            prompt_builder=ctx.prompt_builder,
            session_manager=ctx.session_manager,
            working_scratchpad=ctx.working_scratchpad,
            permission_context=ctx.permission_context,
            skills_manager=ctx.skills_manager,
            context_settings=ctx.context_settings,
            recall_limit=definition.memory.recall_limit if definition.memory.enabled else None,
            memory_formation=definition.memory.formation,
            context_manager=context_manager,
            nested_sdk_consumer=nested_sdk_consumer,
        )
        return config

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def stream(
        self,
        agent: Any,
        prompt: str | dict[str, Any],
        *,
        session_id: UUID | None = None,
        user_id: UUID | None = None,
        cwd: str = ".",
        tool_extra: dict[str, Any] | None = None,
        abort_event: asyncio.Event | None = None,
        initial_messages: list[dict[str, Any]] | None = None,
        append_system_prompt: str = "",
        nested_sdk_consumer: Any = None,
        overrides: dict[str, Any] | None = None,
        engine: QueryEngine | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Run an agent turn and yield unified :class:`AgentEvent` frames."""
        from leagent.telemetry.otel import get_tracer

        definition = self.resolve(agent) if engine is None else None
        tracer = get_tracer("leagent.runtime")
        with tracer.start_as_current_span("agent.runtime.stream") as span:
            if hasattr(span, "set_attribute"):
                span.set_attribute(
                    "agent.name", definition.name if definition else "engine"
                )
                if definition is not None:
                    span.set_attribute("agent.variant", definition.prompt_variant)
                    span.set_attribute("agent.runtime_profile", definition.runtime_profile)
                if session_id is not None:
                    span.set_attribute("agent.session_id", str(session_id))

            from leagent.runtime.execution_factory import (
                begin_execution,
                end_execution_unless_blocked,
            )
            from leagent.runtime.execution_run import ExecutionScope
            from leagent.sdk.kernel.loop import run_loop
            from leagent.sdk.kernel.state import RunState

            extra = dict(tool_extra or {})
            # Callers historically pass the parent run via tool_extra["run_id"].
            parent_run_id = extra.get("parent_run_id") or extra.get("run_id")
            experiment_id = extra.get("experiment_id")
            prompt_preview = prompt if isinstance(prompt, str) else None

            meta: dict[str, Any] = {
                "agent_name": definition.name if definition else "",
                "model": (
                    (definition.model.model or "")
                    if definition is not None
                    else ""
                ),
            }
            if experiment_id:
                meta["experiment_id"] = experiment_id
            if prompt_preview:
                meta["prompt"] = prompt_preview[:2000]
            if isinstance(extra.get("tags"), dict):
                meta["tags"] = extra["tags"]
            if overrides:
                ov_model = overrides.get("model")
                if ov_model is not None and getattr(ov_model, "model", None):
                    meta["model"] = str(ov_model.model)
                elif overrides.get("model_name"):
                    meta["model"] = str(overrides["model_name"])

            exec_run = begin_execution(
                scope=ExecutionScope.CHAT_TURN,
                session_id=str(session_id or "") or None,
                user_id=str(user_id or "") if user_id else None,
                parent_run_id=str(parent_run_id) if parent_run_id else None,
                metadata=meta,
            )
            extra["run_id"] = exec_run.run_id

            run_engine = engine or self.build_engine(
                definition,
                session_id=session_id,
                user_id=user_id,
                cwd=cwd,
                tool_extra=extra,
                abort_event=abort_event,
                initial_messages=initial_messages,
                append_system_prompt=append_system_prompt,
                nested_sdk_consumer=nested_sdk_consumer,
                overrides=overrides,
            )
            if engine is not None:
                try:
                    cfg_extra = getattr(run_engine.config, "tool_extra", None)
                    if isinstance(cfg_extra, dict):
                        cfg_extra["run_id"] = exec_run.run_id
                    else:
                        run_engine.config.tool_extra = dict(extra)
                except Exception:
                    logger.debug("tool_extra_run_id_patch_failed", exc_info=True)

            state = RunState(
                session_id=str(session_id or ""),
                agent_name=(definition.name if definition else getattr(run_engine.config, "agent_id", "") or ""),
            )
            try:
                async for event in run_loop(
                    run_engine,
                    prompt,
                    run_state=state,
                    checkpoint_store=self.checkpoint_store,
                ):
                    if hasattr(span, "set_attribute"):
                        span.set_attribute("agent.run_id", exec_run.run_id)
                        if exec_run.parent_run_id:
                            span.set_attribute("agent.parent_run_id", exec_run.parent_run_id)
                    yield event
            finally:
                end_execution_unless_blocked(exec_run.run_id)
    async def run(
        self,
        agent: Any,
        prompt: str | dict[str, Any],
        *,
        session_id: UUID | None = None,
        user_id: UUID | None = None,
        cwd: str = ".",
        tool_extra: dict[str, Any] | None = None,
        abort_event: asyncio.Event | None = None,
        initial_messages: list[dict[str, Any]] | None = None,
        append_system_prompt: str = "",
        overrides: dict[str, Any] | None = None,
        engine: QueryEngine | None = None,
        collect_events: bool = False,
    ) -> AgentResult:
        """Run an agent turn to completion and return an aggregate result."""
        text_parts: list[str] = []
        final_text = ""
        tool_calls = 0
        produced_files: list[str] = []
        result = AgentResult(session_id=str(session_id or ""))

        async for event in self.stream(
            agent,
            prompt,
            session_id=session_id,
            user_id=user_id,
            cwd=cwd,
            tool_extra=tool_extra,
            abort_event=abort_event,
            initial_messages=initial_messages,
            append_system_prompt=append_system_prompt,
            overrides=overrides,
            engine=engine,
        ):
            if collect_events:
                result.events.append(event)
            etype = event.type
            data = event.data or {}
            if etype == AgentEventType.STREAM_DELTA:
                delta = data.get("content")
                if delta:
                    text_parts.append(str(delta))
            elif etype == AgentEventType.ASSISTANT:
                final_text = str(data.get("content") or "")
            elif etype == AgentEventType.TOOL_USE:
                tool_calls += 1
            elif etype == AgentEventType.WORKSPACE_ATTACHMENTS:
                for path in data.get("paths") or []:
                    if path:
                        produced_files.append(str(path))
            elif etype == AgentEventType.RESULT:
                result.session_id = str(data.get("session_id") or result.session_id)
                result.reason = str(data.get("reason") or "completed")
                result.error = data.get("error")
                result.usage = dict(data.get("usage") or {})
                result.meta = dict(data.get("meta") or {})

        result.text = final_text or "".join(text_parts)
        result.tool_calls = tool_calls
        result.produced_files = produced_files
        return result

    # ------------------------------------------------------------------
    # Durable resume
    # ------------------------------------------------------------------

    async def resume(
        self,
        agent: Any,
        checkpoint_id: str,
        prompt: str | dict[str, Any],
        *,
        user_id: UUID | None = None,
        cwd: str = ".",
        tool_extra: dict[str, Any] | None = None,
        abort_event: asyncio.Event | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Resume a paused run from a persisted checkpoint and stream events.

        Loads the :class:`~leagent.sdk.protocols.Checkpoint` from the
        configured store (Codex ``RolloutRecorder`` / Claude ``SessionStore``
        analogue), rebuilds an engine seeded with the checkpoint's message
        history, then drives a fresh turn with ``prompt`` (e.g. the user's
        answer to an ``awaiting_user_input`` pause).
        """
        from uuid import UUID as _UUID

        store = self.checkpoint_store
        checkpoint = await store.load(checkpoint_id)
        if checkpoint is None:
            raise ValueError(f"checkpoint {checkpoint_id!r} not found")

        session_id: UUID | None = None
        if checkpoint.session_id:
            try:
                session_id = _UUID(checkpoint.session_id)
            except (ValueError, TypeError):
                session_id = None

        engine = self.build_engine(
            agent,
            session_id=session_id,
            user_id=user_id,
            cwd=cwd,
            tool_extra=tool_extra,
            abort_event=abort_event,
            initial_messages=list(checkpoint.messages or []),
            overrides=overrides,
        )
        async for event in self.stream(
            agent,
            prompt,
            engine=engine,
            session_id=session_id,
            user_id=user_id,
        ):
            yield event

    # ------------------------------------------------------------------
    # Session factory
    # ------------------------------------------------------------------

    def session(
        self,
        agent: Any,
        *,
        session_id: UUID | None = None,
        user_id: UUID | None = None,
        cwd: str = ".",
        tool_extra: dict[str, Any] | None = None,
        abort_event: asyncio.Event | None = None,
    ) -> AgentSession:
        """Create a stateful multi-turn :class:`AgentSession`."""
        from leagent.sdk.session import AgentSession

        return AgentSession(
            self,
            agent,
            session_id=session_id,
            user_id=user_id,
            cwd=cwd,
            tool_extra=tool_extra,
            abort_event=abort_event,
        )

    # ------------------------------------------------------------------
    # Sub-agent delegation
    # ------------------------------------------------------------------

    async def delegate(
        self,
        parent: Any,
        agent: Any,
        prompt: str,
        *,
        allowed_tools: Any = None,
        extra_denied_tools: Any = None,
        max_turns: int | None = None,
        tool_extra: dict[str, Any] | None = None,
        cwd: str | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        max_tool_calls_per_turn: int | None = None,
        system_prompt: str | None = None,
        inherit_abort: bool = True,
        nested_preview_emit: Any = None,
        parent_tool_call_id: str | None = None,
        log_event: str = "subagent_delegate",
        log_fields: dict[str, Any] | None = None,
        session_id_hint: Any = None,
        user_id_hint: Any = None,
    ) -> dict[str, Any]:
        """Run a definition-driven sub-agent forked off ``parent``.

        ``parent`` is an :class:`~leagent.agent.controller.AgentController`
        or :class:`~leagent.agent.query_engine.QueryEngine`. The resolved
        :class:`AgentDefinition` supplies the tool allow/deny policy, prompt
        variant, model controls, and turn budget; per-call arguments override
        them. The proven fork mechanics (child-scoped executor, abort bridge,
        nested-preview plumbing, file-state merge) live in
        :func:`leagent.agent.subagent._run_subagent_core`, which this method
        drives — so delegation is declarative without re-implementing the
        battle-tested fork core.

        Returns the flat sub-agent envelope (``text`` / ``success`` /
        ``steps_count`` / ``partial`` / ``error`` / ``activity`` / ...).
        """
        from leagent.agent.controller import AgentController
        from leagent.agent.query_engine import QueryEngine
        from leagent.agent.subagent import _run_subagent_core
        from leagent.telemetry.otel import get_tracer

        definition = self.resolve(agent)

        profile_override = (tool_extra or {}).get("runtime_profile")
        if profile_override:
            from leagent.agent.runtime_profile import normalize_runtime_profile

            definition = definition.with_overrides(
                runtime_profile=normalize_runtime_profile(profile_override),
            )

        if allowed_tools is not None:
            allow: list[str] | None = [str(t) for t in allowed_tools]
        else:
            allow = list(definition.tools.allow) or None

        denied: list[str] = list(definition.tools.deny)
        if extra_denied_tools:
            for name in extra_denied_tools:
                if name and name not in denied:
                    denied.append(str(name))

        budget = resolve_runtime_budget(definition.runtime_profile)
        if profile_override:
            eff_max_turns = max_turns or budget.max_turns
            eff_max_tool_calls = (
                max_tool_calls_per_turn
                if max_tool_calls_per_turn is not None
                else budget.max_tool_calls_per_turn
            )
        else:
            eff_max_turns = max_turns or definition.max_turns or budget.max_turns
            eff_max_tool_calls = max_tool_calls_per_turn

        parent_controller: AgentController | None = None
        parent_engine: QueryEngine | None = None
        if isinstance(parent, QueryEngine):
            parent_engine = parent
        elif isinstance(parent, AgentController):
            parent_controller = parent
        else:
            raise TypeError(
                "AgentRuntime.delegate expects an AgentController or QueryEngine, "
                f"got {type(parent).__name__}"
            )

        tracer = get_tracer("leagent.runtime")
        with tracer.start_as_current_span("agent.runtime.delegate") as span:
            if hasattr(span, "set_attribute"):
                span.set_attribute("agent.name", definition.name)
                span.set_attribute("agent.variant", definition.prompt_variant)
                span.set_attribute("agent.max_turns", int(eff_max_turns))
                span.set_attribute(
                    "agent.parent",
                    "engine" if parent_engine is not None else "controller",
                )
            return await _run_subagent_core(
                parent_controller=parent_controller,
                parent_engine=parent_engine,
                prompt=prompt,
                prompt_variant=definition.prompt_variant,
                allowed_tools=allow,
                denied_tools=denied or None,
                system_prompt=system_prompt or (definition.system_prompt or None),
                max_turns=eff_max_turns,
                tool_extra=tool_extra,
                temperature=(
                    temperature if temperature is not None else definition.model.temperature
                ),
                max_output_tokens=(
                    max_output_tokens
                    if max_output_tokens is not None
                    else definition.model.max_output_tokens
                ),
                max_tool_calls_per_turn=(
                    eff_max_tool_calls
                    if eff_max_tool_calls is not None
                    else definition.max_tool_calls_per_turn
                ),
                # Definition fidelity: the child runs under its own context
                # recipe, model routing, and memory policy rather than
                # inheriting the parent's.
                context_recipe=definition.resolved_recipe(),
                model_task=definition.model.task,
                model_provider=definition.model.provider,
                model_name=definition.model.model,
                memory_enabled=definition.memory.enabled,
                recall_limit=(
                    definition.memory.recall_limit
                    if definition.memory.enabled
                    else None
                ),
                memory_formation=definition.memory.formation,
                tools_max_tools=definition.tools.max_tools,
                cwd=cwd,
                inherit_abort=inherit_abort,
                log_event=log_event,
                log_fields=log_fields,
                nested_preview_emit=nested_preview_emit,
                parent_tool_call_id=parent_tool_call_id,
                session_id_hint=session_id_hint,
                user_id_hint=user_id_hint,
            )


_DELEGATION_RUNTIME: AgentRuntime | None = None


def get_delegation_runtime() -> AgentRuntime:
    """Return a process-wide runtime for definition-driven sub-agent delegation.

    Delegation forks the *parent* engine/controller for its services, so the
    runtime only needs the agent registry (an empty :class:`RuntimeContext` is
    sufficient). This lets sub-agent tools resolve their tool/model/budget
    policy from the registry without each carrying a fully-wired context.
    """
    global _DELEGATION_RUNTIME
    if _DELEGATION_RUNTIME is None:
        _DELEGATION_RUNTIME = AgentRuntime(RuntimeContext())
    return _DELEGATION_RUNTIME


__all__ = ["AgentRuntime", "AgentRef", "get_delegation_runtime"]
