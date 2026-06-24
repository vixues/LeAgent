"""Tests for the chat workflow DAG embed runner (background execution)."""

from __future__ import annotations

from typing import Any

import pytest

from leagent.chat_workflow.runner import (
    ChatWorkflowEmbedResult,
    evaluate_embed_result,
    start_chat_workflow_embed_via_engine,
)


class _FakeResult:
    def __init__(self, success: bool, outputs: dict[str, Any] | None, errors: list[str]):
        self.success = success
        self.outputs = outputs
        self.errors = errors


def test_evaluate_embed_result_success() -> None:
    out = evaluate_embed_result(_FakeResult(True, {"foo": 1}, []))
    assert out == ChatWorkflowEmbedResult(success=True, outputs={"foo": 1}, error=None)


def test_evaluate_embed_result_failure() -> None:
    out = evaluate_embed_result(_FakeResult(False, None, ["boom"]))
    assert out.success is False
    assert out.error == "boom"


def test_evaluate_embed_result_below_quality_bar() -> None:
    result = _FakeResult(
        True,
        {"quality_passed": False, "quality_score": 0.4, "quality_threshold": 0.8},
        [],
    )
    out = evaluate_embed_result(result)
    assert out.success is False
    assert out.error is not None
    assert "0.40" in out.error and "0.80" in out.error


def test_evaluate_embed_result_none() -> None:
    out = evaluate_embed_result(None)
    assert out.success is False


@pytest.mark.asyncio
async def test_start_embed_without_service_manager() -> None:
    outcome = await start_chat_workflow_embed_via_engine(
        flow_data={"nodes": {}, "control": {"start": "s", "end": "e"}},
        service_manager=None,
        user_id="00000000-0000-0000-0000-000000000001",
        session_id="00000000-0000-0000-0000-000000000002",
    )
    assert outcome.started is False
    assert outcome.error == "Workflow service unavailable"


@pytest.mark.asyncio
async def test_start_embed_delegates_to_workflow_service(
    registered_builtins,  # noqa: ARG001
) -> None:
    """A valid graph is started in the background; ids are returned immediately."""

    class _FakeWorkflowService:
        def __init__(self) -> None:
            self.called_with: dict[str, Any] | None = None

        async def start_compiled_document(self, document: Any, **kwargs: Any) -> dict[str, Any]:
            self.called_with = kwargs
            return {"prompt_id": "chat-embed-abc", "run_id": "run-1"}

    class _FakeServiceManager:
        def __init__(self, svc: _FakeWorkflowService) -> None:
            self.workflow_service = svc

    svc = _FakeWorkflowService()
    sm = _FakeServiceManager(svc)

    flow = {
        "id": "x",
        "name": "x",
        "control": {"start": "start", "end": "end", "edges": []},
        "nodes": {
            "start": {"class_type": "StartNode", "control": {"next": "end"}},
            "end": {"class_type": "EndNode"},
        },
    }

    outcome = await start_chat_workflow_embed_via_engine(
        flow_data=flow,
        service_manager=sm,
        user_id="00000000-0000-0000-0000-000000000001",
        session_id="sess-1",
        user_input="hi",
    )
    assert outcome.started is True
    assert outcome.prompt_id == "chat-embed-abc"
    assert outcome.run_id == "run-1"
    assert svc.called_with is not None
    assert svc.called_with["trigger_type"] == "chat_embed"
    assert svc.called_with["inputs"]["user_input"] == "hi"
