"""Graph / flow definition schemas for the workflow visual editor."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class InputValue(BaseModel):
    """A single input value for a workflow node."""

    name: str
    value: Any = None
    type: str = "string"
    required: bool = False
    description: str = ""
    default: Any = None
    options: list[Any] | None = None


class Tweaks(BaseModel):
    """Runtime overrides applied to a flow before execution."""

    node_id: str
    field: str
    value: Any


class NodeData(BaseModel):
    """Data payload for a single node in a flow graph."""

    id: str
    type: str
    label: str = ""
    description: str = ""
    tool: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    inputs: list[InputValue] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    position: dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0})
    config: dict[str, Any] = Field(default_factory=dict)
    next_node: str | None = None
    on_error: str | None = None


class EdgeData(BaseModel):
    """A directed edge between two nodes."""

    id: str
    source: str
    target: str
    source_handle: str | None = None
    target_handle: str | None = None
    label: str = ""
    condition: str | None = None
    animated: bool = False


class FlowData(BaseModel):
    """Complete flow definition (nodes + edges)."""

    flow_id: str
    name: str
    description: str = ""
    version: str = "1.0"
    nodes: list[NodeData] = Field(default_factory=list)
    edges: list[EdgeData] = Field(default_factory=list)
    tweaks: list[Tweaks] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
