"""Curated chat workflow card templates for demos, QA, and docs.

Each entry is validated against :class:`~leagent.tools.registry.ToolRegistry`
at catalog build time so every template is runnable via
``POST /chat/sessions/{id}/workflow-steps/{step_id}/run``.
"""

from __future__ import annotations

from typing import Any

from leagent.chat_workflow.schema import chat_workflow_digest, parse_chat_workflow_spec
from leagent.tools.registry import ToolRegistry

# Raw specs only use read-only tools registered at bootstrap.
_RAW: list[dict[str, Any]] = [
    {
        "id": "clock_utc",
        "title": "Server clock (UTC)",
        "description": "Returns the current date/time in UTC using the date_calculator tool.",
        "spec": {
            "version": 1,
            "title": "Server clock (UTC)",
            "summary": "Useful sanity check that tool execution and session context work.",
            "steps": [
                {
                    "id": "now_utc",
                    "label": "Get current time (UTC)",
                    "hint": "Uses operation=now with UTC timezone.",
                    "action": {
                        "kind": "tool",
                        "tool_id": "date_calculator",
                        "arguments": {
                            "operation": "now",
                            "to_timezone": "UTC",
                            "format": "%Y-%m-%d %H:%M:%S %Z",
                        },
                    },
                },
            ],
        },
    },
    {
        "id": "json_parse_sample",
        "title": "Parse sample JSON",
        "description": "Parses a small JSON object with json_parser (read-only).",
        "spec": {
            "version": 1,
            "title": "Parse sample JSON",
            "summary": "Extracts structured data from inline JSON text.",
            "steps": [
                {
                    "id": "parse_inline",
                    "label": "Parse JSON text",
                    "hint": "operation=parse on a fixed payload.",
                    "action": {
                        "kind": "tool",
                        "tool_id": "json_parser",
                        "arguments": {
                            "operation": "parse",
                            "text": '{"project":"leagent","kind":"chat_workflow","version":1}',
                        },
                    },
                },
            ],
        },
    },
    {
        "id": "text_chunk",
        "title": "Chunk placeholder text",
        "description": "Splits fixed lorem text into character chunks with text_splitter.",
        "spec": {
            "version": 1,
            "title": "Chunk placeholder text",
            "summary": "Demonstrates split_chars with overlap disabled.",
            "steps": [
                {
                    "id": "split_chars",
                    "label": "Split into 32-character chunks",
                    "hint": "chunk_size=32, chunk_overlap=0",
                    "action": {
                        "kind": "tool",
                        "tool_id": "text_splitter",
                        "arguments": {
                            "operation": "split_chars",
                            "text": "LeAgent chat workflow templates help validate tool wiring end-to-end.",
                            "chunk_size": 32,
                            "chunk_overlap": 0,
                        },
                    },
                },
            ],
        },
    },
    {
        "id": "date_add_week",
        "title": "Add 7 days to a fixed date",
        "description": "Date arithmetic without depending on “today” in the template.",
        "spec": {
            "version": 1,
            "title": "Add 7 days to a fixed date",
            "summary": "Adds one week to 2026-04-01 and returns ISO-friendly output.",
            "steps": [
                {
                    "id": "add_week",
                    "label": "Add 7 days",
                    "hint": "operation=add, date=2026-04-01, days=7",
                    "action": {
                        "kind": "tool",
                        "tool_id": "date_calculator",
                        "arguments": {
                            "operation": "add",
                            "date": "2026-04-01",
                            "days": 7,
                            "format": "%Y-%m-%d",
                        },
                    },
                },
            ],
        },
    },
    {
        "id": "session_context_json",
        "title": "Resolve session placeholders",
        "description": "json_parser parse on text that embeds ${session_id} (resolved server-side on run).",
        "spec": {
            "version": 1,
            "title": "Resolve session placeholders",
            "summary": "Verifies template resolution for session_id in tool arguments.",
            "steps": [
                {
                    "id": "parse_session_wrapped",
                    "label": "Parse JSON mentioning current session",
                    "hint": "Placeholder ${session_id} is substituted before the tool runs.",
                    "action": {
                        "kind": "tool",
                        "tool_id": "json_parser",
                        "arguments": {
                            "operation": "parse",
                            "text": '{"session_id":"${session_id}","note":"from chat workflow template"}',
                        },
                    },
                },
            ],
        },
    },
    {
        "id": "rule_eval_minimal",
        "title": "Evaluate a simple rule",
        "description": "rule_matcher with a single eq rule on inline data.",
        "spec": {
            "version": 1,
            "title": "Evaluate a simple rule",
            "summary": "Checks status field equals ok.",
            "steps": [
                {
                    "id": "eval_status",
                    "label": "Match status == ok",
                    "hint": "operation=evaluate with one rule.",
                    "action": {
                        "kind": "tool",
                        "tool_id": "rule_matcher",
                        "arguments": {
                            "operation": "evaluate",
                            "data": {"status": "ok", "region": "test-lab"},
                            "rules": [
                                {
                                    "id": "status_ok",
                                    "field": "status",
                                    "operator": "eq",
                                    "value": "ok",
                                },
                            ],
                        },
                    },
                },
            ],
        },
    },
]


def build_chat_workflow_template_catalog(registry: ToolRegistry) -> list[dict[str, Any]]:
    """Return validated specs plus digests for API responses."""
    catalog: list[dict[str, Any]] = []
    for row in _RAW:
        spec = parse_chat_workflow_spec(row["spec"], registry=registry)
        catalog.append({
            "id": row["id"],
            "title": row["title"],
            "description": row.get("description", ""),
            "spec": spec.model_dump(mode="json"),
            "digest": chat_workflow_digest(spec),
        })
    return catalog
