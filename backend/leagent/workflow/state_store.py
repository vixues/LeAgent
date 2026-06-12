"""Durable workflow state persistence (Codex RolloutRecorder analogue for DAG runs)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from leagent.workflow.base import WorkflowState, WorkflowStatus


@dataclass
class WorkflowRunSnapshot:
    """Serializable bundle for pause/resume."""

    state: WorkflowState
    output_cache: dict[str, Any]
    blocked_nodes: list[str]
    prompt_id: str | None = None
    execution_id: UUID | None = None

    def to_payload(self) -> str:
        return json.dumps(
            {
                "state": self.state.model_dump(mode="json"),
                "output_cache": self.output_cache,
                "blocked_nodes": self.blocked_nodes,
                "prompt_id": self.prompt_id,
                "execution_id": str(self.execution_id) if self.execution_id else None,
            },
            ensure_ascii=False,
            default=str,
        )

    @classmethod
    def from_payload(cls, raw: str) -> WorkflowRunSnapshot:
        data = json.loads(raw)
        state = WorkflowState.model_validate(data["state"])
        execution_id = data.get("execution_id")
        return cls(
            state=state,
            output_cache=dict(data.get("output_cache") or {}),
            blocked_nodes=list(data.get("blocked_nodes") or []),
            prompt_id=data.get("prompt_id"),
            execution_id=UUID(execution_id) if execution_id else None,
        )


class WorkflowStateStore(Protocol):
    async def save(self, snapshot: WorkflowRunSnapshot) -> None: ...

    async def load(self, state_id: UUID) -> WorkflowRunSnapshot | None: ...

    async def load_by_prompt_id(self, prompt_id: str) -> WorkflowRunSnapshot | None: ...

    async def delete(self, state_id: UUID) -> None: ...


class InMemoryWorkflowStateStore:
    """Non-durable store for tests and single-process deployments."""

    def __init__(self) -> None:
        self._by_state: dict[str, WorkflowRunSnapshot] = {}
        self._by_prompt: dict[str, str] = {}

    async def save(self, snapshot: WorkflowRunSnapshot) -> None:
        key = str(snapshot.state.id)
        self._by_state[key] = snapshot
        if snapshot.prompt_id:
            self._by_prompt[snapshot.prompt_id] = key

    async def load(self, state_id: UUID) -> WorkflowRunSnapshot | None:
        return self._by_state.get(str(state_id))

    async def load_by_prompt_id(self, prompt_id: str) -> WorkflowRunSnapshot | None:
        key = self._by_prompt.get(prompt_id)
        if key is None:
            return None
        return self._by_state.get(key)

    async def delete(self, state_id: UUID) -> None:
        snap = self._by_state.pop(str(state_id), None)
        if snap and snap.prompt_id:
            self._by_prompt.pop(snap.prompt_id, None)


class SQLWorkflowStateStore:
    """Database-backed workflow snapshot store."""

    def __init__(self, database_service: Any) -> None:
        self._db = database_service

    async def save(self, snapshot: WorkflowRunSnapshot) -> None:
        from sqlmodel import select

        from leagent.db.models.workflow_state_snapshot import WorkflowStateSnapshot

        payload = snapshot.to_payload()
        status = snapshot.state.status.value if isinstance(
            snapshot.state.status, WorkflowStatus
        ) else str(snapshot.state.status)
        async with self._db.session() as session:
            existing = await session.exec(
                select(WorkflowStateSnapshot).where(
                    WorkflowStateSnapshot.state_id == snapshot.state.id
                )
            )
            row = existing.first()
            if row is None:
                row = WorkflowStateSnapshot(
                    state_id=snapshot.state.id,
                    execution_id=snapshot.execution_id,
                    prompt_id=snapshot.prompt_id,
                    status=status,
                    payload=payload,
                )
            else:
                row.execution_id = snapshot.execution_id
                row.prompt_id = snapshot.prompt_id
                row.status = status
                row.payload = payload
            session.add(row)
            await session.flush()

    async def load(self, state_id: UUID) -> WorkflowRunSnapshot | None:
        from sqlmodel import select

        from leagent.db.models.workflow_state_snapshot import WorkflowStateSnapshot

        async with self._db.session() as session:
            result = await session.exec(
                select(WorkflowStateSnapshot).where(
                    WorkflowStateSnapshot.state_id == state_id
                )
            )
            row = result.first()
            if row is None:
                return None
            return WorkflowRunSnapshot.from_payload(row.payload)

    async def load_by_prompt_id(self, prompt_id: str) -> WorkflowRunSnapshot | None:
        from sqlmodel import select

        from leagent.db.models.workflow_state_snapshot import WorkflowStateSnapshot

        async with self._db.session() as session:
            result = await session.exec(
                select(WorkflowStateSnapshot).where(
                    WorkflowStateSnapshot.prompt_id == prompt_id
                )
            )
            row = result.first()
            if row is None:
                return None
            return WorkflowRunSnapshot.from_payload(row.payload)

    async def delete(self, state_id: UUID) -> None:
        from sqlmodel import select

        from leagent.db.models.workflow_state_snapshot import WorkflowStateSnapshot

        async with self._db.session() as session:
            result = await session.exec(
                select(WorkflowStateSnapshot).where(
                    WorkflowStateSnapshot.state_id == state_id
                )
            )
            row = result.first()
            if row is not None:
                await session.delete(row)
                await session.flush()


def build_workflow_state_store(database_service: Any | None) -> WorkflowStateStore:
    if database_service is not None:
        return SQLWorkflowStateStore(database_service)
    return InMemoryWorkflowStateStore()


__all__ = [
    "WorkflowRunSnapshot",
    "WorkflowStateStore",
    "InMemoryWorkflowStateStore",
    "SQLWorkflowStateStore",
    "build_workflow_state_store",
]
