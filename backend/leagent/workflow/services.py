"""Database-backed :class:`WorkflowService`.

Preserves the legacy API used across the codebase
(``service_manager``, cron executor, chat integration) — ``run``,
``list_executions``, ``cancel_execution``, ``pause_execution``,
``resume_execution`` — and adds queue-aware primitives (``enqueue``,
``get_by_prompt_id``, ``cancel/pause/resume(prompt_id)``,
``queue_position``) consumed by the new ``/workflow`` router.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, TYPE_CHECKING
from uuid import UUID, uuid4

import structlog

from leagent.workflow.base import WorkflowResult, WorkflowStatus

from .prompt_map import InMemoryPromptMap, PromptExecutionMap
from .registry import FlowWorkflowRegistry

if TYPE_CHECKING:
    from leagent.db.service import DatabaseService

    from .engine.executor import WorkflowExecutor
    from .queue.base import PromptItem, PromptQueue

logger = structlog.get_logger(__name__)


class WorkflowService:
    """Orchestrates flow loading, queuing, execution, and persistence."""

    def __init__(
        self,
        db: "DatabaseService",
        executor: "WorkflowExecutor",
        registry: FlowWorkflowRegistry,
        queue: "PromptQueue | None" = None,
        prompt_map: "PromptExecutionMap | None" = None,
    ) -> None:
        self._db = db
        self._executor = executor
        self._registry = registry
        self._queue = queue
        # ``prompt_map`` replaces the old per-process ``dict[str, UUID]`` so
        # multi-worker / multi-node deployments share the hot-path lookup.
        self._prompt_to_execution: PromptExecutionMap = prompt_map or InMemoryPromptMap()

    # ------------------------------------------------------------------
    # Queue-based API (new)
    # ------------------------------------------------------------------

    async def enqueue(
        self,
        *,
        prompt_id: str,
        flow_id: UUID,
        user_id: UUID,
        inputs: dict[str, Any],
        trigger_type: str = "manual",
        priority: int = 5,
        extra_data: dict[str, Any] | None = None,
    ) -> Any:
        """Persist a ``pending`` execution row and enqueue the job."""
        from leagent.db.models.workflow_execution import WorkflowExecution

        execution_id = uuid4()
        async with self._db.session() as session:
            from sqlmodel import select

            dup = await session.exec(
                select(WorkflowExecution).where(
                    WorkflowExecution.prompt_id == prompt_id,
                    WorkflowExecution.user_id == user_id,
                    WorkflowExecution.status.in_(("queued", "running")),  # type: ignore[arg-type]
                )
            )
            if (existing := dup.first()) is not None:
                return await self._fetch_execution_record(existing.id)

            record = WorkflowExecution(
                id=execution_id,
                flow_id=flow_id,
                user_id=user_id,
                prompt_id=prompt_id,
                priority=priority,
                status="queued",
                trigger_type=trigger_type,
                inputs=json.dumps(inputs or {}),
            )
            session.add(record)
            await session.flush()

        await self._prompt_to_execution.set(prompt_id, execution_id)

        if self._queue is not None:
            from .queue.base import PromptItem
            item = PromptItem.new(
                prompt_id=prompt_id,
                flow_id=str(flow_id),
                user_id=str(user_id),
                inputs=inputs or {},
                trigger_type=trigger_type,
                priority=priority,
                extra_data=extra_data or {},
            )
            await self._queue.put(item)
        else:
            # No external queue → run in-process without blocking the HTTP handler.
            asyncio.create_task(
                self._run_enqueued_inline(
                    prompt_id=prompt_id,
                    flow_id=flow_id,
                    user_id=user_id,
                    inputs=inputs,
                    trigger_type=trigger_type,
                    execution_id=execution_id,
                    extra_data=extra_data,
                )
            )
        return await self._fetch_execution_record(execution_id)

    async def queue_position(self, prompt_id: str) -> int | None:
        if self._queue is None:
            return None
        return await self._queue.queue_position(prompt_id)

    async def get_by_prompt_id(self, prompt_id: str) -> dict[str, Any] | None:
        from sqlmodel import select
        from leagent.db.models.workflow_execution import WorkflowExecution

        async with self._db.session() as session:
            result = await session.exec(
                select(WorkflowExecution).where(WorkflowExecution.prompt_id == prompt_id)
            )
            record = result.first()
            if not record:
                return None
            return self._record_to_dict(record)

    async def cancel(self, prompt_id: str) -> bool:
        eid = await self._prompt_to_execution.get(prompt_id)
        if eid is None:
            record = await self.get_by_prompt_id(prompt_id)
            if record is None:
                return False
            eid = UUID(record["id"])
        return await self.cancel_execution(eid)

    async def pause(self, prompt_id: str) -> bool:
        eid = await self._prompt_to_execution.get(prompt_id)
        if eid is None:
            record = await self.get_by_prompt_id(prompt_id)
            if record is None:
                return False
            eid = UUID(record["id"])
        return await self.pause_execution(eid)

    async def resume(
        self,
        prompt_id: str,
        *,
        resume_data: dict[str, Any] | None = None,
    ) -> WorkflowResult | None:
        record = await self.get_by_prompt_id(prompt_id)
        if record is None:
            return None
        eid = UUID(record["id"])
        flow_id = UUID(record["flow_id"]) if record.get("flow_id") else None
        if flow_id is None:
            return None
        return await self.resume_execution(eid, flow_id, resume_data)

    # ------------------------------------------------------------------
    # Unified start API
    # ------------------------------------------------------------------

    async def start(
        self,
        flow_id: UUID,
        user_id: UUID,
        inputs: dict[str, Any] | None = None,
        *,
        trigger_type: str = "manual",
        cron_job_id: UUID | None = None,
        extra_data: dict[str, Any] | None = None,
        priority: int = 5,
    ) -> WorkflowResult:
        """Single entry point for workflow runs (API, cron, agent tools, chat steps)."""
        if trigger_type in ("manual", "agent", "cron") and extra_data is None:
            return await self.run(
                flow_id,
                user_id,
                inputs=inputs,
                trigger_type=trigger_type,
                cron_job_id=cron_job_id,
            )
        prompt_id = str(uuid4())
        await self.enqueue(
            prompt_id=prompt_id,
            flow_id=flow_id,
            user_id=user_id,
            inputs=inputs or {},
            trigger_type=trigger_type,
            priority=priority,
            extra_data=extra_data,
        )
        record = await self.get_by_prompt_id(prompt_id)
        if record is None:
            raise RuntimeError("Failed to create workflow execution record")
        eid = UUID(record["id"])
        return await self._execute_inline(
            prompt_id,
            flow_id,
            user_id,
            inputs or {},
            trigger_type,
            eid,
            extra_data=extra_data,
        )

    async def run_compiled_document(
        self,
        document: Any,
        *,
        user_id: UUID,
        session_id: str,
        inputs: dict[str, Any] | None = None,
        outputs_to_execute: list[str] | None = None,
        trigger_type: str = "chat_step",
        parent_run_id: str | None = None,
        extra_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute an inline compiled document (chat playbook steps).

        Returns ``{prompt_id, run_id, result}`` for WebSocket subscription and
        execution-plane correlation.
        """
        from leagent.db.models.workflow_execution import WorkflowExecution
        from leagent.runtime.execution_factory import (
            begin_execution,
            end_execution,
            end_execution_unless_blocked,
        )
        from leagent.runtime.execution_run import ExecutionScope

        execution_id = uuid4()
        prompt_id = f"chat-step-{uuid4().hex[:16]}"
        started_at = datetime.utcnow()
        merged_extra = {
            "session_id": session_id,
            "user_id": str(user_id),
            **(extra_data or {}),
        }

        async with self._db.session() as session:
            record = WorkflowExecution(
                id=execution_id,
                flow_id=None,
                user_id=user_id,
                prompt_id=prompt_id,
                status="running",
                trigger_type=trigger_type,
                inputs=json.dumps(inputs or {}),
                started_at=started_at,
            )
            session.add(record)
            await session.flush()

        await self._prompt_to_execution.set(prompt_id, execution_id)

        exec_run = begin_execution(
            scope=ExecutionScope.WORKFLOW,
            session_id=session_id,
            user_id=str(user_id),
            parent_run_id=parent_run_id,
            prompt_id=prompt_id,
            workflow_execution_id=execution_id,
        )

        try:
            result = await self._execute_inline_document(
                prompt_id,
                document,
                user_id,
                inputs or {},
                trigger_type,
                execution_id,
                merged_extra,
                outputs_to_execute=outputs_to_execute,
            )
        except Exception:
            end_execution(exec_run.run_id)
            raise

        blocked_statuses = {WorkflowStatus.PAUSED, WorkflowStatus.WAITING_HUMAN}
        if result.status in blocked_statuses or exec_run.is_blocked:
            end_execution_unless_blocked(exec_run.run_id)
        else:
            end_execution(exec_run.run_id)
        return {
            "prompt_id": prompt_id,
            "run_id": exec_run.run_id,
            "result": result,
        }

    # ------------------------------------------------------------------
    # Legacy API (preserved)
    # ------------------------------------------------------------------

    async def run(
        self,
        flow_id: UUID,
        user_id: UUID,
        inputs: dict[str, Any] | None = None,
        trigger_type: str = "manual",
        cron_job_id: UUID | None = None,
    ) -> WorkflowResult:
        from leagent.db.models.workflow_execution import WorkflowExecution

        execution_id = uuid4()
        prompt_id = str(uuid4())
        started_at = datetime.utcnow()

        async with self._db.session() as session:
            record = WorkflowExecution(
                id=execution_id,
                flow_id=flow_id,
                user_id=user_id,
                cron_job_id=cron_job_id,
                prompt_id=prompt_id,
                status="running",
                trigger_type=trigger_type,
                inputs=json.dumps(inputs or {}),
                started_at=started_at,
            )
            session.add(record)
            await session.flush()

        await self._prompt_to_execution.set(prompt_id, execution_id)
        return await self._execute_inline(
            prompt_id, flow_id, user_id, inputs or {}, trigger_type,
            execution_id, extra_data=None,
        )

    async def get_execution(self, execution_id: UUID) -> dict[str, Any] | None:
        from leagent.db.models.workflow_execution import WorkflowExecution
        async with self._db.session() as session:
            record = await session.get(WorkflowExecution, execution_id)
            if not record:
                return None
            return self._record_to_dict(record)

    async def list_executions(
        self,
        flow_id: UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        from sqlmodel import col, select
        from leagent.db.models.workflow_execution import WorkflowExecution

        async with self._db.session() as session:
            q = (
                select(WorkflowExecution)
                .where(WorkflowExecution.flow_id == flow_id)
                .order_by(col(WorkflowExecution.created_at).desc())
                .offset(offset)
                .limit(limit)
            )
            result = await session.exec(q)
            return [self._record_to_dict(r) for r in result.all()]

    async def cancel_execution(self, execution_id: UUID) -> bool:
        from leagent.db.models.workflow_execution import WorkflowExecution
        async with self._db.session() as session:
            record = await session.get(WorkflowExecution, execution_id)
            if not record or record.status not in ("queued", "running", "pending", "paused", "waiting_human"):
                return False
        if record.workflow_state_id:
            await self._executor.cancel(record.workflow_state_id)
        await self._update_execution(execution_id, status="cancelled")
        return True

    async def pause_execution(self, execution_id: UUID) -> bool:
        from leagent.db.models.workflow_execution import WorkflowExecution
        async with self._db.session() as session:
            record = await session.get(WorkflowExecution, execution_id)
            if not record or record.status != "running":
                return False
        if record.workflow_state_id:
            await self._executor.pause(record.workflow_state_id)
        await self._update_execution(execution_id, status="paused")
        return True

    async def resume_execution(
        self,
        execution_id: UUID,
        flow_id: UUID,
        resume_data: dict[str, Any] | None = None,
    ) -> WorkflowResult | None:
        from leagent.db.models.workflow_execution import WorkflowExecution
        async with self._db.session() as session:
            record = await session.get(WorkflowExecution, execution_id)
            if not record or record.status not in ("paused", "waiting_human"):
                return None
        if not record.workflow_state_id:
            return None
        doc = await self._registry.get(str(flow_id))
        if not doc:
            return None
        result = await self._executor.resume(
            doc, record.workflow_state_id, resume_data,
            prompt_id=record.prompt_id,
        )
        await self._update_execution(
            execution_id,
            status=result.status.value,
            outputs=result.outputs,
            error="; ".join(result.errors) if result.errors else None,
            completed_at=datetime.utcnow(),
            duration_ms=result.duration_ms,
        )
        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _run_enqueued_inline(
        self,
        *,
        prompt_id: str,
        flow_id: UUID,
        user_id: UUID,
        inputs: dict[str, Any],
        trigger_type: str,
        execution_id: UUID,
        extra_data: dict[str, Any] | None,
    ) -> None:
        try:
            await self._execute_inline(
                prompt_id,
                flow_id,
                user_id,
                inputs,
                trigger_type,
                execution_id,
                extra_data,
            )
        except Exception:
            logger.exception(
                "workflow_enqueued_inline_failed",
                execution_id=str(execution_id),
                prompt_id=prompt_id,
            )

    async def _execute_inline(
        self,
        prompt_id: str,
        flow_id: UUID,
        user_id: UUID,
        inputs: dict[str, Any],
        trigger_type: str,
        execution_id: UUID,
        extra_data: dict[str, Any] | None,
    ) -> WorkflowResult:
        doc = await self._registry.get(str(flow_id))
        if not doc:
            await self._update_execution(execution_id, status="failed",
                                          error=f"Flow {flow_id} not found or has no definition")
            raise ValueError(f"Flow {flow_id} not found or has no parseable definition")

        started_at = datetime.utcnow()
        await self._update_execution(execution_id, status="running", started_at=started_at)

        try:
            result = await self._executor.execute_async(
                doc, inputs, prompt_id=prompt_id,
                extra_data={"user_id": str(user_id), **(extra_data or {})},
            )
        except Exception as exc:
            await self._update_execution(execution_id, status="failed", error=str(exc))
            raise

        await self._update_execution(
            execution_id,
            status=result.status.value,
            outputs=result.outputs,
            execution_history=[r.model_dump() for r in result.execution_history],
            error="; ".join(result.errors) if result.errors else None,
            completed_at=datetime.utcnow(),
            duration_ms=result.duration_ms,
            node_count=len(result.execution_history),
            workflow_state_id=result.state_id,
        )
        return result

    async def _execute_inline_document(
        self,
        prompt_id: str,
        document: Any,
        user_id: UUID,
        inputs: dict[str, Any],
        trigger_type: str,
        execution_id: UUID,
        extra_data: dict[str, Any] | None,
        *,
        outputs_to_execute: list[str] | None = None,
    ) -> WorkflowResult:
        """Run a pre-loaded document without registry lookup."""
        started_at = datetime.utcnow()
        await self._update_execution(execution_id, status="running", started_at=started_at)

        try:
            result = await self._executor.execute_async(
                document,
                inputs,
                prompt_id=prompt_id,
                extra_data={"user_id": str(user_id), **(extra_data or {})},
                outputs_to_execute=outputs_to_execute,
            )
        except Exception as exc:
            await self._update_execution(execution_id, status="failed", error=str(exc))
            raise

        await self._update_execution(
            execution_id,
            status=result.status.value,
            outputs=result.outputs,
            execution_history=[r.model_dump() for r in result.execution_history],
            error="; ".join(result.errors) if result.errors else None,
            completed_at=datetime.utcnow(),
            duration_ms=result.duration_ms,
            node_count=len(result.execution_history),
            workflow_state_id=result.state_id,
        )
        return result

    async def _fetch_execution_record(self, execution_id: UUID) -> Any:
        from leagent.db.models.workflow_execution import WorkflowExecution
        async with self._db.session() as session:
            return await session.get(WorkflowExecution, execution_id)

    async def _update_execution(
        self,
        execution_id: UUID,
        status: str | None = None,
        outputs: dict[str, Any] | None = None,
        execution_history: list[dict[str, Any]] | None = None,
        error: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        duration_ms: int | None = None,
        node_count: int | None = None,
        workflow_state_id: UUID | None = None,
        graph_hash: str | None = None,
    ) -> None:
        from leagent.db.models.workflow_execution import WorkflowExecution
        async with self._db.session() as session:
            record = await session.get(WorkflowExecution, execution_id)
            if not record:
                return
            if status:
                record.status = status
            if outputs is not None:
                record.outputs = json.dumps(outputs)
            if execution_history is not None:
                record.execution_history = json.dumps(execution_history)
            if error is not None:
                record.error = error
            if started_at:
                record.started_at = started_at
            if completed_at:
                record.completed_at = completed_at
            if duration_ms is not None:
                record.duration_ms = duration_ms
            if node_count is not None:
                record.node_count = node_count
            if workflow_state_id is not None:
                record.workflow_state_id = workflow_state_id
            if graph_hash is not None:
                record.graph_hash = graph_hash
            record.updated_at = datetime.utcnow()
            session.add(record)
            await session.flush()

    async def update_execution_by_prompt_id(
        self,
        *,
        prompt_id: str,
        status: str,
        outputs: dict[str, Any] | None = None,
        error: str | None = None,
        duration_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Update execution row by prompt id (used by queue workers)."""
        from sqlmodel import select
        from leagent.db.models.workflow_execution import WorkflowExecution

        async with self._db.session() as session:
            result = await session.exec(
                select(WorkflowExecution).where(WorkflowExecution.prompt_id == prompt_id)
            )
            record = result.first()
            if record is None:
                return

            record.status = status
            if status == "running" and record.started_at is None:
                record.started_at = datetime.utcnow()
            if status in {"completed", "failed", "cancelled", "timeout"}:
                record.completed_at = datetime.utcnow()
            if outputs is not None:
                record.outputs = json.dumps(outputs)
            if error is not None:
                record.error = error
            if duration_ms is not None:
                record.duration_ms = duration_ms
            if metadata is not None:
                history = list(json.loads(record.execution_history) if record.execution_history else [])
                history.append({"status": status, "metadata": metadata, "duration_ms": duration_ms or 0})
                record.execution_history = json.dumps(history)
                record.node_count = max(record.node_count or 0, len(history))
            record.updated_at = datetime.utcnow()
            session.add(record)
            await session.flush()

    def _record_to_dict(self, record: Any) -> dict[str, Any]:
        return {
            "id": str(record.id),
            "flow_id": str(record.flow_id) if record.flow_id else None,
            "user_id": str(record.user_id) if record.user_id else None,
            "cron_job_id": str(record.cron_job_id) if record.cron_job_id else None,
            "prompt_id": record.prompt_id,
            "graph_hash": record.graph_hash,
            "priority": record.priority,
            "status": record.status,
            "trigger_type": record.trigger_type,
            "inputs": json.loads(record.inputs) if record.inputs else {},
            "outputs": json.loads(record.outputs) if record.outputs else {},
            "execution_history": json.loads(record.execution_history) if record.execution_history else [],
            "current_node": record.current_node,
            "node_count": record.node_count,
            "error": record.error,
            "started_at": record.started_at.isoformat() if record.started_at else None,
            "completed_at": record.completed_at.isoformat() if record.completed_at else None,
            "duration_ms": record.duration_ms,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }
