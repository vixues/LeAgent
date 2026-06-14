"""Tests for ProgressRegistry async handler scheduling."""

from __future__ import annotations

import asyncio

import pytest

from leagent.workflow.engine.progress import ProgressEvent, ProgressRegistry


@pytest.mark.asyncio
async def test_emit_schedules_async_handlers() -> None:
    progress = ProgressRegistry(prompt_id="p-async")
    seen: list[str] = []

    async def _handler(event: ProgressEvent) -> None:
        seen.append(event.type)

    progress.add_handler(_handler)
    progress.emit(ProgressEvent(type="execution_start", prompt_id="p-async"))
    await asyncio.sleep(0)
    assert seen == ["execution_start"]
