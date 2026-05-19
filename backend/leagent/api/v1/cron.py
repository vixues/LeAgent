"""Cron job management API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Optional
from uuid import UUID, uuid4

from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from leagent.cron.base import CronExecution, CronJob, CronJobStatus, CronJobType as CronJobTypeBase
from leagent.cron.manager import CronManager
from leagent.services.auth import CurrentUserId
from leagent.services.service_manager import get_service_manager

router = APIRouter()


class CronJobType(str, Enum):
    FLOW = "flow"
    TASK = "task"
    WEBHOOK = "webhook"
    SCRIPT = "script"


def get_cron_manager() -> CronManager:
    sm = get_service_manager()
    if sm.cron is None:
        raise HTTPException(status_code=503, detail="Cron service unavailable")
    return sm.cron


CronManagerDep = Annotated[CronManager, Depends(get_cron_manager)]


def _api_type_to_base(t: CronJobType) -> CronJobTypeBase:
    if t is CronJobType.FLOW:
        return CronJobTypeBase.WORKFLOW
    return CronJobTypeBase(t.value)


def _base_type_to_api(t: CronJobTypeBase) -> CronJobType:
    if t is CronJobTypeBase.WORKFLOW:
        return CronJobType.FLOW
    return CronJobType(t.value)


def _parse_target_uuid(s: str | None) -> Optional[UUID]:
    if not s:
        return None
    try:
        return UUID(s)
    except ValueError:
        return None


def calculate_next_runs(cron_expression: str, count: int = 5, from_time: datetime | None = None) -> list[datetime]:
    base = from_time or datetime.now(timezone.utc)
    itr = croniter(cron_expression.strip(), base)
    return [itr.get_next(datetime) for _ in range(count)]


def calculate_next_run(cron_expression: str, from_time: datetime | None = None) -> datetime:
    return calculate_next_runs(cron_expression, 1, from_time)[0]


def _job_to_info(job: CronJob) -> "CronJobInfo":
    success_rate = 0.0
    if job.run_count > 0:
        success_rate = round((job.success_count / job.run_count) * 100, 1)

    next_runs: list[str] = []
    if job.enabled and job.status == CronJobStatus.ACTIVE:
        try:
            next_runs = [t.isoformat() for t in calculate_next_runs(job.schedule, 3)]
        except Exception:
            pass

    return CronJobInfo(
        id=job.id,
        name=job.name,
        description=job.description or None,
        job_type=_base_type_to_api(job.target_type),
        cron_expression=job.schedule,
        status=job.status,
        enabled=job.enabled,
        last_run_at=job.last_run_at,
        next_run_at=job.next_run_at,
        run_count=job.run_count,
        success_count=job.success_count,
        error_count=job.error_count,
        success_rate=success_rate,
        consecutive_failures=job.consecutive_failures,
        next_runs=next_runs,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _job_to_detail(job: CronJob) -> "CronJobDetail":
    success_rate = 0.0
    if job.run_count > 0:
        success_rate = round((job.success_count / job.run_count) * 100, 1)

    next_runs: list[str] = []
    if job.enabled and job.status == CronJobStatus.ACTIVE:
        try:
            next_runs = [t.isoformat() for t in calculate_next_runs(job.schedule, 5)]
        except Exception:
            pass

    return CronJobDetail(
        id=job.id,
        name=job.name,
        description=job.description or None,
        job_type=_base_type_to_api(job.target_type),
        cron_expression=job.schedule,
        status=job.status,
        enabled=job.enabled,
        target_id=_parse_target_uuid(job.target_id),
        payload=job.payload,
        last_run_at=job.last_run_at,
        next_run_at=job.next_run_at,
        last_run_status=job.last_run_status.value if job.last_run_status else None,
        last_error=job.last_error,
        run_count=job.run_count,
        success_count=job.success_count,
        error_count=job.error_count,
        success_rate=success_rate,
        consecutive_failures=job.consecutive_failures,
        next_runs=next_runs,
        timezone=job.timezone,
        max_retries=job.max_retries,
        timeout_sec=job.timeout_sec,
        notify_on_start=job.notify_on_start,
        notify_on_complete=job.notify_on_complete,
        notify_on_fail=job.notify_on_fail,
        tags=job.tags,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _require_user_job(cron: CronManager, job_id: UUID, user_id: UUID) -> CronJob:
    job = cron.get_job(job_id)
    if not job or job.user_id != str(user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cron job not found",
        )
    return job


# ---- Schemas ----

class CronJobInfo(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    job_type: CronJobType
    cron_expression: str
    status: CronJobStatus
    enabled: bool
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    run_count: int = 0
    success_count: int = 0
    error_count: int = 0
    success_rate: float = 0.0
    consecutive_failures: int = 0
    next_runs: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class CronJobDetail(CronJobInfo):
    target_id: Optional[UUID] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    last_run_status: Optional[str] = None
    last_error: Optional[str] = None
    timezone: str = "UTC"
    max_retries: int = 3
    timeout_sec: int = 3600
    notify_on_start: bool = False
    notify_on_complete: bool = True
    notify_on_fail: bool = True
    tags: list[str] = Field(default_factory=list)


class CronJobCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    job_type: CronJobType
    cron_expression: str = Field(..., min_length=1, max_length=100)
    target_id: Optional[UUID] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = Field(default=True)
    timezone: str = Field(default="UTC", max_length=50)
    max_retries: int = Field(default=3, ge=0, le=10)
    timeout_sec: int = Field(default=3600, ge=1, le=86400)
    notify_on_start: bool = False
    notify_on_complete: bool = True
    notify_on_fail: bool = True
    tags: list[str] = Field(default_factory=list)


class CronJobUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    cron_expression: Optional[str] = Field(default=None, min_length=1, max_length=100)
    target_id: Optional[UUID] = None
    payload: Optional[dict[str, Any]] = None
    enabled: Optional[bool] = None
    timezone: Optional[str] = Field(default=None, max_length=50)
    max_retries: Optional[int] = Field(default=None, ge=0, le=10)
    timeout_sec: Optional[int] = Field(default=None, ge=1, le=86400)
    notify_on_start: Optional[bool] = None
    notify_on_complete: Optional[bool] = None
    notify_on_fail: Optional[bool] = None
    tags: Optional[list[str]] = None


class CronJobListResponse(BaseModel):
    jobs: list[CronJobInfo]
    total: int


class CronJobRunResponse(BaseModel):
    job_id: UUID
    task_id: UUID
    status: str
    message: str


class CronExecutionHistoryResponse(BaseModel):
    executions: list[CronExecution]
    total: int


class CronJobStats(BaseModel):
    job_id: UUID
    name: str
    total_runs: int
    successful_runs: int
    failed_runs: int
    success_rate: float
    avg_duration_ms: float
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]


class CronSystemStats(BaseModel):
    total_jobs: int
    active_jobs: int
    paused_jobs: int
    failed_jobs: int
    running_executions: int
    total_runs_all_jobs: int
    scheduler_running: bool
    next_runs: list[dict[str, Any]]


class NextRunsResponse(BaseModel):
    cron_expression: str
    next_runs: list[str]


# ---- Endpoints ----

@router.get("", response_model=CronJobListResponse)
async def list_cron_jobs(
    user_id: CurrentUserId,
    cron: CronManagerDep,
    job_status: Optional[CronJobStatus] = Query(default=None, alias="status"),
    job_type: Optional[CronJobType] = Query(default=None),
    search: Optional[str] = Query(default=None, max_length=100),
) -> CronJobListResponse:
    jobs = cron.list_jobs(status=job_status, user_id=user_id)
    if job_type is not None:
        jobs = [j for j in jobs if _base_type_to_api(j.target_type) == job_type]
    if search:
        s = search.lower()
        jobs = [j for j in jobs if s in j.name.lower() or s in (j.description or "").lower()]
    return CronJobListResponse(
        jobs=[_job_to_info(j) for j in jobs],
        total=len(jobs),
    )


@router.get("/health")
async def cron_health(cron: CronManagerDep) -> dict[str, Any]:
    return await cron.get_health_status()


@router.get("/stats", response_model=CronSystemStats)
async def cron_system_stats(
    user_id: CurrentUserId,
    cron: CronManagerDep,
) -> CronSystemStats:
    jobs = cron.list_jobs(user_id=user_id)
    active = sum(1 for j in jobs if j.status == CronJobStatus.ACTIVE)
    paused = sum(1 for j in jobs if j.status == CronJobStatus.PAUSED)
    failed = sum(1 for j in jobs if j.status == CronJobStatus.FAILED)
    total_runs = sum(j.run_count for j in jobs)
    running = len(cron.get_running_executions())

    next_run_times = cron.get_next_run_times(5)
    next_runs = [
        {"job_id": str(j.id), "name": j.name, "next_run": t.isoformat()}
        for j, t in next_run_times
        if j.user_id == str(user_id)
    ]

    return CronSystemStats(
        total_jobs=len(jobs),
        active_jobs=active,
        paused_jobs=paused,
        failed_jobs=failed,
        running_executions=running,
        total_runs_all_jobs=total_runs,
        scheduler_running=cron._started,
        next_runs=next_runs,
    )


@router.get("/preview-next-runs", response_model=NextRunsResponse)
async def get_preview_cron_next_runs(
    user_id: CurrentUserId,
    cron_expression: str = Query(..., min_length=1, max_length=100),
    count: int = Query(default=5, ge=1, le=20),
) -> NextRunsResponse:
    """Preview next run times for a cron expression (GET, for browser / simple clients)."""
    try:
        next_runs = [t.isoformat() for t in calculate_next_runs(cron_expression, count)]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid cron expression: {e}") from e
    return NextRunsResponse(cron_expression=cron_expression, next_runs=next_runs)


@router.post("/preview-next-runs", response_model=NextRunsResponse)
async def preview_cron_next_runs(
    user_id: CurrentUserId,
    cron_expression: str = Query(..., min_length=1, max_length=100),
    count: int = Query(default=5, ge=1, le=20),
) -> NextRunsResponse:
    try:
        next_runs = [t.isoformat() for t in calculate_next_runs(cron_expression, count)]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid cron expression: {e}") from e
    return NextRunsResponse(cron_expression=cron_expression, next_runs=next_runs)


@router.post("", response_model=CronJobDetail, status_code=status.HTTP_201_CREATED)
async def create_cron_job(
    data: CronJobCreateRequest,
    user_id: CurrentUserId,
    cron: CronManagerDep,
) -> CronJobDetail:
    tid = str(data.target_id) if data.target_id else None
    base_type = _api_type_to_base(data.job_type)
    job = CronJob(
        id=uuid4(),
        name=data.name,
        description=data.description or "",
        schedule=data.cron_expression,
        target_type=base_type,
        target_id=tid,
        workflow_id=tid if data.job_type is CronJobType.FLOW else None,
        enabled=data.enabled,
        status=CronJobStatus.ACTIVE if data.enabled else CronJobStatus.PAUSED,
        payload=data.payload,
        user_id=str(user_id),
        next_run_at=calculate_next_run(data.cron_expression) if data.enabled else None,
        timezone=data.timezone,
        max_retries=data.max_retries,
        timeout_sec=data.timeout_sec,
        notify_on_start=data.notify_on_start,
        notify_on_complete=data.notify_on_complete,
        notify_on_fail=data.notify_on_fail,
        tags=data.tags,
    )
    try:
        added = await cron.add_job(job)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    return _job_to_detail(added)


@router.get("/{job_id}/history", response_model=CronExecutionHistoryResponse)
async def get_cron_job_history(
    job_id: UUID,
    user_id: CurrentUserId,
    cron: CronManagerDep,
    limit: int = Query(default=100, ge=1, le=1000),
) -> CronExecutionHistoryResponse:
    _require_user_job(cron, job_id, user_id)
    if cron.executor is None:
        raise HTTPException(status_code=503, detail="Cron executor unavailable")
    executions = await cron.executor.get_execution_history(job_id, limit)
    return CronExecutionHistoryResponse(executions=executions, total=len(executions))


@router.get("/{job_id}/stats", response_model=CronJobStats)
async def get_cron_job_stats(
    job_id: UUID,
    user_id: CurrentUserId,
    cron: CronManagerDep,
) -> CronJobStats:
    job = _require_user_job(cron, job_id, user_id)
    success_rate = 0.0
    if job.run_count > 0:
        success_rate = round((job.success_count / job.run_count) * 100, 1)

    avg_duration_ms = 0.0
    if cron.executor:
        executions = await cron.executor.get_execution_history(job_id, 100)
        durations = [e.duration_ms for e in executions if e.duration_ms > 0]
        if durations:
            avg_duration_ms = sum(durations) / len(durations)

    return CronJobStats(
        job_id=job.id,
        name=job.name,
        total_runs=job.run_count,
        successful_runs=job.success_count,
        failed_runs=job.error_count,
        success_rate=success_rate,
        avg_duration_ms=avg_duration_ms,
        last_run_at=job.last_run_at,
        next_run_at=job.next_run_at,
    )


@router.get("/{job_id}/next-runs", response_model=NextRunsResponse)
async def get_cron_job_next_runs(
    job_id: UUID,
    user_id: CurrentUserId,
    cron: CronManagerDep,
    count: int = Query(default=5, ge=1, le=20),
) -> NextRunsResponse:
    job = _require_user_job(cron, job_id, user_id)
    try:
        next_runs = [t.isoformat() for t in calculate_next_runs(job.schedule, count)]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid cron expression: {e}") from e
    return NextRunsResponse(cron_expression=job.schedule, next_runs=next_runs)


@router.get("/{job_id}", response_model=CronJobDetail)
async def get_cron_job(
    job_id: UUID,
    user_id: CurrentUserId,
    cron: CronManagerDep,
) -> CronJobDetail:
    job = _require_user_job(cron, job_id, user_id)
    return _job_to_detail(job)


@router.put("/{job_id}", response_model=CronJobDetail)
async def update_cron_job(
    job_id: UUID,
    data: CronJobUpdateRequest,
    user_id: CurrentUserId,
    cron: CronManagerDep,
) -> CronJobDetail:
    _require_user_job(cron, job_id, user_id)
    updates: dict[str, Any] = {}
    if data.name is not None:
        updates["name"] = data.name
    if data.description is not None:
        updates["description"] = data.description
    if data.cron_expression is not None:
        updates["schedule"] = data.cron_expression
    if data.target_id is not None:
        tid = str(data.target_id)
        updates["target_id"] = tid
        job = cron.get_job(job_id)
        if job and job.target_type is CronJobTypeBase.WORKFLOW:
            updates["workflow_id"] = tid
    if data.payload is not None:
        updates["payload"] = data.payload
    if data.enabled is not None:
        updates["enabled"] = data.enabled
        updates["status"] = CronJobStatus.ACTIVE if data.enabled else CronJobStatus.PAUSED
    if data.timezone is not None:
        updates["timezone"] = data.timezone
    if data.max_retries is not None:
        updates["max_retries"] = data.max_retries
    if data.timeout_sec is not None:
        updates["timeout_sec"] = data.timeout_sec
    if data.notify_on_start is not None:
        updates["notify_on_start"] = data.notify_on_start
    if data.notify_on_complete is not None:
        updates["notify_on_complete"] = data.notify_on_complete
    if data.notify_on_fail is not None:
        updates["notify_on_fail"] = data.notify_on_fail
    if data.tags is not None:
        updates["tags"] = data.tags

    updated = await cron.update_job(job_id, updates)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cron job not found",
        )
    return _job_to_detail(updated)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cron_job(
    job_id: UUID,
    user_id: CurrentUserId,
    cron: CronManagerDep,
) -> None:
    _require_user_job(cron, job_id, user_id)
    removed = await cron.remove_job(job_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cron job not found",
        )


@router.post("/{job_id}/run", response_model=CronJobRunResponse)
async def run_cron_job(
    job_id: UUID,
    user_id: CurrentUserId,
    cron: CronManagerDep,
) -> CronJobRunResponse:
    _require_user_job(cron, job_id, user_id)
    execution = await cron.trigger_job(job_id)
    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cron job not found",
        )
    return CronJobRunResponse(
        job_id=job_id,
        task_id=execution.id,
        status=execution.status.value,
        message="Cron job triggered successfully",
    )


@router.post("/{job_id}/pause")
async def pause_cron_job(
    job_id: UUID,
    user_id: CurrentUserId,
    cron: CronManagerDep,
) -> dict[str, Any]:
    _require_user_job(cron, job_id, user_id)
    updated = await cron.pause_job(job_id)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cron job not found",
        )
    return {
        "job_id": str(job_id),
        "status": updated.status.value,
        "message": "Cron job paused",
    }


@router.post("/{job_id}/resume")
async def resume_cron_job(
    job_id: UUID,
    user_id: CurrentUserId,
    cron: CronManagerDep,
) -> dict[str, Any]:
    _require_user_job(cron, job_id, user_id)
    updated = await cron.resume_job(job_id)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cron job not found",
        )
    return {
        "job_id": str(job_id),
        "status": updated.status.value,
        "message": "Cron job resumed",
    }


@router.post("/{job_id}/clone", response_model=CronJobDetail, status_code=status.HTTP_201_CREATED)
async def clone_cron_job(
    job_id: UUID,
    user_id: CurrentUserId,
    cron: CronManagerDep,
    new_name: Optional[str] = Query(default=None, max_length=100),
) -> CronJobDetail:
    """Duplicate a cron job."""
    original = _require_user_job(cron, job_id, user_id)
    from leagent.cron.base import CronJobStatus

    cloned = CronJob(
        id=uuid4(),
        name=new_name or f"{original.name} (Copy)",
        description=original.description,
        schedule=original.schedule,
        target_type=original.target_type,
        target_id=original.target_id,
        workflow_id=original.workflow_id,
        enabled=False,
        status=CronJobStatus.PAUSED,
        payload=dict(original.payload),
        user_id=original.user_id,
        timezone=original.timezone,
        max_retries=original.max_retries,
        timeout_sec=original.timeout_sec,
        notify_on_start=original.notify_on_start,
        notify_on_complete=original.notify_on_complete,
        notify_on_fail=original.notify_on_fail,
        tags=list(original.tags),
        next_run_at=None,
    )
    try:
        added = await cron.add_job(cloned)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return _job_to_detail(added)
