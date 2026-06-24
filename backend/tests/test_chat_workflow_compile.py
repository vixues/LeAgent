"""Tests for chat workflow compilation."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from leagent.chat_workflow.compile import compile_chat_workflow_to_document
from leagent.chat_workflow.runner import run_chat_workflow_step_via_engine
from leagent.chat_workflow.schema import ChatWorkflowSpec, ChatWorkflowStep, ChatWorkflowToolAction
from leagent.tools.base import ToolContext
from leagent.workflow.base import WorkflowResult, WorkflowStatus


def test_compile_linear_document() -> None:
    spec = ChatWorkflowSpec(
        title="Demo",
        steps=[
            ChatWorkflowStep(
                id="s1",
                label="Step 1",
                action=ChatWorkflowToolAction(tool_id="echo", arguments={"x": 1}),
            ),
            ChatWorkflowStep(
                id="s2",
                label="Step 2",
                action=ChatWorkflowToolAction(tool_id="echo", arguments={"y": 2}),
            ),
        ],
    )
    doc = compile_chat_workflow_to_document(spec)
    assert doc["start_id"] == "start"
    assert "s1" in doc["nodes"]
    assert doc["nodes"]["s1"]["class_type"] == "ToolCallNode"
    assert doc["nodes"]["s1"]["inputs"]["tool"] == "echo"
    assert any(e["source"] == "start" and e["target"] == "s1" for e in doc["edges"])
    assert any(e["target"] == "end" for e in doc["edges"])


def test_runner_imports_workflow_service_path() -> None:
    """Runner module must delegate to WorkflowService, not WorkflowExecutor."""
    runner_path = (
        Path(__file__).resolve().parents[1] / "leagent" / "chat_workflow" / "runner.py"
    )
    source = runner_path.read_text(encoding="utf-8")
    assert "run_compiled_document" in source
    assert "execute_async" not in source


async def test_runner_reads_workflow_result_outputs() -> None:
    """Runner must use the current WorkflowResult shape, not legacy result.state."""

    class _WorkflowService:
        async def run_compiled_document(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return {
                "prompt_id": "p1",
                "run_id": "r1",
                "result": WorkflowResult(
                    workflow_id="wf",
                    state_id=uuid4(),
                    status=WorkflowStatus.COMPLETED,
                    outputs={"s1": {"answer": 42}},
                ),
            }

    class _ServiceManager:
        workflow_service = _WorkflowService()

    spec = ChatWorkflowSpec(
        title="Demo",
        steps=[
            ChatWorkflowStep(
                id="s1",
                label="Step 1",
                action=ChatWorkflowToolAction(tool_id="echo", arguments={"x": 1}),
            ),
        ],
    )

    outcome = await run_chat_workflow_step_via_engine(
        spec=spec,
        step_id="s1",
        resolved_args={"x": 2},
        tool_ctx=ToolContext(user_id=str(uuid4()), session_id=str(uuid4())),
        service_manager=_ServiceManager(),
        user_id=str(uuid4()),
        session_id=str(uuid4()),
    )

    assert outcome.tool_result.success is True
    assert outcome.tool_result.data == {"answer": 42}
    assert outcome.prompt_id == "p1"
    assert outcome.run_id == "r1"
