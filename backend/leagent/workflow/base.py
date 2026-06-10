"""Runtime workflow models: status, condition evaluation, state, and results.

Workflow *structure* lives exclusively in the canonical document
(:mod:`leagent.workflow.io.loader`); this module only holds the runtime
data types the executor operates on.
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
