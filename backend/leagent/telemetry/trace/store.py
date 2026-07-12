"""SQL-backed durable store for agent running traces."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import case
from sqlmodel import col, func, select

from leagent.db.models.agent_trace import (
    AgentTrace,
    AgentTraceExperiment,
    AgentTraceSpan,
)
from leagent.db.models.base import _naive_utc_now, naive_utc_for_db_column
from leagent.telemetry.trace.models import dumps_json, loads_json
from leagent.utils.logging import get_logger

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return _naive_utc_now()


class TraceStore:
    """Persist and query agent_traces / spans / experiments."""

    def __init__(self, db: Any | None = None) -> None:
        self._db = db

    def _resolve_db(self) -> Any:
        if self._db is not None:
            return self._db
        from leagent.db import get_database_service

        return get_database_service()

    async def create_trace(
        self,
        *,
        trace_id: str,
        parent_trace_id: str | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        scope: str = "chat_turn",
        agent_name: str = "",
        model: str = "",
        experiment_id: str | None = None,
        prompt_hash: str | None = None,
        tags: dict[str, Any] | list[Any] | None = None,
        root_span_id: str | None = None,
        started_at: datetime | None = None,
    ) -> AgentTrace:
        row = AgentTrace(
            trace_id=trace_id,
            parent_trace_id=parent_trace_id,
            session_id=session_id,
            user_id=user_id,
            scope=scope or "chat_turn",
            agent_name=agent_name or "",
            model=model or "",
            status="running",
            started_at=naive_utc_for_db_column(started_at) or _utcnow(),
            experiment_id=experiment_id,
            prompt_hash=prompt_hash,
            tags=dumps_json(tags),
            root_span_id=root_span_id,
        )
        db = self._resolve_db()
        async with db.session() as session:
            session.add(row)
        return row

    async def update_trace(
        self,
        trace_id: str,
        *,
        status: str | None = None,
        terminal_reason: str | None = None,
        ended_at: datetime | None = None,
        latency_ms: float | None = None,
        model: str | None = None,
        agent_name: str | None = None,
        error: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cache_read_tokens: int | None = None,
        cache_miss_tokens: int | None = None,
        total_cost_usd: float | None = None,
        tool_call_count: int | None = None,
        llm_call_count: int | None = None,
        scores: dict[str, Any] | None = None,
        incr_input_tokens: int = 0,
        incr_output_tokens: int = 0,
        incr_cache_read_tokens: int = 0,
        incr_cache_miss_tokens: int = 0,
        incr_total_cost_usd: float = 0.0,
        incr_tool_call_count: int = 0,
        incr_llm_call_count: int = 0,
    ) -> None:
        db = self._resolve_db()
        async with db.session() as session:
            result = await session.exec(
                select(AgentTrace).where(AgentTrace.trace_id == trace_id)
            )
            row = result.first()
            if row is None:
                return
            if status is not None:
                row.status = status
            if terminal_reason is not None:
                row.terminal_reason = terminal_reason
            if ended_at is not None:
                row.ended_at = naive_utc_for_db_column(ended_at)
            if latency_ms is not None:
                row.latency_ms = float(latency_ms)
            if model is not None and model:
                row.model = model
            if agent_name is not None and agent_name:
                row.agent_name = agent_name
            if error is not None:
                row.error = error[:4000] if error else None
            if input_tokens is not None:
                row.input_tokens = input_tokens
            if output_tokens is not None:
                row.output_tokens = output_tokens
            if cache_read_tokens is not None:
                row.cache_read_tokens = cache_read_tokens
            if cache_miss_tokens is not None:
                row.cache_miss_tokens = cache_miss_tokens
            if total_cost_usd is not None:
                row.total_cost_usd = total_cost_usd
            if tool_call_count is not None:
                row.tool_call_count = tool_call_count
            if llm_call_count is not None:
                row.llm_call_count = llm_call_count
            if scores is not None:
                row.scores = dumps_json(scores)
            row.input_tokens += incr_input_tokens
            row.output_tokens += incr_output_tokens
            row.cache_read_tokens += incr_cache_read_tokens
            row.cache_miss_tokens += incr_cache_miss_tokens
            row.total_cost_usd += incr_total_cost_usd
            row.tool_call_count += incr_tool_call_count
            row.llm_call_count += incr_llm_call_count
            row.updated_at = _utcnow()
            session.add(row)

    async def append_span(
        self,
        *,
        span_id: str,
        trace_id: str,
        seq: int,
        kind: str,
        name: str,
        parent_span_id: str | None = None,
        status: str = "ok",
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
        latency_ms: float = 0.0,
        attrs: dict[str, Any] | None = None,
        input_preview: str | None = None,
        output_preview: str | None = None,
        payload_ref: str | None = None,
    ) -> AgentTraceSpan:
        row = AgentTraceSpan(
            span_id=span_id,
            parent_span_id=parent_span_id,
            trace_id=trace_id,
            seq=seq,
            kind=kind,
            name=name[:300],
            status=status,
            started_at=naive_utc_for_db_column(started_at) or _utcnow(),
            ended_at=naive_utc_for_db_column(ended_at),
            latency_ms=float(latency_ms or 0.0),
            attrs=dumps_json(attrs),
            input_preview=input_preview,
            output_preview=output_preview,
            payload_ref=payload_ref,
        )
        db = self._resolve_db()
        async with db.session() as session:
            session.add(row)
        return row

    async def close_span(
        self,
        span_id: str,
        *,
        status: str | None = None,
        ended_at: datetime | None = None,
        latency_ms: float | None = None,
        attrs: dict[str, Any] | None = None,
        output_preview: str | None = None,
        payload_ref: str | None = None,
    ) -> None:
        db = self._resolve_db()
        async with db.session() as session:
            result = await session.exec(
                select(AgentTraceSpan).where(AgentTraceSpan.span_id == span_id)
            )
            row = result.first()
            if row is None:
                return
            if status is not None:
                row.status = status
            end = naive_utc_for_db_column(ended_at) or _utcnow()
            row.ended_at = end
            if latency_ms is not None:
                row.latency_ms = float(latency_ms)
            elif row.started_at is not None:
                row.latency_ms = max(
                    0.0, (end - row.started_at).total_seconds() * 1000.0
                )
            if attrs is not None:
                existing = loads_json(row.attrs, default={}) or {}
                if isinstance(existing, dict):
                    existing.update(attrs)
                    row.attrs = dumps_json(existing)
                else:
                    row.attrs = dumps_json(attrs)
            if output_preview is not None:
                row.output_preview = output_preview
            if payload_ref is not None:
                row.payload_ref = payload_ref
            row.updated_at = _utcnow()
            session.add(row)

    async def get_trace(self, trace_id: str) -> AgentTrace | None:
        db = self._resolve_db()
        async with db.session() as session:
            result = await session.exec(
                select(AgentTrace).where(AgentTrace.trace_id == trace_id)
            )
            return result.first()

    async def list_spans(self, trace_id: str) -> list[AgentTraceSpan]:
        db = self._resolve_db()
        async with db.session() as session:
            result = await session.exec(
                select(AgentTraceSpan)
                .where(AgentTraceSpan.trace_id == trace_id)
                .order_by(col(AgentTraceSpan.seq).asc())
            )
            return list(result.all())

    async def list_traces(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        model: str | None = None,
        status: str | None = None,
        experiment_id: str | None = None,
        has_error: bool | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AgentTrace]:
        db = self._resolve_db()
        async with db.session() as session:
            stmt = select(AgentTrace)
            if session_id:
                stmt = stmt.where(AgentTrace.session_id == session_id)
            if user_id:
                stmt = stmt.where(AgentTrace.user_id == user_id)
            if model:
                stmt = stmt.where(AgentTrace.model == model)
            if status:
                stmt = stmt.where(AgentTrace.status == status)
            if experiment_id:
                stmt = stmt.where(AgentTrace.experiment_id == experiment_id)
            if has_error is True:
                stmt = stmt.where(AgentTrace.error.is_not(None))  # type: ignore[union-attr]
            elif has_error is False:
                stmt = stmt.where(AgentTrace.error.is_(None))  # type: ignore[union-attr]
            if since is not None:
                stmt = stmt.where(
                    AgentTrace.started_at >= naive_utc_for_db_column(since)
                )
            if until is not None:
                stmt = stmt.where(
                    AgentTrace.started_at <= naive_utc_for_db_column(until)
                )
            stmt = (
                stmt.order_by(col(AgentTrace.started_at).desc())
                .offset(max(0, offset))
                .limit(max(1, min(limit, 500)))
            )
            result = await session.exec(stmt)
            return list(result.all())

    async def stats_by_model(self, *, days: int = 30) -> list[dict[str, Any]]:
        db = self._resolve_db()
        since = _utcnow() - timedelta(days=max(1, days))
        async with db.session() as session:
            success_case = case(
                (AgentTrace.status.in_(["completed", "success"]), 1),
                else_=0,
            )
            error_case = case(
                (AgentTrace.error.is_not(None), 1),  # type: ignore[union-attr]
                else_=0,
            )
            stmt = (
                select(  # type: ignore[call-overload]
                    AgentTrace.model,
                    func.count().label("runs"),
                    func.sum(success_case).label("successes"),
                    func.sum(error_case).label("errors"),
                    func.avg(AgentTrace.latency_ms).label("avg_latency_ms"),
                    func.avg(AgentTrace.input_tokens).label("avg_input_tokens"),
                    func.avg(AgentTrace.output_tokens).label("avg_output_tokens"),
                    func.avg(AgentTrace.total_cost_usd).label("avg_cost_usd"),
                    func.avg(AgentTrace.tool_call_count).label("avg_tool_calls"),
                    func.sum(AgentTrace.input_tokens).label("total_input_tokens"),
                    func.sum(AgentTrace.output_tokens).label("total_output_tokens"),
                    func.sum(AgentTrace.total_cost_usd).label("total_cost_usd"),
                )
                .where(AgentTrace.started_at >= since)
                .group_by(AgentTrace.model)
                .order_by(func.count().desc())
            )
            result = await session.exec(stmt)
            rows = result.all()

        out: list[dict[str, Any]] = []
        for row in rows:
            runs = int(row[1] or 0)
            successes = int(row[2] or 0)
            model = str(row[0] or "") or "(unknown)"
            out.append(
                {
                    "model": model,
                    "runs": runs,
                    "successes": successes,
                    "errors": int(row[3] or 0),
                    "success_rate": round(successes / runs, 4) if runs else 0.0,
                    "avg_latency_ms": float(row[4] or 0.0),
                    "avg_input_tokens": float(row[5] or 0.0),
                    "avg_output_tokens": float(row[6] or 0.0),
                    "avg_cost_usd": float(row[7] or 0.0),
                    "avg_tool_calls": float(row[8] or 0.0),
                    "total_input_tokens": int(row[9] or 0),
                    "total_output_tokens": int(row[10] or 0),
                    "total_cost_usd": float(row[11] or 0.0),
                }
            )
        # Approximate p50/p95 from per-model latency lists (second query).
        for item in out:
            item["p50_latency_ms"] = await self._percentile_latency(
                item["model"], since, 0.50
            )
            item["p95_latency_ms"] = await self._percentile_latency(
                item["model"], since, 0.95
            )
        return out

    async def _percentile_latency(
        self, model: str, since: datetime, pct: float
    ) -> float:
        db = self._resolve_db()
        async with db.session() as session:
            result = await session.exec(
                select(AgentTrace.latency_ms)
                .where(AgentTrace.started_at >= since)
                .where(AgentTrace.model == ("" if model == "(unknown)" else model))
                .where(AgentTrace.latency_ms > 0)
                .order_by(col(AgentTrace.latency_ms).asc())
            )
            values = [float(v) for v in result.all() if v is not None]
        if not values:
            return 0.0
        idx = min(len(values) - 1, max(0, int(round((len(values) - 1) * pct))))
        return values[idx]

    async def create_experiment(
        self,
        *,
        experiment_id: str,
        name: str,
        prompt: str,
        model_ids: list[str],
        session_id: str | None = None,
        created_by: str | None = None,
    ) -> AgentTraceExperiment:
        row = AgentTraceExperiment(
            experiment_id=experiment_id,
            name=name or experiment_id,
            prompt=prompt,
            session_id=session_id,
            model_ids=dumps_json(model_ids) or "[]",
            created_by=created_by,
            status="pending",
        )
        db = self._resolve_db()
        async with db.session() as session:
            session.add(row)
        return row

    async def get_experiment(self, experiment_id: str) -> AgentTraceExperiment | None:
        db = self._resolve_db()
        async with db.session() as session:
            result = await session.exec(
                select(AgentTraceExperiment).where(
                    AgentTraceExperiment.experiment_id == experiment_id
                )
            )
            return result.first()

    async def update_experiment(
        self,
        experiment_id: str,
        *,
        status: str | None = None,
        error: str | None = None,
    ) -> None:
        db = self._resolve_db()
        async with db.session() as session:
            result = await session.exec(
                select(AgentTraceExperiment).where(
                    AgentTraceExperiment.experiment_id == experiment_id
                )
            )
            row = result.first()
            if row is None:
                return
            if status is not None:
                row.status = status
            if error is not None:
                row.error = error[:4000] if error else None
            row.updated_at = _utcnow()
            session.add(row)

    async def list_experiments(
        self, *, limit: int = 50, offset: int = 0
    ) -> list[AgentTraceExperiment]:
        db = self._resolve_db()
        async with db.session() as session:
            result = await session.exec(
                select(AgentTraceExperiment)
                .order_by(col(AgentTraceExperiment.created_at).desc())
                .offset(max(0, offset))
                .limit(max(1, min(limit, 200)))
            )
            return list(result.all())


_store: TraceStore | None = None


def get_trace_store() -> TraceStore:
    global _store
    if _store is None:
        _store = TraceStore()
    return _store


__all__ = ["TraceStore", "get_trace_store"]
