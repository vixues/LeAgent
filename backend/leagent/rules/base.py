"""Base classes for the rule engine."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field, field_validator


class RuleType(str, Enum):
    """Types of rule evaluations supported."""

    COMPARE = "compare"
    DATE_RANGE = "date_range"
    THRESHOLD = "threshold"
    CONTAINS_ALL = "contains_all"
    DATE_DIFF = "date_diff"
    REGEX_MATCH = "regex_match"
    CROSS_VALIDATE = "cross_validate"
    LLM_JUDGE = "llm_judge"


class Severity(str, Enum):
    """Rule violation severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Operator(str, Enum):
    """Comparison operators."""

    EQ = "=="
    NE = "!="
    LT = "<"
    GT = ">"
    LE = "<="
    GE = ">="
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"


@dataclass
class RuleResult:
    """Result of a single rule evaluation.

    Attributes:
        rule_id: Unique identifier of the rule.
        rule_name: Human-readable rule name.
        passed: Whether the rule passed.
        severity: Severity level if failed.
        message: Descriptive message (especially for failures).
        details: Additional context about the evaluation.
        execution_time_ms: Time taken to evaluate in milliseconds.
    """

    rule_id: str
    rule_name: str
    passed: bool
    severity: Severity = Severity.ERROR
    message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    execution_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "passed": self.passed,
            "severity": self.severity.value,
            "message": self.message,
            "details": self.details,
            "execution_time_ms": self.execution_time_ms,
        }


@dataclass
class RuleSetResult:
    """Aggregated result of evaluating a rule set.

    Attributes:
        rule_set_id: Identifier of the evaluated rule set.
        passed: True if no error-severity rules failed.
        total_rules: Total number of rules evaluated.
        error_count: Count of failed error-severity rules.
        warning_count: Count of failed warning-severity rules.
        info_count: Count of failed info-severity rules.
        results: Individual rule results.
        execution_time_ms: Total evaluation time in milliseconds.
    """

    rule_set_id: str
    passed: bool
    total_rules: int
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    results: list[RuleResult] = field(default_factory=list)
    execution_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_set_id": self.rule_set_id,
            "passed": self.passed,
            "total_rules": self.total_rules,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "results": [r.to_dict() for r in self.results],
            "execution_time_ms": self.execution_time_ms,
        }

    def get_failed_rules(self, severity: Severity | None = None) -> list[RuleResult]:
        """Get all failed rules, optionally filtered by severity."""
        failed = [r for r in self.results if not r.passed]
        if severity:
            failed = [r for r in failed if r.severity == severity]
        return failed


class RuleCondition(BaseModel):
    """Condition specification for a rule.

    The condition type determines which evaluator is used and what
    parameters are expected.
    """

    type: RuleType
    params: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


class RuleDefinition(BaseModel):
    """Complete definition of a single rule.

    Rules are loaded from YAML and define the evaluation logic,
    messages, and severity.
    """

    id: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=256)
    description: str | None = None
    condition: RuleCondition
    severity: Severity = Severity.ERROR
    message: str = Field(default="Rule validation failed")
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_-]*$", v):
            raise ValueError(
                "Rule ID must start with letter and contain only alphanumeric, underscore, hyphen"
            )
        return v


class RuleSet(BaseModel):
    """A collection of related rules.

    Rule sets are typically loaded from a single YAML file and
    represent logically grouped rules (e.g., "expense_validation").
    """

    id: str = Field(..., min_length=1, max_length=128)
    name: str = Field(..., min_length=1, max_length=256)
    description: str | None = None
    version: str = "1.0.0"
    rules: list[RuleDefinition] = Field(default_factory=list)
    enabled: bool = True
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_-]*$", v):
            raise ValueError(
                "RuleSet ID must start with letter and contain only alphanumeric, underscore, hyphen"
            )
        return v

    def get_enabled_rules(self) -> list[RuleDefinition]:
        """Return only enabled rules from this set."""
        return [r for r in self.rules if r.enabled]


class RuleEvaluator(ABC):
    """Abstract base class for rule evaluators.

    Each rule type has a corresponding evaluator that implements
    the evaluation logic.
    """

    rule_type: RuleType

    @abstractmethod
    def evaluate(
        self,
        params: dict[str, Any],
        data: dict[str, Any],
    ) -> tuple[bool, str | None, dict[str, Any]]:
        """Evaluate the rule condition.

        Args:
            params: Rule condition parameters (resolved from templates).
            data: Context data to evaluate against.

        Returns:
            Tuple of (passed, error_message, details_dict).
        """


class LogicalOperator(str, Enum):
    """Logical operators for combining conditions."""

    AND = "and"
    OR = "or"
    NOT = "not"


@dataclass
class CompositeCondition:
    """A composite condition combining multiple conditions with logical operators.

    Allows building complex rules like:
        (condition_a AND condition_b) OR (NOT condition_c)
    """

    operator: LogicalOperator
    conditions: list[RuleCondition | CompositeCondition] = field(default_factory=list)

    def add_condition(self, condition: RuleCondition | CompositeCondition) -> None:
        self.conditions.append(condition)

    @classmethod
    def and_all(cls, *conditions: RuleCondition | CompositeCondition) -> CompositeCondition:
        return cls(operator=LogicalOperator.AND, conditions=list(conditions))

    @classmethod
    def or_any(cls, *conditions: RuleCondition | CompositeCondition) -> CompositeCondition:
        return cls(operator=LogicalOperator.OR, conditions=list(conditions))

    @classmethod
    def negate(cls, condition: RuleCondition | CompositeCondition) -> CompositeCondition:
        return cls(operator=LogicalOperator.NOT, conditions=[condition])


def resolve_template(template: str, data: dict[str, Any]) -> Any:
    """Resolve a template string against data context.

    Template format: {{path.to.value}}
    Supports nested paths like {{user.profile.email}}

    Args:
        template: String potentially containing {{...}} placeholders.
        data: Dictionary to resolve values from.

    Returns:
        Resolved value (preserves type) or original template if no match.
    """
    if not isinstance(template, str):
        return template

    pattern = r"\{\{([^}]+)\}\}"
    matches = re.findall(pattern, template)

    if not matches:
        return template

    if len(matches) == 1 and template == f"{{{{{matches[0]}}}}}":
        return _get_nested_value(data, matches[0].strip())

    def replace_match(match: re.Match) -> str:
        path = match.group(1).strip()
        value = _get_nested_value(data, path)
        return str(value) if value is not None else ""

    return re.sub(pattern, replace_match, template)


def _get_nested_value(data: dict[str, Any], path: str) -> Any:
    """Get a value from nested dict using dot notation."""
    keys = path.split(".")
    current = data

    for key in keys:
        if isinstance(current, dict):
            if key in current:
                current = current[key]
            else:
                return None
        elif hasattr(current, key):
            current = getattr(current, key)
        else:
            return None

    return current


def resolve_all_templates(params: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    """Recursively resolve all templates in params dict."""
    resolved = {}
    for key, value in params.items():
        if isinstance(value, str):
            resolved[key] = resolve_template(value, data)
        elif isinstance(value, dict):
            resolved[key] = resolve_all_templates(value, data)
        elif isinstance(value, list):
            resolved[key] = [
                resolve_template(v, data) if isinstance(v, str) else v for v in value
            ]
        else:
            resolved[key] = value
    return resolved
