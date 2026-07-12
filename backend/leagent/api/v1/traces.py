"""Agent running-trace API (debug / eval / model comparison)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from leagent.services.auth import CurrentUserId
from leagent.telemetry.trace.export import build_span_tree, export_trace_jsonl
from leagent.telemetry.trace.models import loads_json, new_experiment_id
from leagent.telemetry.trace.store import get_trace_store
from leagent.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


class TraceSummary(BaseModel):
    trace_id: str
    parent_trace_id: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    scope: str = "chat_turn"
    agent_name: str = ""
    model: str = ""
    status: str = "running"
    terminal_reason: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_miss_tokens: int = 0
    total_cost_usd: float = 0.0
    tool_call_count: int = 0
    llm_call_count: int = 0
    experiment_id: Optional[str] = None
    prompt_hash: Optional[str] = None
    tags: Any = None
    error: Optional[str] = None
    scores: Any = None
    root_span_id: Optional[str] = None


class TraceSpanRead(BaseModel):
    span_id: str
    parent_span_id: Optional[str] = None
    trace_id: str
    seq: int = 0
    kind: str = "event"
    name: str = ""
    status: str = "ok"
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    latency_ms: float = 0.0
    attrs: Any = None
    input_preview: Optional[str] = None
    output_preview: Optional[str] = None
    payload_ref: Optional[str] = None


class TraceDetail(BaseModel):
    trace: TraceSummary
    spans: list[TraceSpanRead] = Field(default_factory=list)
    tree: list[dict[str, Any]] = Field(default_factory=list)


class ModelTraceStats(BaseModel):
    model: str
    runs: int = 0
    successes: int = 0
    errors: int = 0
    success_rate: float = 0.0
    avg_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    avg_input_tokens: float = 0.0
    avg_output_tokens: float = 0.0
    avg_cost_usd: float = 0.0
    avg_tool_calls: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0


class ExperimentCreate(BaseModel):
    name: str = ""
    prompt: str
    model_ids: list[str] = Field(min_length=1)
    session_id: Optional[str] = None
    agent_name: str = "default_agent"


class ExperimentRead(BaseModel):
    experiment_id: str
    name: str = ""
    prompt: str = ""
    session_id: Optional[str] = None
    model_ids: list[str] = Field(default_factory=list)
    created_by: Optional[str] = None
    status: str = "pending"
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    traces: list[TraceSummary] = Field(default_factory=list)


def _summary(row: Any) -> TraceSummary:
    return TraceSummary(
        trace_id=row.trace_id,
        parent_trace_id=row.parent_trace_id,
        session_id=row.session_id,
        user_id=row.user_id,
        scope=row.scope,
        agent_name=row.agent_name,
        model=row.model,
        status=row.status,
        terminal_reason=row.terminal_reason,
        started_at=row.started_at,
        ended_at=row.ended_at,
        latency_ms=row.latency_ms,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        cache_read_tokens=row.cache_read_tokens,
        cache_miss_tokens=row.cache_miss_tokens,
        total_cost_usd=row.total_cost_usd,
        tool_call_count=row.tool_call_count,
        llm_call_count=row.llm_call_count,
        experiment_id=row.experiment_id,
        prompt_hash=row.prompt_hash,
        tags=loads_json(row.tags, default=None),
        error=row.error,
        scores=loads_json(row.scores, default=None),
        root_span_id=row.root_span_id,
    )


def _span(row: Any) -> TraceSpanRead:
    return TraceSpanRead(
        span_id=row.span_id,
        parent_span_id=row.parent_span_id,
        trace_id=row.trace_id,
        seq=row.seq,
        kind=row.kind,
        name=row.name,
        status=row.status,
        started_at=row.started_at,
        ended_at=row.ended_at,
        latency_ms=row.latency_ms,
        attrs=loads_json(row.attrs, default={}),
        input_preview=row.input_preview,
        output_preview=row.output_preview,
        payload_ref=row.payload_ref,
    )


@router.get("", response_model=list[TraceSummary])
async def list_traces(
    user_id: CurrentUserId,
    session_id: Optional[str] = None,
    model: Optional[str] = None,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    experiment_id: Optional[str] = None,
    has_error: Optional[bool] = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[TraceSummary]:
    store = get_trace_store()
    rows = await store.list_traces(
        session_id=session_id,
        model=model,
        status=status_filter,
        experiment_id=experiment_id,
        has_error=has_error,
        limit=limit,
        offset=offset,
    )
    return [_summary(r) for r in rows]


@router.get("/stats/by-model", response_model=list[ModelTraceStats])
async def stats_by_model(
    user_id: CurrentUserId,
    days: int = Query(default=30, ge=1, le=365),
) -> list[ModelTraceStats]:
    store = get_trace_store()
    rows = await store.stats_by_model(days=days)
    return [ModelTraceStats(**row) for row in rows]


@router.get("/experiments", response_model=list[ExperimentRead])
async def list_experiments(
    user_id: CurrentUserId,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[ExperimentRead]:
    store = get_trace_store()
    rows = await store.list_experiments(limit=limit, offset=offset)
    out: list[ExperimentRead] = []
    for row in rows:
        traces = await store.list_traces(experiment_id=row.experiment_id, limit=50)
        out.append(
            ExperimentRead(
                experiment_id=row.experiment_id,
                name=row.name,
                prompt=row.prompt,
                session_id=row.session_id,
                model_ids=loads_json(row.model_ids, default=[]) or [],
                created_by=row.created_by,
                status=row.status,
                error=row.error,
                created_at=row.created_at,
                traces=[_summary(t) for t in traces],
            )
        )
    return out


@router.post("/experiments", response_model=ExperimentRead, status_code=status.HTTP_201_CREATED)
async def create_experiment(
    body: ExperimentCreate,
    user_id: CurrentUserId,
) -> ExperimentRead:
    if not body.prompt.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="prompt required")
    if not body.model_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="model_ids required")
    store = get_trace_store()
    eid = new_experiment_id()
    row = await store.create_experiment(
        experiment_id=eid,
        name=body.name or f"compare-{eid[:8]}",
        prompt=body.prompt,
        model_ids=list(body.model_ids),
        session_id=body.session_id,
        created_by=str(user_id) if user_id else None,
    )
    return ExperimentRead(
        experiment_id=row.experiment_id,
        name=row.name,
        prompt=row.prompt,
        session_id=row.session_id,
        model_ids=list(body.model_ids),
        created_by=row.created_by,
        status=row.status,
        error=row.error,
        created_at=row.created_at,
        traces=[],
    )


@router.get("/experiments/{experiment_id}", response_model=ExperimentRead)
async def get_experiment(experiment_id: str, user_id: CurrentUserId) -> ExperimentRead:
    store = get_trace_store()
    row = await store.get_experiment(experiment_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Experiment not found")
    traces = await store.list_traces(experiment_id=experiment_id, limit=100)
    return ExperimentRead(
        experiment_id=row.experiment_id,
        name=row.name,
        prompt=row.prompt,
        session_id=row.session_id,
        model_ids=loads_json(row.model_ids, default=[]) or [],
        created_by=row.created_by,
        status=row.status,
        error=row.error,
        created_at=row.created_at,
        traces=[_summary(t) for t in traces],
    )


@router.post("/experiments/{experiment_id}/run", response_model=ExperimentRead)
async def run_experiment(
    experiment_id: str,
    user_id: CurrentUserId,
    agent_name: str = Query(default="default_agent"),
) -> ExperimentRead:
    """Run the experiment prompt once per configured model."""
    store = get_trace_store()
    row = await store.get_experiment(experiment_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Experiment not found")
    model_ids = loads_json(row.model_ids, default=[]) or []
    if not model_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no models configured")

    await store.update_experiment(experiment_id, status="running", error=None)
    errors: list[str] = []

    try:
        from leagent.runtime.definition import ModelPolicy
        from leagent.sdk import AgentRuntime
        from leagent.services.service_manager import get_service_manager

        sm = get_service_manager()
        runtime = AgentRuntime.from_service_manager(sm)
        session_uuid: UUID | None = None
        if row.session_id:
            try:
                session_uuid = UUID(str(row.session_id))
            except Exception:
                session_uuid = None

        for model_id in model_ids:
            try:
                result = await runtime.run(
                    agent_name,
                    row.prompt,
                    session_id=session_uuid,
                    user_id=UUID(str(user_id)) if user_id else None,
                    tool_extra={
                        "experiment_id": experiment_id,
                        "tags": {"experiment": True, "model": model_id},
                    },
                    overrides={
                        "model": ModelPolicy(model=str(model_id)),
                    },
                )
                logger.info(
                    "trace_experiment_model_done",
                    experiment_id=experiment_id,
                    model=model_id,
                    reason=result.reason,
                    error=result.error,
                )
            except Exception as exc:
                logger.warning(
                    "trace_experiment_model_failed",
                    experiment_id=experiment_id,
                    model=model_id,
                    error=str(exc),
                )
                errors.append(f"{model_id}: {exc}")
    except Exception as exc:
        await store.update_experiment(
            experiment_id, status="error", error=str(exc)[:2000]
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"experiment run failed: {exc}",
        ) from exc

    status_val = "completed" if not errors else "completed_with_errors"
    await store.update_experiment(
        experiment_id,
        status=status_val,
        error="; ".join(errors) if errors else None,
    )
    return await get_experiment(experiment_id, user_id)


@router.get("/{trace_id}", response_model=TraceDetail)
async def get_trace(trace_id: str, user_id: CurrentUserId) -> TraceDetail:
    store = get_trace_store()
    row = await store.get_trace(trace_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trace not found")
    spans = await store.list_spans(trace_id)
    return TraceDetail(
        trace=_summary(row),
        spans=[_span(s) for s in spans],
        tree=build_span_tree(spans),
    )


@router.get("/{trace_id}/spans", response_model=list[TraceSpanRead])
async def list_trace_spans(trace_id: str, user_id: CurrentUserId) -> list[TraceSpanRead]:
    store = get_trace_store()
    row = await store.get_trace(trace_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trace not found")
    spans = await store.list_spans(trace_id)
    return [_span(s) for s in spans]


@router.get("/{trace_id}/export")
async def export_trace(trace_id: str, user_id: CurrentUserId) -> Response:
    try:
        body = await export_trace_jsonl(trace_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trace not found") from None
    return Response(
        content=body,
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="trace-{trace_id}.jsonl"',
        },
    )
