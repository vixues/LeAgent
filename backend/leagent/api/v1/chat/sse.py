"""Server-Sent Event serialization for the chat streaming endpoints.

Pure wire-format helpers that turn agent stream data into the two SSE shapes the
frontend consumes: OpenAI-compatible ``chat.completion.chunk`` frames and the
LeAgent ``{type, data}`` frontend-event envelope. No I/O, no DB — safe to reuse
from any streaming surface (companion bubbles, canvas/gen-UI, OpenAI proxy).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4


def tokens_from_stream_usage(
    token_usage: dict[str, Any] | None,
) -> tuple[int | None, int | None]:
    """Extract persisted DB token columns from agent ``token_usage`` metadata."""
    if not isinstance(token_usage, dict) or not token_usage:
        return None, None

    def _as_int(v: Any) -> int | None:
        if v is None:
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    return _as_int(token_usage.get("prompt_tokens")), _as_int(token_usage.get("completion_tokens"))


def format_openai_chunk(
    completion_id: str,
    created: int,
    model: str,
    delta: dict[str, Any],
    finish_reason: str | None = None,
) -> dict[str, Any]:
    """Serialize one OpenAI-compatible ``chat.completion.chunk`` SSE frame."""
    return {
        "event": "message",
        "data": json.dumps({
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
        }),
    }


def format_frontend_event(event_type: str, data: Any) -> dict[str, Any]:
    """Serialize one LeAgent ``{type, data}`` frontend-event SSE frame."""
    return {
        "event": "message",
        "data": json.dumps({"type": event_type, "data": data}),
    }


def companion_sse_events(etype: str, edata: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Extra frontend SSE events derived from tool results (canvas / generative UI)."""
    out: list[tuple[str, dict[str, Any]]] = []
    if etype != "tool_result" or not isinstance(edata, dict):
        return out

    td_any = edata.get("data")
    if isinstance(td_any, dict):
        _artifact_id = td_any.get("artifact_id")
        if _artifact_id:
            artifact_payload: dict[str, Any] = {
                "artifact_id": str(_artifact_id),
                "origin_tool": str(edata.get("name") or ""),
                "syntax_valid": td_any.get("syntax_valid"),
                "kind": td_any.get("kind"),
                "language": td_any.get("language"),
                "target_path": td_any.get("target_path"),
                "diagnostics": td_any.get("syntax_diagnostics"),
                "source_length": td_any.get("source_length"),
                "error_type": td_any.get("error_type"),
            }
            artifact_payload = {k: v for k, v in artifact_payload.items() if v is not None}
            out.append(("code_artifact", artifact_payload))

    if not edata.get("success"):
        return out
    name = str(edata.get("name") or "")
    td = edata.get("data")
    if not isinstance(td, dict):
        return out
    tool_call_id = str(edata.get("tool_call_id") or "")
    if name == "canvas_publish" and td.get("preview_path"):
        cid = str(td.get("canvas_id", ""))
        rev = int(td.get("revision") or 0)
        out.append(
            (
                "canvas",
                {
                    "id": f"{cid}-{rev}" if cid and rev else str(uuid4()),
                    "title": str(td.get("title") or "Canvas"),
                    "type": "html",
                    "preview_path": str(td["preview_path"]),
                    "canvas_id": cid,
                    "revision": rev,
                    "content_type": str(td.get("content_type") or "html"),
                    "trust": str(td.get("trust") or "hosted"),
                    "open_in_panel": bool(td.get("open_in_panel", True)),
                    **({"tool_call_id": tool_call_id} if tool_call_id else {}),
                },
            )
        )
    if name == "emit_ui_tree":
        # Flat result `{tree, canvas_id?}` matches tool args; unwrap legacy `{payload: …}`.
        tree_body = _genui_tool_result_body(td, primary_key="tree")
        if tree_body is not None:
            event = dict(tree_body)
            if tool_call_id:
                event["tool_call_id"] = tool_call_id
            out.append(("ui_tree", event))
    if name == "emit_ui_patch":
        patch_body = _genui_tool_result_body(td, primary_key="patches")
        if patch_body is not None:
            event = dict(patch_body)
            if tool_call_id:
                event["tool_call_id"] = tool_call_id
            out.append(("ui_patch", event))
    if name == "emit_pet_bubble":
        text = str(td.get("text") or "").strip()
        if text:
            bubble: dict[str, Any] = {"text": text[:120]}
            em = td.get("emoji")
            if em is not None:
                es = str(em).strip()
                if es:
                    bubble["emoji"] = es[:16]
            out.append(("pet_bubble", bubble))

    return out


def _genui_tool_result_body(td: dict[str, Any], *, primary_key: str) -> dict[str, Any] | None:
    """Return the GenUI event body from a flat or legacy-wrapped tool result."""
    if primary_key in td:
        return td
    nested = td.get("payload")
    if isinstance(nested, dict) and primary_key in nested:
        return nested
    return None


def openai_tool_call_from_stream_edata(edata: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize an SSE ``tool_call`` payload to an OpenAI-shaped ``tool_calls`` entry."""
    tid = str(edata.get("id") or "").strip()
    if not tid:
        return None
    name = str(edata.get("name") or "")
    args = edata.get("arguments", {})
    if isinstance(args, dict):
        arg_str = json.dumps(args, ensure_ascii=False)
    else:
        arg_str = str(args or "")
    return {
        "id": tid,
        "type": "function",
        "function": {"name": name, "arguments": arg_str},
    }
