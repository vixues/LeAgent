"""WebSocket endpoints for live execution streaming.

Two endpoints are mounted by :mod:`router`:

- ``/ws/executions/{prompt_id}`` — per-prompt event stream. Clients
  receive every ``ProgressEvent`` for that prompt until ``execution_success``
  or ``execution_failure``.
- ``/ws/executions`` — monitor mode; clients see all events so dashboards
  can render a cross-flow view.

Auth: derived from the standard HTTP auth dependency (cookie/bearer).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, is_dataclass
from typing import Any

import structlog
from fastapi import WebSocket, WebSocketDisconnect, status

from ..engine.progress import NodeProgressState, ProgressEvent
from .event_bus import ExecutionEventBus

logger = structlog.get_logger(__name__)


async def stream_execution(websocket: WebSocket, prompt_id: str, bus: ExecutionEventBus) -> None:
    """Stream a single prompt's events to the client."""
    await websocket.accept()
    logger.info("ws_execution_connect", prompt_id=prompt_id)
    try:
        async for event in bus.subscribe(prompt_id):
            await _send_event(websocket, event)
            if event.type in {"execution_success", "execution_failed",
                               "execution_cancelled"}:
                break
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.error("ws_execution_stream_failed", prompt_id=prompt_id, exc_info=True)
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass
    finally:
        logger.info("ws_execution_disconnect", prompt_id=prompt_id)


async def stream_all(websocket: WebSocket, bus: ExecutionEventBus) -> None:
    """Monitor endpoint — relay every event on the bus."""
    await websocket.accept()
    try:
        async for event in bus.subscribe_all():
            await _send_event(websocket, event)
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.error("ws_monitor_stream_failed", exc_info=True)
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass


async def _send_event(websocket: WebSocket, event: ProgressEvent) -> None:
    state = event.state
    state_payload: dict[str, Any] | None = None
    if isinstance(state, NodeProgressState):
        state_payload = {
            "node_id": state.node_id,
            "status": state.status.value,
            "value": state.value,
            "max": state.max,
            "message": state.message,
            "error": state.error,
            "metadata": state.metadata,
        }
    payload = {
        "type": event.type,
        "prompt_id": event.prompt_id,
        "node_id": event.node_id,
        "state": state_payload,
        "data": event.data,
    }
    try:
        await websocket.send_text(json.dumps(payload, default=_default_json))
    except RuntimeError:
        raise WebSocketDisconnect(code=status.WS_1000_NORMAL_CLOSURE)


def _default_json(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return str(value)
