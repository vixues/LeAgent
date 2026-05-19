"""Rule engine exceptions."""

from __future__ import annotations

from leagent.exceptions.base import LeAgentError


class RuleError(LeAgentError):
    """Base exception for rule engine errors."""

    error_code = "RULE_ERROR"
    status_code = 500


class RuleValidationError(RuleError):
    """Invalid rule definition or structure."""

    error_code = "RULE_VALIDATION_ERROR"
    status_code = 422


class RuleEvaluationError(RuleError):
    """Error during rule evaluation."""

    error_code = "RULE_EVALUATION_ERROR"
    status_code = 500


class RuleSetNotFoundError(RuleError):
    """Rule set not found."""

    error_code = "RULE_SET_NOT_FOUND"
    status_code = 404


class RuleLoadError(RuleError):
    """Error loading rules from file."""

    error_code = "RULE_LOAD_ERROR"
    status_code = 500
