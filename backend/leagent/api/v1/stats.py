"""Statistics and analytics API endpoints.

Aggregates data from both the ``Task`` and ``WorkflowExecution`` tables so the
dashboard reflects all activity – background tasks **and** workflow runs.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import func, select

from leagent.services.auth import CurrentUserId
from leagent.services.database import DatabaseService, get_database_service
from leagent.services.database.models import Flow, Task, TaskStatus
from leagent.services.database.models.workflow_execution import WorkflowExecution

router = APIRouter()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class HomeStats(BaseModel):
    totalFlows: int
    runningTasks: int
    completedToday: int
    successRate: float


class DashboardStats(BaseModel):
    tasksToday: int
    tasksChange: float
    successRate: float
    successRateChange: float
    failedTasks: int
    failedChange: float
    avgDuration: str
    durationChange: float


class UsageDataPoint(BaseModel):
    label: str
    success: int
    failed: int
    date: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pct_change(current: int | float, previous: int | float) -> float:
    if previous == 0:
        return 0.0
    return round((current - previous) / previous * 100, 1)


def _fmt_duration(ms: float) -> str:
    if ms < 1000:
        return f"{int(ms)}ms"
    if ms < 60_000:
        return f"{ms / 1000:.1f}s"
    return f"{ms / 60_000:.1f}m"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/home", response_model=HomeStats)
async def get_home_stats(
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> HomeStats:
    """Return summary statistics for the home dashboard."""
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    thirty_days_ago = now - timedelta(days=30)

    async with db.session() as session:
        # Total accessible flows
        total_flows_res = await session.exec(
            select(func.count()).select_from(
                select(Flow)
                .where(
                    (Flow.user_id == user_id) | (Flow.is_public == True),
                    Flow.is_deleted == False,
                )
                .subquery()
            )
        )
        total_flows: int = total_flows_res.one()

        # Currently running tasks
        running_res = await session.exec(
            select(func.count()).select_from(
                select(Task)
                .where(Task.user_id == user_id, Task.status == TaskStatus.RUNNING)
                .subquery()
            )
        )
        running_tasks: int = running_res.one()

        # Running workflow executions
        wf_running_res = await session.exec(
            select(func.count()).select_from(
                select(WorkflowExecution)
                .where(
                    WorkflowExecution.user_id == user_id,
                    WorkflowExecution.status == "running",
                )
                .subquery()
            )
        )
        running_tasks += wf_running_res.one()

        # Tasks completed today
        completed_today_res = await session.exec(
            select(func.count()).select_from(
                select(Task)
                .where(
                    Task.user_id == user_id,
                    Task.status == TaskStatus.COMPLETED,
                    Task.completed_at >= today_start,
                )
                .subquery()
            )
        )
        completed_today: int = completed_today_res.one()

        # Workflow executions completed today
        wf_completed_res = await session.exec(
            select(func.count()).select_from(
                select(WorkflowExecution)
                .where(
                    WorkflowExecution.user_id == user_id,
                    WorkflowExecution.status == "completed",
                    WorkflowExecution.completed_at >= today_start,
                )
                .subquery()
            )
        )
        completed_today += wf_completed_res.one()

        # Success rate over last 30 days (tasks)
        terminal_res = await session.exec(
            select(func.count()).select_from(
                select(Task)
                .where(
                    Task.user_id == user_id,
                    Task.status.in_([TaskStatus.COMPLETED, TaskStatus.FAILED]),
                    Task.completed_at >= thirty_days_ago,
                )
                .subquery()
            )
        )
        terminal_total: int = terminal_res.one()

        success_count = 0
        if terminal_total > 0:
            success_res = await session.exec(
                select(func.count()).select_from(
                    select(Task)
                    .where(
                        Task.user_id == user_id,
                        Task.status == TaskStatus.COMPLETED,
                        Task.completed_at >= thirty_days_ago,
                    )
                    .subquery()
                )
            )
            success_count = success_res.one()

        # Workflow execution terminal counts over 30 days
        wf_terminal_res = await session.exec(
            select(func.count()).select_from(
                select(WorkflowExecution)
                .where(
                    WorkflowExecution.user_id == user_id,
                    WorkflowExecution.status.in_(["completed", "failed"]),
                    WorkflowExecution.completed_at >= thirty_days_ago,
                )
                .subquery()
            )
        )
        wf_terminal: int = wf_terminal_res.one()

        wf_success = 0
        if wf_terminal > 0:
            wf_success_res = await session.exec(
                select(func.count()).select_from(
                    select(WorkflowExecution)
                    .where(
                        WorkflowExecution.user_id == user_id,
                        WorkflowExecution.status == "completed",
                        WorkflowExecution.completed_at >= thirty_days_ago,
                    )
                    .subquery()
                )
            )
            wf_success = wf_success_res.one()

        all_terminal = terminal_total + wf_terminal
        all_success = success_count + wf_success
        success_rate = round(all_success / all_terminal * 100, 1) if all_terminal else 0.0

    return HomeStats(
        totalFlows=total_flows,
        runningTasks=running_tasks,
        completedToday=completed_today,
        successRate=success_rate,
    )


@router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard_stats(
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    timeRange: str = Query(default="today", pattern="^(today|week|month)$"),
) -> DashboardStats:
    """Return period-over-period dashboard statistics."""
    now = datetime.utcnow()

    if timeRange == "today":
        period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        prev_start = period_start - timedelta(days=1)
        prev_end = period_start
    elif timeRange == "week":
        period_start = now - timedelta(days=7)
        prev_start = period_start - timedelta(days=7)
        prev_end = period_start
    else:  # month
        period_start = now - timedelta(days=30)
        prev_start = period_start - timedelta(days=30)
        prev_end = period_start

    async def _count(session, status_filter, start, end=None):
        q = select(Task).where(
            Task.user_id == user_id,
            Task.created_at >= start,
        )
        if end:
            q = q.where(Task.created_at < end)
        if status_filter:
            q = q.where(Task.status == status_filter)
        res = await session.exec(select(func.count()).select_from(q.subquery()))
        return res.one()

    async def _wf_count(session, status_filter, start, end=None):
        q = select(WorkflowExecution).where(
            WorkflowExecution.user_id == user_id,
            WorkflowExecution.created_at >= start,
        )
        if end:
            q = q.where(WorkflowExecution.created_at < end)
        if status_filter:
            q = q.where(WorkflowExecution.status == status_filter)
        res = await session.exec(select(func.count()).select_from(q.subquery()))
        return res.one()

    async def _avg_duration(session, start, end=None):
        q = select(func.avg(Task.duration_ms)).where(
            Task.user_id == user_id,
            Task.status == TaskStatus.COMPLETED,
            Task.duration_ms.isnot(None),
            Task.created_at >= start,
        )
        if end:
            q = q.where(Task.created_at < end)
        res = await session.exec(q)
        val = res.one()
        return float(val) if val else 0.0

    async def _wf_avg_duration(session, start, end=None):
        q = select(func.avg(WorkflowExecution.duration_ms)).where(
            WorkflowExecution.user_id == user_id,
            WorkflowExecution.status == "completed",
            WorkflowExecution.duration_ms > 0,
            WorkflowExecution.created_at >= start,
        )
        if end:
            q = q.where(WorkflowExecution.created_at < end)
        res = await session.exec(q)
        val = res.one()
        return float(val) if val else 0.0

    async with db.session() as session:
        tasks_cur = await _count(session, None, period_start)
        tasks_prev = await _count(session, None, prev_start, prev_end)
        wf_tasks_cur = await _wf_count(session, None, period_start)
        wf_tasks_prev = await _wf_count(session, None, prev_start, prev_end)

        failed_cur = await _count(session, TaskStatus.FAILED, period_start)
        failed_prev = await _count(session, TaskStatus.FAILED, prev_start, prev_end)
        wf_failed_cur = await _wf_count(session, "failed", period_start)
        wf_failed_prev = await _wf_count(session, "failed", prev_start, prev_end)

        success_cur = await _count(session, TaskStatus.COMPLETED, period_start)
        success_prev = await _count(session, TaskStatus.COMPLETED, prev_start, prev_end)
        wf_success_cur = await _wf_count(session, "completed", period_start)
        wf_success_prev = await _wf_count(session, "completed", prev_start, prev_end)

        dur_cur = await _avg_duration(session, period_start)
        dur_prev = await _avg_duration(session, prev_start, prev_end)
        wf_dur_cur = await _wf_avg_duration(session, period_start)
        wf_dur_prev = await _wf_avg_duration(session, prev_start, prev_end)

    all_tasks_cur = tasks_cur + wf_tasks_cur
    all_tasks_prev = tasks_prev + wf_tasks_prev

    all_failed_cur = failed_cur + wf_failed_cur
    all_failed_prev = failed_prev + wf_failed_prev

    all_success_cur = success_cur + wf_success_cur
    all_success_prev = success_prev + wf_success_prev

    terminal_cur = all_success_cur + all_failed_cur
    rate_cur = round(all_success_cur / terminal_cur * 100, 1) if terminal_cur else 0.0

    terminal_prev = all_success_prev + all_failed_prev
    rate_prev = round(all_success_prev / terminal_prev * 100, 1) if terminal_prev else 0.0

    # Weighted average duration across both sources
    dur_total_cur = tasks_cur + wf_tasks_cur
    if dur_total_cur > 0:
        combined_dur_cur = (
            (dur_cur * tasks_cur + wf_dur_cur * wf_tasks_cur) / dur_total_cur
        )
    else:
        combined_dur_cur = 0.0

    dur_total_prev = tasks_prev + wf_tasks_prev
    if dur_total_prev > 0:
        combined_dur_prev = (
            (dur_prev * tasks_prev + wf_dur_prev * wf_tasks_prev) / dur_total_prev
        )
    else:
        combined_dur_prev = 0.0

    return DashboardStats(
        tasksToday=all_tasks_cur,
        tasksChange=_pct_change(all_tasks_cur, all_tasks_prev),
        successRate=rate_cur,
        successRateChange=_pct_change(rate_cur, rate_prev),
        failedTasks=all_failed_cur,
        failedChange=_pct_change(all_failed_cur, all_failed_prev),
        avgDuration=_fmt_duration(combined_dur_cur),
        durationChange=_pct_change(combined_dur_cur, combined_dur_prev),
    )


@router.get("/usage", response_model=list[UsageDataPoint])
async def get_usage_data(
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    timeRange: str = Query(default="week", pattern="^(today|week|month)$"),
) -> list[UsageDataPoint]:
    """Return time-series task usage data for charts."""
    now = datetime.utcnow()

    if timeRange == "today":
        # Hourly buckets for today
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        buckets = [
            (day_start + timedelta(hours=h), day_start + timedelta(hours=h + 1))
            for h in range(now.hour + 1)
        ]
        label_fmt = "%H:00"
    elif timeRange == "week":
        # Daily buckets for last 7 days
        buckets = [
            (now - timedelta(days=d + 1), now - timedelta(days=d))
            for d in reversed(range(7))
        ]
        label_fmt = "%a"
    else:  # month
        # Daily buckets for last 30 days
        buckets = [
            (now - timedelta(days=d + 1), now - timedelta(days=d))
            for d in reversed(range(30))
        ]
        label_fmt = "%m/%d"

    async with db.session() as session:
        result = []
        for bucket_start, bucket_end in buckets:
            def _make_count_query(status):
                return (
                    select(func.count())
                    .select_from(
                        select(Task)
                        .where(
                            Task.user_id == user_id,
                            Task.status == status,
                            Task.created_at >= bucket_start,
                            Task.created_at < bucket_end,
                        )
                        .subquery()
                    )
                )

            def _make_wf_count_query(status_str):
                return (
                    select(func.count())
                    .select_from(
                        select(WorkflowExecution)
                        .where(
                            WorkflowExecution.user_id == user_id,
                            WorkflowExecution.status == status_str,
                            WorkflowExecution.created_at >= bucket_start,
                            WorkflowExecution.created_at < bucket_end,
                        )
                        .subquery()
                    )
                )

            s_res = await session.exec(_make_count_query(TaskStatus.COMPLETED))
            f_res = await session.exec(_make_count_query(TaskStatus.FAILED))
            wf_s_res = await session.exec(_make_wf_count_query("completed"))
            wf_f_res = await session.exec(_make_wf_count_query("failed"))

            result.append(
                UsageDataPoint(
                    label=bucket_start.strftime(label_fmt),
                    success=s_res.one() + wf_s_res.one(),
                    failed=f_res.one() + wf_f_res.one(),
                    date=bucket_start.date().isoformat(),
                )
            )

    return result
