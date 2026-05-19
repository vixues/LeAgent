"""Pydantic request/response models for the workflow server."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class FlowRunRequest(BaseModel):
    input_data: Optional[dict[str, Any]] = Field(default=None)
    priority: int = Field(default=5, ge=0, le=10, description="0=highest, 10=lowest")
    trigger_type: str = "manual"
    session_id: Optional[UUID] = None
    extra_data: dict[str, Any] = Field(default_factory=dict)


class FlowRunResponse(BaseModel):
    execution_id: UUID
    prompt_id: str
    flow_id: UUID
    status: str = "queued"
    queue_position: Optional[int] = None
    message: str = "Workflow execution queued"


class WorkflowExecutionSummary(BaseModel):
    id: UUID
    flow_id: Optional[UUID]
    status: str
    trigger_type: str
    node_count: int = 0
    duration_ms: int = 0
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime


class WorkflowExecutionDetail(WorkflowExecutionSummary):
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    execution_history: list[dict[str, Any]] = Field(default_factory=list)
    current_node: Optional[str] = None


class FlowValidateRequest(BaseModel):
    data: dict[str, Any]


class FlowValidateResponse(BaseModel):
    ok: bool
    output_nodes: list[str] = Field(default_factory=list)
    errors: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


class FlowExportResponse(BaseModel):
    flow_id: UUID
    name: str
    document: dict[str, Any]


class FlowImportRequest(BaseModel):
    name: Optional[str] = None
    document: dict[str, Any]
    folder_id: Optional[UUID] = None


class FlowImportResponse(BaseModel):
    flow_id: UUID
    name: str
    node_count: int


class FlowDuplicateResponse(BaseModel):
    flow_id: UUID
    name: str


class FlowBuildRequest(BaseModel):
    """``build`` compiles a document into a validated graph hash without running it."""

    data: Optional[dict[str, Any]] = None


class FlowBuildResponse(BaseModel):
    ok: bool
    graph_hash: str
    node_count: int
    output_nodes: list[str] = Field(default_factory=list)


class NodeReplacementEntry(BaseModel):
    old_class: str
    new_class: str
    reason: str = ""


class NodeReloadResponse(BaseModel):
    registered: dict[str, list[str]]


class ExecutionStatusEvent(BaseModel):
    type: str
    prompt_id: str
    node_id: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)


class ObjectInfoResponse(BaseModel):
    """Alias over the raw node snapshot; typed for documentation."""

    nodes: dict[str, dict[str, Any]]
