"""Flow CRUD and execution history routes for the workflow server.

These endpoints replace the legacy ``/api/v1/flows`` module. They live at
``/api/v1/workflow/flows`` and ``/api/v1/workflow/executions`` and share the
same :class:`APIRouter` as the engine-level ``/prompts`` routes so the whole
workflow feature lives behind a single prefix.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any, Optional
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import col, func, select

from leagent.schema.api import PaginatedResponse
from leagent.services.auth import CurrentUserId
from leagent.services.database import DatabaseService, get_database_service
from leagent.services.database.models import (
    Flow,
    FlowRead,
    FlowStatus,
    FlowType,
)

from ..io.authoring import to_canonical
from .schemas import (
    FlowDuplicateResponse,
    WorkflowExecutionDetail,
    WorkflowExecutionSummary,
)


def _canonicalize(data: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Best-effort conversion of incoming flow data to the canonical shape.

    The frontend may send visual-editor style documents (flat ``nodes`` list,
    ``edges`` list). The engine only accepts canonical documents, so we convert
    on write. If the payload is already canonical, :func:`to_canonical` returns
    a copy unchanged. If it looks like unrelated free-form data we leave it be.
    """
    if not isinstance(data, dict):
        return data
    try:
        return to_canonical(data)
    except Exception:
        return data

logger = structlog.get_logger(__name__)

flows_router = APIRouter(tags=["workflow-flows"])


# ---------------------------------------------------------------------------
# Request models (kept compact; mirrors the legacy schema one-to-one)
# ---------------------------------------------------------------------------


class FlowCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    icon: Optional[str] = Field(default="🤖", max_length=50)
    icon_bg_color: Optional[str] = Field(default=None, max_length=20)
    status: FlowStatus = Field(default=FlowStatus.DRAFT)
    flow_type: FlowType = Field(default=FlowType.AGENT)
    is_public: bool = Field(default=False)
    tags: Optional[str] = Field(default=None, max_length=500)
    data: Optional[dict[str, Any]] = None
    settings: Optional[dict[str, Any]] = None
    folder_id: Optional[UUID] = None


class FlowUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    icon: Optional[str] = Field(default=None, max_length=50)
    icon_bg_color: Optional[str] = Field(default=None, max_length=20)
    status: Optional[FlowStatus] = None
    flow_type: Optional[FlowType] = None
    is_public: Optional[bool] = None
    tags: Optional[str] = Field(default=None, max_length=500)
    data: Optional[dict[str, Any]] = None
    settings: Optional[dict[str, Any]] = None
    folder_id: Optional[UUID] = None


class RecentFlowItem(BaseModel):
    id: str
    name: str
    description: Optional[str]
    status: str
    nodeCount: int
    createdAt: str
    updatedAt: str


class WorkflowExecutionListResponse(BaseModel):
    executions: list[WorkflowExecutionSummary]
    total: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_workflow_service() -> Any:
    from leagent.services.service_manager import get_service_manager

    sm = get_service_manager()
    if sm.workflow_service is None:
        raise HTTPException(status_code=503, detail="Workflow service unavailable")
    return sm.workflow_service


def _node_count(flow: Flow) -> int:
    if not flow.data:
        return 0
    try:
        doc = json.loads(flow.data)
        nodes = doc.get("nodes") if isinstance(doc, dict) else None
        if isinstance(nodes, dict):
            return len(nodes)
        if isinstance(nodes, list):
            return len(nodes)
    except Exception:
        return 0
    return 0


# ---------------------------------------------------------------------------
# Flow CRUD
# ---------------------------------------------------------------------------


@flows_router.post(
    "/flows",
    response_model=FlowRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_flow(
    data: FlowCreateRequest,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> FlowRead:
    async with db.session() as session:
        canonical = _canonicalize(data.data)
        flow = Flow(
            name=data.name,
            description=data.description,
            icon=data.icon,
            icon_bg_color=data.icon_bg_color,
            status=data.status,
            flow_type=data.flow_type,
            is_public=data.is_public,
            tags=data.tags,
            data=json.dumps(canonical) if canonical else None,
            settings=json.dumps(data.settings) if data.settings else None,
            folder_id=data.folder_id,
            user_id=user_id,
        )
        session.add(flow)
        await session.flush()
        await session.refresh(flow)
        return FlowRead.model_validate(flow)


@flows_router.get("/flows", response_model=PaginatedResponse[FlowRead])
async def list_flows(
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_: Optional[FlowStatus] = Query(default=None, alias="status"),
    flow_type: Optional[FlowType] = Query(default=None),
    folder_id: Optional[UUID] = Query(default=None),
    is_public: Optional[bool] = Query(default=None),
    search: Optional[str] = Query(default=None, max_length=100),
) -> PaginatedResponse[FlowRead]:
    async with db.session() as session:
        query = select(Flow).where(
            (Flow.user_id == user_id) | (Flow.is_public == True),  # noqa: E712
            Flow.is_deleted == False,  # noqa: E712
        )
        if status_ is not None:
            query = query.where(Flow.status == status_)
        if flow_type is not None:
            query = query.where(Flow.flow_type == flow_type)
        if folder_id is not None:
            query = query.where(Flow.folder_id == folder_id)
        if is_public is not None:
            query = query.where(Flow.is_public == is_public)
        if search:
            query = query.where(
                (Flow.name.ilike(f"%{search}%"))
                | (Flow.description.ilike(f"%{search}%"))
            )

        count_query = select(func.count()).select_from(query.subquery())
        total = (await session.exec(count_query)).one()

        query = query.order_by(col(Flow.updated_at).desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        flows = list((await session.exec(query)).all())

        return PaginatedResponse[FlowRead](
            items=[FlowRead.model_validate(f) for f in flows],
            total=total,
            page=page,
            page_size=page_size,
            has_next=(page * page_size) < total,
            has_prev=page > 1,
        )


@flows_router.get("/flows/recent", response_model=list[RecentFlowItem])
async def get_recent_flows(
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    limit: int = Query(default=10, ge=1, le=50),
) -> list[RecentFlowItem]:
    async with db.session() as session:
        query = (
            select(Flow)
            .where(
                (Flow.user_id == user_id) | (Flow.is_public == True),  # noqa: E712
                Flow.is_deleted == False,  # noqa: E712
            )
            .order_by(col(Flow.updated_at).desc())
            .limit(limit)
        )
        flows = list((await session.exec(query)).all())

    return [
        RecentFlowItem(
            id=str(f.id),
            name=f.name,
            description=f.description,
            status=f.status.value,
            nodeCount=_node_count(f),
            createdAt=f.created_at.isoformat() if f.created_at else "",
            updatedAt=f.updated_at.isoformat() if f.updated_at else "",
        )
        for f in flows
    ]


@flows_router.get("/flows/{flow_id}", response_model=FlowRead)
async def get_flow(
    flow_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> FlowRead:
    async with db.session() as session:
        flow = await session.get(Flow, flow_id)
        if not flow or flow.is_deleted:
            raise HTTPException(status_code=404, detail="Flow not found")
        if flow.user_id != user_id and not flow.is_public:
            raise HTTPException(status_code=403, detail="Access denied to this flow")
        return FlowRead.model_validate(flow)


@flows_router.put("/flows/{flow_id}", response_model=FlowRead)
async def update_flow(
    flow_id: UUID,
    data: FlowUpdateRequest,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> FlowRead:
    async with db.session() as session:
        flow = await session.get(Flow, flow_id)
        if not flow or flow.is_deleted:
            raise HTTPException(status_code=404, detail="Flow not found")
        if flow.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied to this flow")

        update_data = data.model_dump(exclude_unset=True)
        if "data" in update_data:
            canonical = _canonicalize(update_data["data"])
            update_data["data"] = (
                json.dumps(canonical) if canonical else None
            )
        if "settings" in update_data:
            update_data["settings"] = (
                json.dumps(update_data["settings"]) if update_data["settings"] else None
            )

        for field, value in update_data.items():
            setattr(flow, field, value)

        flow.version += 1
        flow.updated_at = datetime.utcnow()
        session.add(flow)
        await session.flush()
        await session.refresh(flow)
        return FlowRead.model_validate(flow)


@flows_router.delete("/flows/{flow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_flow(
    flow_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> None:
    async with db.session() as session:
        flow = await session.get(Flow, flow_id)
        if not flow or flow.is_deleted:
            raise HTTPException(status_code=404, detail="Flow not found")
        if flow.user_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied to this flow")

        flow.is_deleted = True
        flow.deleted_at = datetime.utcnow()
        flow.updated_at = datetime.utcnow()
        session.add(flow)


@flows_router.post(
    "/flows/{flow_id}/duplicate",
    response_model=FlowDuplicateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def duplicate_flow(
    flow_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> FlowDuplicateResponse:
    async with db.session() as session:
        flow = await session.get(Flow, flow_id)
        if not flow or flow.is_deleted:
            raise HTTPException(status_code=404, detail="Flow not found")
        if flow.user_id != user_id and not flow.is_public:
            raise HTTPException(status_code=403, detail="Access denied to this flow")

        clone = Flow(
            name=f"{flow.name} (copy)",
            description=flow.description,
            icon=flow.icon,
            icon_bg_color=flow.icon_bg_color,
            status=FlowStatus.DRAFT,
            flow_type=flow.flow_type,
            is_public=False,
            tags=flow.tags,
            data=flow.data,
            settings=flow.settings,
            folder_id=flow.folder_id,
            user_id=user_id,
        )
        session.add(clone)
        await session.flush()
        await session.refresh(clone)
        return FlowDuplicateResponse(flow_id=clone.id, name=clone.name)


# ---------------------------------------------------------------------------
# Execution history by execution id (flow-scoped history is in ``router.py``)
# ---------------------------------------------------------------------------


@flows_router.get(
    "/executions/{execution_id}",
    response_model=WorkflowExecutionDetail,
)
async def get_execution(
    execution_id: UUID,
    user_id: CurrentUserId,
) -> WorkflowExecutionDetail:
    service = _get_workflow_service()
    record = await service.get_execution(execution_id)
    if not record:
        raise HTTPException(status_code=404, detail="Execution not found")

    return WorkflowExecutionDetail(
        id=record["id"],
        flow_id=record.get("flow_id"),
        status=record["status"],
        trigger_type=record.get("trigger_type", "manual"),
        node_count=record.get("node_count", 0),
        duration_ms=record.get("duration_ms", 0),
        error=record.get("error"),
        current_node=record.get("current_node"),
        inputs=record.get("inputs", {}),
        outputs=record.get("outputs", {}),
        execution_history=record.get("execution_history", []),
        started_at=_opt_dt(record.get("started_at")),
        completed_at=_opt_dt(record.get("completed_at")),
        created_at=_opt_dt(record.get("created_at")) or datetime.utcnow(),
    )


@flows_router.post("/executions/{execution_id}/cancel")
async def cancel_execution(
    execution_id: UUID,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    service = _get_workflow_service()
    ok = await service.cancel_execution(execution_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Execution not cancellable")
    return {"execution_id": str(execution_id), "status": "cancelled"}


@flows_router.post("/executions/{execution_id}/pause")
async def pause_execution(
    execution_id: UUID,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    service = _get_workflow_service()
    ok = await service.pause_execution(execution_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Execution not pausable")
    return {"execution_id": str(execution_id), "status": "paused"}


@flows_router.post("/executions/{execution_id}/resume")
async def resume_execution(
    execution_id: UUID,
    flow_id: UUID,
    user_id: CurrentUserId,
    resume_data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    service = _get_workflow_service()
    result = await service.resume_execution(execution_id, flow_id, resume_data)
    if not result:
        raise HTTPException(status_code=400, detail="Execution not resumable")
    return {"execution_id": str(execution_id), "status": result.status.value}


def _opt_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None
