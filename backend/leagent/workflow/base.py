"""Base workflow engine classes: definitions, state management, and execution models.

This module provides the foundational abstractions for the workflow engine,
including node types, workflow definitions, edges, and state management.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

import structlog
from pydantic import BaseModel, Field, field_validator

logger = structlog.get_logger(__name__)


class NodeType(str, Enum):
    """Type of workflow node determining execution behavior."""

    START = "start"
    END = "end"
    TOOL_CALL = "tool_call"
    LLM_CALL = "llm_call"
    CONDITION = "condition"
    PARALLEL = "parallel"
    HUMAN_REVIEW = "human_review"
    ERROR_HANDLER = "error_handler"
    SUBWORKFLOW = "subworkflow"
    TRANSFORM = "transform"
    WAIT = "wait"


class WorkflowStatus(str, Enum):
    """Execution status of a workflow instance."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_HUMAN = "waiting_human"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class EdgeType(str, Enum):
    """Type of workflow edge for conditional routing."""

    DEFAULT = "default"
    CONDITIONAL = "conditional"
    ERROR = "error"


class ConditionOperator(str, Enum):
    """Operators for condition evaluation."""

    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GE = "ge"
    LT = "lt"
    LE = "le"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    MATCHES = "matches"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"
    AND = "and"
    OR = "or"
    NOT = "not"


class ConditionExpression(BaseModel):
    """A single condition expression for branching logic."""

    left: str
    operator: ConditionOperator
    right: Any = None
    conditions: list[ConditionExpression] | None = None

    def evaluate(self, context: dict[str, Any]) -> bool:
        """Evaluate the condition against a context dictionary."""
        if self.operator in (ConditionOperator.AND, ConditionOperator.OR, ConditionOperator.NOT):
            return self._evaluate_logical(context)
        return self._evaluate_comparison(context)

    def _evaluate_logical(self, context: dict[str, Any]) -> bool:
        if not self.conditions:
            return False

        if self.operator == ConditionOperator.AND:
            return all(c.evaluate(context) for c in self.conditions)
        elif self.operator == ConditionOperator.OR:
            return any(c.evaluate(context) for c in self.conditions)
        elif self.operator == ConditionOperator.NOT:
            return not self.conditions[0].evaluate(context) if self.conditions else False
        return False

    def _evaluate_comparison(self, context: dict[str, Any]) -> bool:
        left_value = _resolve_field(self.left, context)
        right_value = self.right
        if isinstance(right_value, str):
            resolved = _resolve_field(right_value, context)
            if resolved is not right_value and resolved != right_value:
                right_value = resolved

        left_value, right_value = _coerce_for_comparison(left_value, right_value)

        match self.operator:
            case ConditionOperator.EQ:
                return left_value == right_value
            case ConditionOperator.NE:
                return left_value != right_value
            case ConditionOperator.GT:
                return left_value > right_value if left_value is not None and right_value is not None else False
            case ConditionOperator.GE:
                return left_value >= right_value if left_value is not None and right_value is not None else False
            case ConditionOperator.LT:
                return left_value < right_value if left_value is not None and right_value is not None else False
            case ConditionOperator.LE:
                return left_value <= right_value if left_value is not None and right_value is not None else False
            case ConditionOperator.IN:
                return left_value in right_value if right_value is not None else False
            case ConditionOperator.NOT_IN:
                return left_value not in right_value if right_value is not None else True
            case ConditionOperator.CONTAINS:
                return right_value in left_value if left_value else False
            case ConditionOperator.STARTS_WITH:
                return str(left_value).startswith(str(right_value)) if left_value else False
            case ConditionOperator.ENDS_WITH:
                return str(left_value).endswith(str(right_value)) if left_value else False
            case ConditionOperator.MATCHES:
                return bool(re.match(str(right_value), str(left_value))) if left_value else False
            case ConditionOperator.IS_NULL:
                return left_value is None
            case ConditionOperator.IS_NOT_NULL:
                return left_value is not None
            case _:
                return False


class BranchCondition(BaseModel):
    """Condition and target for conditional branching."""

    if_expr: ConditionExpression
    then_node: str


class ParallelBranch(BaseModel):
    """A branch in a parallel execution node."""

    id: str
    name: str = ""
    nodes: list[str] = Field(default_factory=list)
    for_each: str | None = None
    output: str | None = None


class WorkflowNode(BaseModel):
    """Definition of a single workflow node."""

    id: str
    type: NodeType
    name: str = ""
    description: str = ""

    tool: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)

    prompt: str | None = None
    model: str | None = None
    temperature: float = 0.1
    max_tokens: int = 4096

    conditions: list[BranchCondition] = Field(default_factory=list)
    else_node: str | None = None

    branches: list[ParallelBranch] = Field(default_factory=list)
    merge_strategy: str = "collect"

    reviewer: str | None = None
    review_prompt: str | None = None
    timeout_sec: int = 86400
    on_reject: str | None = None

    transform: str | dict[str, Any] | None = None

    subworkflow_id: str | None = None
    subworkflow_inputs: dict[str, Any] = Field(default_factory=dict)

    output: str | None = None
    next: str | None = None
    error_handler: str | None = None
    retry_count: int = 0
    retry_delay_sec: int = 1

    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Node ID cannot be empty")
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_-]*$", v):
            raise ValueError(f"Invalid node ID format: {v}")
        return v


class WorkflowEdge(BaseModel):
    """Definition of a workflow edge connecting nodes."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    source: str
    target: str
    type: EdgeType = EdgeType.DEFAULT
    condition: ConditionExpression | None = None
    label: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowOutput(BaseModel):
    """Definition of a workflow output."""

    name: str
    value_expr: str
    description: str = ""


class WorkflowInput(BaseModel):
    """Definition of a workflow input parameter."""

    name: str
    type: str = "string"
    required: bool = True
    default: Any = None
    description: str = ""

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        valid_types = {"string", "number", "integer", "boolean", "array", "object", "any"}
        # Coerce extended YAML types to their canonical equivalents
        coerce_map = {
            "file": "string",
            "file[]": "array",
            "string[]": "array",
            "integer[]": "array",
            "number[]": "array",
            "object[]": "array",
            "boolean[]": "array",
            "datetime": "string",
            "date": "string",
            "time": "string",
            "url": "string",
            "email": "string",
            "uuid": "string",
            "json": "object",
        }
        normalized = coerce_map.get(v, v)
        if normalized not in valid_types:
            raise ValueError(f"Invalid input type: {v}. Must be one of {valid_types}")
        return normalized


class WorkflowDefinition(BaseModel):
    """Complete workflow definition including nodes, edges, and metadata."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    description: str = ""
    version: str = "1.0.0"

    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    inputs: list[WorkflowInput] = Field(default_factory=list)
    outputs: list[WorkflowOutput] = Field(default_factory=list)

    start_node: str = "start"
    end_node: str = "end"

    timeout_sec: int = 3600
    max_retries: int = 3

    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    _node_map: dict[str, WorkflowNode] = {}

    def model_post_init(self, __context: Any) -> None:
        """Build internal node map after initialization."""
        self._node_map = {node.id: node for node in self.nodes}

    def get_node(self, node_id: str) -> WorkflowNode | None:
        """Retrieve a node by ID."""
        return self._node_map.get(node_id)

    def get_start_node(self) -> WorkflowNode | None:
        """Get the workflow start node."""
        return self._node_map.get(self.start_node)

    def get_end_node(self) -> WorkflowNode | None:
        """Get the workflow end node."""
        return self._node_map.get(self.end_node)

    def get_outgoing_edges(self, node_id: str) -> list[WorkflowEdge]:
        """Get all edges originating from a node."""
        return [e for e in self.edges if e.source == node_id]

    def get_incoming_edges(self, node_id: str) -> list[WorkflowEdge]:
        """Get all edges targeting a node."""
        return [e for e in self.edges if e.target == node_id]

    def validate_structure(self) -> list[str]:
        """Validate workflow structure and return list of errors."""
        errors: list[str] = []

        if not self.nodes:
            errors.append("Workflow must have at least one node")
            return errors

        start_node = self.get_start_node()
        if not start_node:
            errors.append(f"Start node '{self.start_node}' not found")

        end_node = self.get_end_node()
        if not end_node:
            errors.append(f"End node '{self.end_node}' not found")

        node_ids = set(self._node_map.keys())
        for node in self.nodes:
            if node.next and node.next not in node_ids:
                errors.append(f"Node '{node.id}' references unknown next node '{node.next}'")

            if node.error_handler and node.error_handler not in node_ids:
                errors.append(f"Node '{node.id}' references unknown error handler '{node.error_handler}'")

            if node.else_node and node.else_node not in node_ids:
                errors.append(f"Node '{node.id}' references unknown else node '{node.else_node}'")

            if node.on_reject and node.on_reject not in node_ids:
                errors.append(f"Node '{node.id}' references unknown on_reject node '{node.on_reject}'")

            for cond in node.conditions:
                if cond.then_node not in node_ids:
                    errors.append(f"Node '{node.id}' condition references unknown node '{cond.then_node}'")

            for branch in node.branches:
                for branch_node in branch.nodes:
                    if branch_node not in node_ids:
                        errors.append(f"Node '{node.id}' branch '{branch.id}' references unknown node '{branch_node}'")

        for edge in self.edges:
            if edge.source not in node_ids:
                errors.append(f"Edge references unknown source node '{edge.source}'")
            if edge.target not in node_ids:
                errors.append(f"Edge references unknown target node '{edge.target}'")

        if not errors and start_node:
            visited: set[str] = set()
            self._detect_cycles(start_node.id, visited, [], errors)

        return errors

    # Node types that act as natural suspension/resume points, making cycles
    # through them legitimate retry/wait-loop patterns rather than bugs.
    _LOOP_SAFE_TYPES: set[str] = {"wait", "human_review"}

    def _detect_cycles(
        self,
        node_id: str,
        visited: set[str],
        path: list[str],
        errors: list[str],
    ) -> None:
        """Detect cycles in the workflow graph using DFS.

        Cycles that pass through suspension-point nodes (``wait``,
        ``human_review``) are allowed because they represent intentional
        retry/feedback loops common in enterprise workflows.
        """
        if node_id in path:
            cycle_path = path[path.index(node_id) :] + [node_id]
            cycle_types = {
                self.get_node(nid).type.value
                for nid in cycle_path
                if self.get_node(nid)
            }
            if cycle_types & self._LOOP_SAFE_TYPES:
                return
            cycle = " -> ".join(cycle_path)
            errors.append(f"Cycle detected: {cycle}")
            return

        if node_id in visited:
            return

        visited.add(node_id)
        path.append(node_id)

        node = self.get_node(node_id)
        if node:
            next_nodes: list[str] = []
            if node.next:
                next_nodes.append(node.next)
            for cond in node.conditions:
                next_nodes.append(cond.then_node)
            if node.else_node:
                next_nodes.append(node.else_node)
            for branch in node.branches:
                next_nodes.extend(branch.nodes)

            for next_id in next_nodes:
                self._detect_cycles(next_id, visited, path.copy(), errors)

        path.pop()


class NodeExecutionResult(BaseModel):
    """Result of executing a single workflow node."""

    node_id: str
    status: WorkflowStatus
    output: Any = None
    error: str | None = None
    duration_ms: int = 0
    next_node: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowState(BaseModel):
    """Runtime state for workflow execution."""

    id: UUID = Field(default_factory=uuid4)
    workflow_id: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    current_node: str | None = None

    inputs: dict[str, Any] = Field(default_factory=dict)
    variables: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)

    execution_history: list[NodeExecutionResult] = Field(default_factory=list)
    error_stack: list[str] = Field(default_factory=list)

    parent_state_id: UUID | None = None
    child_states: list[UUID] = Field(default_factory=list)

    retry_count: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    paused_at: datetime | None = None

    review_request_id: str | None = None
    review_data: dict[str, Any] = Field(default_factory=dict)

    metadata: dict[str, Any] = Field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a variable from state, supporting dot notation."""
        return _resolve_value(f"${{{key}}}", self._build_context(), default)

    def set(self, key: str, value: Any) -> None:
        """Set a variable in state."""
        if not key:
            return
        self.variables[key] = value
        logger.debug("workflow_state_set", key=key, value_type=type(value).__name__)

    def resolve_template(self, template: Any) -> Any:
        """Resolve template expressions in a value.

        Supports:
        - ${variable} - Simple variable reference
        - ${input.name} - Input field access
        - ${outputs.node_id.field} - Output field access
        """
        context = self._build_context()
        return _resolve_template(template, context)

    def evaluate_expression(self, expr: ConditionExpression) -> bool:
        """Evaluate a condition expression against current state."""
        context = self._build_context()
        return expr.evaluate(context)

    def fork(self, extra_vars: dict[str, Any] | None = None) -> WorkflowState:
        """Create a forked state for parallel execution."""
        forked = WorkflowState(
            workflow_id=self.workflow_id,
            status=WorkflowStatus.RUNNING,
            inputs=self.inputs.copy(),
            variables={**self.variables, **(extra_vars or {})},
            parent_state_id=self.id,
            started_at=datetime.utcnow(),
        )
        self.child_states.append(forked.id)
        return forked

    def merge_child_states(self, child_states: list[WorkflowState]) -> dict[str, Any]:
        """Merge results from child states back into parent."""
        results = {}
        for child in child_states:
            results[str(child.id)] = {
                "status": child.status.value,
                "outputs": child.outputs,
                "variables": child.variables,
            }
        return results

    def record_execution(self, result: NodeExecutionResult) -> None:
        """Record node execution result in history."""
        self.execution_history.append(result)
        if result.output is not None and result.node_id:
            self.outputs[result.node_id] = result.output

    def _build_context(self) -> dict[str, Any]:
        """Build context dictionary for template resolution.

        Variables and inputs are spread at the top level so condition
        expressions can reference them directly (e.g. ``left="amount"``),
        while namespaced access (``${variables.amount}``) also works.
        """
        ctx: dict[str, Any] = {}
        ctx.update(self.inputs)
        ctx.update(self.variables)
        ctx.update(self.outputs)
        ctx.update({
            "input": self.inputs,
            "inputs": self.inputs,
            "var": self.variables,
            "vars": self.variables,
            "variables": self.variables,
            "output": self.outputs,
            "outputs": self.outputs,
            "state": {
                "id": str(self.id),
                "workflow_id": self.workflow_id,
                "status": self.status.value,
                "current_node": self.current_node,
                "retry_count": self.retry_count,
            },
        })
        return ctx

    @property
    def elapsed_ms(self) -> int:
        """Calculate elapsed time in milliseconds."""
        if not self.started_at:
            return 0
        end_time = self.completed_at or datetime.utcnow()
        return int((end_time - self.started_at).total_seconds() * 1000)

    def to_summary(self) -> dict[str, Any]:
        """Generate execution summary."""
        return {
            "id": str(self.id),
            "workflow_id": self.workflow_id,
            "status": self.status.value,
            "elapsed_ms": self.elapsed_ms,
            "node_count": len(self.execution_history),
            "error_count": len(self.error_stack),
            "outputs": self.outputs,
        }


class WorkflowResult(BaseModel):
    """Final result of workflow execution."""

    workflow_id: str
    state_id: UUID
    status: WorkflowStatus
    outputs: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    execution_history: list[NodeExecutionResult] = Field(default_factory=list)
    duration_ms: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.status == WorkflowStatus.COMPLETED and not self.errors


TEMPLATE_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _resolve_field(expr: Any, context: dict[str, Any], default: Any = None) -> Any:
    """Resolve a field reference against context.

    Handles three forms:
    - Template expression: ``${path.to.value}``
    - Plain context key: ``"amount"`` (looked up as ``context["amount"]``)
    - Non-string literal: returned as-is
    """
    if not isinstance(expr, str):
        return expr

    match = TEMPLATE_PATTERN.fullmatch(expr)
    if match:
        path = match.group(1)
        return _get_nested_value(context, path, default)

    if expr in context:
        return context[expr]

    parts = expr.split(".")
    if len(parts) > 1:
        return _get_nested_value(context, expr, default)

    return expr


def _coerce_for_comparison(left: Any, right: Any) -> tuple[Any, Any]:
    """Coerce left and right values to compatible types for comparison."""
    if left is None or right is None:
        return left, right
    if type(left) is type(right):
        return left, right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return float(left), float(right)
    if isinstance(left, str) and isinstance(right, (int, float)):
        try:
            return float(left), float(right)
        except (ValueError, TypeError):
            return left, right
    if isinstance(left, (int, float)) and isinstance(right, str):
        try:
            return float(left), float(right)
        except (ValueError, TypeError):
            return left, right
    return left, right


def _resolve_value(expr: Any, context: dict[str, Any], default: Any = None) -> Any:
    """Resolve a value expression against context."""
    if not isinstance(expr, str):
        return expr

    match = TEMPLATE_PATTERN.fullmatch(expr)
    if match:
        path = match.group(1)
        return _get_nested_value(context, path, default)

    return expr


def _resolve_template(template: Any, context: dict[str, Any]) -> Any:
    """Recursively resolve all template expressions in a value."""
    if isinstance(template, str):
        if TEMPLATE_PATTERN.fullmatch(template):
            path = TEMPLATE_PATTERN.fullmatch(template).group(1)  # type: ignore
            return _get_nested_value(context, path)

        def replace_match(m: re.Match[str]) -> str:
            path = m.group(1)
            value = _get_nested_value(context, path)
            return str(value) if value is not None else m.group(0)

        return TEMPLATE_PATTERN.sub(replace_match, template)

    if isinstance(template, dict):
        return {k: _resolve_template(v, context) for k, v in template.items()}

    if isinstance(template, list):
        return [_resolve_template(item, context) for item in template]

    return template


def _get_nested_value(obj: dict[str, Any], path: str, default: Any = None) -> Any:
    """Get nested value from dictionary using dot notation."""
    parts = path.split(".")
    current: Any = obj

    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif hasattr(current, part):
            current = getattr(current, part)
        else:
            return default

        if current is None:
            return default

    return current
