"""Codex-style JSONL export for agent running traces."""

from __future__ import annotations

import json
from typing import Any

from leagent.telemetry.trace.models import loads_json
from leagent.telemetry.trace.store import TraceStore, get_trace_store


def _trace_dict(row: Any) -> dict[str, Any]:
    return {
        "trace_id": row.trace_id,
        "parent_trace_id": row.parent_trace_id,
        "session_id": row.session_id,
        "user_id": row.user_id,
        "scope": row.scope,
        "agent_name": row.agent_name,
        "model": row.model,
        "status": row.status,
        "terminal_reason": row.terminal_reason,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        "latency_ms": row.latency_ms,
        "input_tokens": row.input_tokens,
        "output_tokens": row.output_tokens,
        "cache_read_tokens": row.cache_read_tokens,
        "cache_miss_tokens": row.cache_miss_tokens,
        "total_cost_usd": row.total_cost_usd,
        "tool_call_count": row.tool_call_count,
        "llm_call_count": row.llm_call_count,
        "experiment_id": row.experiment_id,
        "prompt_hash": row.prompt_hash,
        "tags": loads_json(row.tags, default=None),
        "error": row.error,
        "scores": loads_json(row.scores, default=None),
        "root_span_id": row.root_span_id,
    }


def _span_dict(row: Any) -> dict[str, Any]:
    return {
        "span_id": row.span_id,
        "parent_span_id": row.parent_span_id,
        "trace_id": row.trace_id,
        "seq": row.seq,
        "kind": row.kind,
        "name": row.name,
        "status": row.status,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        "latency_ms": row.latency_ms,
        "attrs": loads_json(row.attrs, default={}),
        "input_preview": row.input_preview,
        "output_preview": row.output_preview,
        "payload_ref": row.payload_ref,
    }


async def export_trace_jsonl(
    trace_id: str,
    *,
    store: TraceStore | None = None,
) -> str:
    """Return a JSONL document: manifest line + one event line per span."""
    store = store or get_trace_store()
    trace = await store.get_trace(trace_id)
    if trace is None:
        raise KeyError(trace_id)
    spans = await store.list_spans(trace_id)
    lines = [
        json.dumps(
            {"type": "manifest", "schema": "leagent.agent_trace.v1", "trace": _trace_dict(trace)},
            ensure_ascii=False,
            default=str,
        )
    ]
    for span in spans:
        lines.append(
            json.dumps(
                {"type": "span", "span": _span_dict(span)},
                ensure_ascii=False,
                default=str,
            )
        )
    return "\n".join(lines) + "\n"


def build_span_tree(spans: list[Any]) -> list[dict[str, Any]]:
    """Nest spans under parents for UI waterfall rendering."""
    nodes: dict[str, dict[str, Any]] = {}
    for span in spans:
        node = _span_dict(span)
        node["children"] = []
        nodes[span.span_id] = node
    roots: list[dict[str, Any]] = []
    for span in spans:
        node = nodes[span.span_id]
        parent_id = span.parent_span_id
        if parent_id and parent_id in nodes:
            nodes[parent_id]["children"].append(node)
        else:
            roots.append(node)
    return roots


__all__ = ["build_span_tree", "export_trace_jsonl"]
