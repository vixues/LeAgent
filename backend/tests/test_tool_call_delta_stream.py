"""Regression: streaming tool_call_delta maps through QueryEngine."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from leagent.agent.deps import ModelStreamEvent
from leagent.agent.query_engine import QueryEngine, QueryEngineConfig


@pytest.mark.asyncio
async def test_map_item_forwards_tool_call_delta() -> None:
    cfg = QueryEngineConfig(llm=MagicMock(), session_id=uuid4())
    eng = QueryEngine(cfg)
    payload = {
        "index": 0,
        "id": "call_abc",
        "name": "canvas_publish",
        "arguments_raw": '{"title":"t"',
    }
    ev = ModelStreamEvent(tool_call_delta=payload)
    out: list[tuple[str, dict]] = []
    async for msg in eng._map_item(ev):
        out.append((msg.type, msg.data))
    assert ("tool_call_delta", payload) in out
