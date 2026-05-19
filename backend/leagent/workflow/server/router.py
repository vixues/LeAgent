"""FastAPI router for the workflow engine.

Mounted by the app at ``/api/v1/workflow``. It owns the new endpoints:

- ``POST /prompts`` — queue a run (replaces ``POST /flows/{id}/run``).
- ``GET /prompts/{prompt_id}`` — introspect a queued/running prompt.
- ``POST /prompts/{prompt_id}/cancel|pause|resume`` — lifecycle controls.
- ``POST /flows/{flow_id}/validate`` — structural validation.
- ``POST /flows/{flow_id}/build`` — compile + hash without running.
- ``POST /flows/{flow_id}/import`` / ``GET /flows/{flow_id}/export`` — IO.
- ``GET  /object_info`` — node schema snapshot.
- ``POST /admin/reload-nodes`` — trigger hot-reload from disk.
- ``POST /admin/replacements`` — manage node-replacement entries.
- ``WS   /ws/executions/{prompt_id}`` — per-prompt event stream.
- ``WS   /ws/executions`` — monitor mode.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any, Optional
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, status
from sqlmodel import col, select

from leagent.services.auth import CurrentUserId
from leagent.services.database import DatabaseService, get_database_service
from leagent.services.database.models import Flow

from ..io import export as io_export
from ..io import graph_hash, load
from ..nodes import get_registry
from ..nodes.replacement import NodeReplacement, get_replace_registry
from .event_bus import ExecutionEventBus
from .flows_router import flows_router
from .prompt_hooks import apply_replacements, seed_context, validate_prompt
from .schemas import (
    ExecutionStatusEvent,
    FlowBuildRequest,
    FlowBuildResponse,
    FlowExportResponse,
    FlowImportRequest,
    FlowImportResponse,
    FlowRunRequest,
    FlowRunResponse,
    FlowValidateRequest,
    FlowValidateResponse,
    NodeReloadResponse,
    NodeReplacementEntry,
    ObjectInfoResponse,
    WorkflowExecutionDetail,
    WorkflowExecutionSummary,
)
from .ws import stream_all, stream_execution

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/workflow", tags=["workflow"])
router.include_router(flows_router)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


async def get_bus() -> ExecutionEventBus:
    from leagent.services.service_manager import get_service_manager
    sm = get_service_manager()
    from .event_bus import get_event_bus
    return await get_event_bus(sm)


def _require_workflow_service() -> Any:
    from leagent.services.service_manager import get_service_manager
    sm = get_service_manager()
    if sm.workflow_service is None:
        raise HTTPException(status_code=503, detail="Workflow service unavailable")
    return sm.workflow_service


# ---------------------------------------------------------------------------
# Prompt submission / lifecycle
# ---------------------------------------------------------------------------


@router.post("/prompts", response_model=FlowRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_prompt(
    data: FlowRunRequest,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    flow_id: UUID = Query(..., description="Flow to execute."),
) -> FlowRunResponse:
    """Queue a workflow run. Returns immediately with a ``prompt_id``."""
    async with db.session() as session:
        flow = await session.get(Flow, flow_id)
        if not flow or flow.is_deleted:
            raise HTTPException(status_code=404, detail="Flow not found")
        if flow.user_id != user_id and not flow.is_public:
            raise HTTPException(status_code=403, detail="Access denied to this flow")
        flow.run_count += 1
        flow.last_run_at = datetime.utcnow()
        session.add(flow)
        await session.flush()

        raw = json.loads(flow.data) if flow.data else {}

    # Apply deprecated-node replacements before validation.
    raw, changes = apply_replacements(raw, user_id=str(user_id))
    if changes:
        logger.info("prompt_replacements_applied", count=len(changes), changes=changes)

    try:
        doc = load(raw)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid flow document: {exc}") from exc

    ok, _, errors = validate_prompt(doc)
    if not ok:
        raise HTTPException(status_code=422, detail={"validation_errors": errors})

    workflow_service = _require_workflow_service()
    extra = seed_context(data.extra_data, user_id=str(user_id),
                         session_id=str(data.session_id) if data.session_id else None)

    prompt_id = str(uuid4())
    execution = await workflow_service.enqueue(
        prompt_id=prompt_id,
        flow_id=flow_id,
        user_id=user_id,
        inputs=data.input_data or {},
        trigger_type=data.trigger_type,
        priority=data.priority,
        extra_data=extra,
    )

    position = await workflow_service.queue_position(prompt_id)
    return FlowRunResponse(
        execution_id=execution.id,
        prompt_id=prompt_id,
        flow_id=flow_id,
        status="queued",
        queue_position=position,
    )


@router.post(
    "/flows/{flow_id}/run",
    response_model=FlowRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_flow(
    flow_id: UUID,
    data: FlowRunRequest,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> FlowRunResponse:
    """Convenience wrapper around :func:`submit_prompt` using a path parameter."""
    return await submit_prompt(data, user_id, db, flow_id=flow_id)


@router.get("/prompts/{prompt_id}", response_model=WorkflowExecutionDetail)
async def get_prompt(prompt_id: str, user_id: CurrentUserId) -> WorkflowExecutionDetail:
    workflow_service = _require_workflow_service()
    record = await workflow_service.get_by_prompt_id(prompt_id)
    if not record:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return _to_detail(record)


@router.post("/prompts/{prompt_id}/cancel")
async def cancel_prompt(prompt_id: str, user_id: CurrentUserId) -> dict[str, Any]:
    workflow_service = _require_workflow_service()
    ok = await workflow_service.cancel(prompt_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Prompt not running or already finished")
    return {"prompt_id": prompt_id, "status": "cancelled"}


@router.post("/prompts/{prompt_id}/pause")
async def pause_prompt(prompt_id: str, user_id: CurrentUserId) -> dict[str, Any]:
    workflow_service = _require_workflow_service()
    ok = await workflow_service.pause(prompt_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Prompt not pausable")
    return {"prompt_id": prompt_id, "status": "paused"}


@router.post("/prompts/{prompt_id}/resume")
async def resume_prompt(
    prompt_id: str,
    user_id: CurrentUserId,
    resume_data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    workflow_service = _require_workflow_service()
    result = await workflow_service.resume(prompt_id, resume_data=resume_data)
    if result is None:
        raise HTTPException(status_code=400, detail="Prompt not resumable")
    return {"prompt_id": prompt_id, "status": result.status.value}


# ---------------------------------------------------------------------------
# Flow-level IO helpers
# ---------------------------------------------------------------------------


@router.post("/flows/{flow_id}/validate", response_model=FlowValidateResponse)
async def validate_flow(
    flow_id: UUID,
    body: FlowValidateRequest,
    user_id: CurrentUserId,
) -> FlowValidateResponse:
    try:
        doc = load(body.data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid flow document: {exc}") from exc
    ok, outputs, errors = validate_prompt(doc)
    return FlowValidateResponse(ok=ok, output_nodes=outputs, errors=errors)


@router.post("/flows/{flow_id}/build", response_model=FlowBuildResponse)
async def build_flow(
    flow_id: UUID,
    body: FlowBuildRequest,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> FlowBuildResponse:
    raw = body.data
    if raw is None:
        async with db.session() as session:
            flow = await session.get(Flow, flow_id)
            if not flow or flow.is_deleted:
                raise HTTPException(status_code=404, detail="Flow not found")
            if flow.user_id != user_id and not flow.is_public:
                raise HTTPException(status_code=403, detail="Access denied")
            raw = json.loads(flow.data) if flow.data else {}
    try:
        doc = load(raw)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid flow document: {exc}") from exc
    ok, outputs, _ = validate_prompt(doc)
    return FlowBuildResponse(
        ok=ok,
        graph_hash=graph_hash(doc),
        node_count=len(doc.nodes),
        output_nodes=outputs,
    )


@router.get("/flows/{flow_id}/export", response_model=FlowExportResponse)
async def export_flow(
    flow_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> FlowExportResponse:
    async with db.session() as session:
        flow = await session.get(Flow, flow_id)
        if not flow or flow.is_deleted:
            raise HTTPException(status_code=404, detail="Flow not found")
        if flow.user_id != user_id and not flow.is_public:
            raise HTTPException(status_code=403, detail="Access denied")
        raw = json.loads(flow.data) if flow.data else {}
    doc = load(raw)
    payload = io_export(doc)
    return FlowExportResponse(flow_id=flow.id, name=flow.name, document=payload)


@router.post("/flows/import", response_model=FlowImportResponse,
             status_code=status.HTTP_201_CREATED)
async def import_flow(
    body: FlowImportRequest,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> FlowImportResponse:
    try:
        doc = load(body.document)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid document: {exc}") from exc
    async with db.session() as session:
        flow = Flow(
            name=body.name or doc.id or "imported-flow",
            description="",
            data=json.dumps(io_export(doc)),
            user_id=user_id,
            folder_id=body.folder_id,
        )
        session.add(flow)
        await session.flush()
        await session.refresh(flow)
    return FlowImportResponse(flow_id=flow.id, name=flow.name, node_count=len(doc.nodes))


# ---------------------------------------------------------------------------
# Node introspection + admin
# ---------------------------------------------------------------------------


@router.get("/object_info", response_model=ObjectInfoResponse)
async def object_info() -> ObjectInfoResponse:
    return ObjectInfoResponse(nodes=get_registry().snapshot())


@router.post("/admin/reload-nodes", response_model=NodeReloadResponse)
async def reload_nodes(user_id: CurrentUserId) -> NodeReloadResponse:
    from leagent.config import get_settings
    from ..nodes import load_directory
    settings = get_settings()
    custom_dir = getattr(settings, "workflow_custom_nodes_dir", None)
    if custom_dir:
        await load_directory(custom_dir, get_registry(), run_prestartup=False)
    snapshot = get_registry().snapshot()
    registered: dict[str, list[str]] = {}
    for node_id, meta in snapshot.items():
        module = meta.get("module", "?")
        registered.setdefault(module, []).append(node_id)
    return NodeReloadResponse(registered=registered)


@router.get("/admin/replacements", response_model=list[NodeReplacementEntry])
async def list_replacements(user_id: CurrentUserId) -> list[NodeReplacementEntry]:
    return [
        NodeReplacementEntry(old_class=r.old_class, new_class=r.new_class, reason=r.reason)
        for r in get_replace_registry().list_all()
    ]


@router.post("/admin/replacements", response_model=NodeReplacementEntry,
             status_code=status.HTTP_201_CREATED)
async def register_replacement(
    entry: NodeReplacementEntry,
    user_id: CurrentUserId,
) -> NodeReplacementEntry:
    get_replace_registry().register(NodeReplacement(
        old_class=entry.old_class, new_class=entry.new_class, reason=entry.reason,
    ))
    return entry


@router.delete("/admin/replacements")
async def unregister_replacement(
    old_class: str,
    new_class: Optional[str] = None,
    user_id: CurrentUserId = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    removed = get_replace_registry().unregister(old_class, new_class)
    return {"removed": removed}


# ---------------------------------------------------------------------------
# Execution history
# ---------------------------------------------------------------------------


@router.get("/flows/{flow_id}/executions", response_model=list[WorkflowExecutionSummary])
async def list_flow_executions(
    flow_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[WorkflowExecutionSummary]:
    async with db.session() as session:
        flow = await session.get(Flow, flow_id)
        if not flow or flow.is_deleted:
            raise HTTPException(status_code=404, detail="Flow not found")
        if flow.user_id != user_id and not flow.is_public:
            raise HTTPException(status_code=403, detail="Access denied")
    workflow_service = _require_workflow_service()
    records = await workflow_service.list_executions(flow_id, limit, offset)
    return [_to_summary(r) for r in records]


# ---------------------------------------------------------------------------
# WebSocket endpoints
# ---------------------------------------------------------------------------


@router.websocket("/ws/executions/{prompt_id}")
async def ws_execution(
    websocket: WebSocket,
    prompt_id: str,
    bus: ExecutionEventBus = Depends(get_bus),
) -> None:
    await stream_execution(websocket, prompt_id, bus)


@router.websocket("/ws/executions")
async def ws_monitor(
    websocket: WebSocket,
    bus: ExecutionEventBus = Depends(get_bus),
) -> None:
    await stream_all(websocket, bus)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_summary(record: dict[str, Any]) -> WorkflowExecutionSummary:
    return WorkflowExecutionSummary(
        id=record["id"],
        flow_id=record.get("flow_id"),
        status=record["status"],
        trigger_type=record.get("trigger_type", "manual"),
        node_count=record.get("node_count", 0),
        duration_ms=record.get("duration_ms", 0),
        error=record.get("error"),
        started_at=_opt_dt(record.get("started_at")),
        completed_at=_opt_dt(record.get("completed_at")),
        created_at=_opt_dt(record.get("created_at")) or datetime.utcnow(),
    )


def _to_detail(record: dict[str, Any]) -> WorkflowExecutionDetail:
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


def _opt_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None
