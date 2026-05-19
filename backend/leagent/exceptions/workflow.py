"""Workflow engine exceptions."""

from __future__ import annotations

from typing import Any

from leagent.exceptions.base import LeAgentError


class WorkflowError(LeAgentError):
    """Generic workflow execution failure."""

    error_code = "WORKFLOW_ERROR"
    status_code = 500

    def __init__(
        self,
        message: str = "Workflow execution failed",
        *,
        workflow_id: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = {**(details or {}), "workflow_id": workflow_id}
        super().__init__(message, details=merged)
        self.workflow_id = workflow_id


class WorkflowNodeError(WorkflowError):
    """A specific workflow node failed."""

    error_code = "WORKFLOW_NODE_ERROR"

    def __init__(
        self,
        message: str = "Workflow node failed",
        *,
        workflow_id: str = "",
        node_id: str = "",
        node_type: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = {
            **(details or {}),
            "node_id": node_id,
            "node_type": node_type,
        }
        super().__init__(message, workflow_id=workflow_id, details=merged)
        self.node_id = node_id
        self.node_type = node_type


class WorkflowTimeoutError(WorkflowError):
    """Workflow execution exceeded the allowed timeout."""

    error_code = "WORKFLOW_TIMEOUT"
    status_code = 504

    def __init__(
        self,
        workflow_id: str = "",
        timeout_sec: int = 0,
    ) -> None:
        super().__init__(
            f"Workflow timed out after {timeout_sec}s",
            workflow_id=workflow_id,
            details={"timeout_sec": timeout_sec},
        )


class WorkflowValidationError(WorkflowError):
    """Workflow definition is invalid."""

    error_code = "WORKFLOW_VALIDATION_ERROR"
    status_code = 422

    def __init__(
        self,
        message: str = "Invalid workflow definition",
        *,
        workflow_id: str = "",
        errors: list[str] | None = None,
    ) -> None:
        super().__init__(
            message,
            workflow_id=workflow_id,
            details={"validation_errors": errors or []},
        )
