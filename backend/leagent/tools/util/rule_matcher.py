"""Rule Matcher Tool - Pattern matching and rule evaluation.

Provides operations for matching data against rule sets,
evaluating conditions, and aggregating results.
"""

from __future__ import annotations

import operator
import re
from typing import Any, Callable

import structlog

from leagent.tools.base import SyncTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)

OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "eq": operator.eq,
    "ne": operator.ne,
    "lt": operator.lt,
    "le": operator.le,
    "gt": operator.gt,
    "ge": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
    "contains": lambda a, b: b in a if isinstance(a, (str, list, dict)) else False,
    "not_contains": lambda a, b: b not in a if isinstance(a, (str, list, dict)) else True,
    "starts_with": lambda a, b: str(a).startswith(str(b)),
    "ends_with": lambda a, b: str(a).endswith(str(b)),
    "matches": lambda a, b: bool(re.search(b, str(a))) if b else False,
    "is_null": lambda a, _: a is None,
    "is_not_null": lambda a, _: a is not None,
    "is_empty": lambda a, _: not a if isinstance(a, (str, list, dict)) else a is None,
    "is_not_empty": lambda a, _: bool(a) if isinstance(a, (str, list, dict)) else a is not None,
    "between": lambda a, b: b[0] <= a <= b[1] if isinstance(b, (list, tuple)) and len(b) == 2 else False,
}


class RuleMatcherTool(SyncTool):
    """Match data against rule sets and evaluate conditions.

    Features:
    - Evaluate single or multiple rules
    - Support various comparison operators
    - Logical operators (AND, OR, NOT)
    - Nested rule evaluation
    - Result aggregation and scoring
    - Rule validation
    """

    name = "rule_matcher"
    description = (
        "Match data against rule sets, evaluate conditions with various operators "
        "(eq, ne, lt, gt, contains, matches, etc.), and aggregate results."
    )
    category = ToolCategory.UTIL
    version = "1.0.0"
    timeout_sec = 60
    aliases = ["rules", "rule_eval", "match_rules"]
    search_hint = "rule match evaluate condition operator aggregate filter"
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 100_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Matching rules"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["evaluate", "match_all", "match_any", "score", "validate", "filter"],
                    "description": "Rule matching operation to perform.",
                    "default": "evaluate",
                },
                "data": {
                    "type": "object",
                    "description": "Data object to evaluate against rules.",
                },
                "data_list": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "List of data objects for filter/batch operations.",
                },
                "rules": {
                    "type": "array",
                    "description": "List of rules to evaluate.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Rule identifier."},
                            "field": {"type": "string", "description": "Field path to evaluate (dot notation)."},
                            "operator": {
                                "type": "string",
                                "enum": list(OPERATORS.keys()),
                                "description": "Comparison operator.",
                            },
                            "value": {"description": "Value to compare against."},
                            "weight": {"type": "number", "description": "Rule weight for scoring.", "default": 1.0},
                            "message": {"type": "string", "description": "Message when rule matches/fails."},
                            "required": {"type": "boolean", "description": "Whether rule must match.", "default": False},
                        },
                        "required": ["field", "operator"],
                    },
                },
                "rule_set": {
                    "type": "object",
                    "description": "Named rule set with logical grouping.",
                    "properties": {
                        "name": {"type": "string"},
                        "logic": {"type": "string", "enum": ["and", "or"], "default": "and"},
                        "rules": {"type": "array", "items": {"type": "object"}},
                        "groups": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "logic": {"type": "string", "enum": ["and", "or"]},
                                    "rules": {"type": "array"},
                                },
                            },
                        },
                    },
                },
                "stop_on_first_match": {
                    "type": "boolean",
                    "description": "Stop evaluation after first matching rule.",
                    "default": False,
                },
                "stop_on_first_failure": {
                    "type": "boolean",
                    "description": "Stop evaluation after first failing rule.",
                    "default": False,
                },
                "include_unmatched": {
                    "type": "boolean",
                    "description": "Include unmatched rules in results.",
                    "default": True,
                },
            },
            "required": ["operation"],
            "additionalProperties": False,
        }

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Execute rule matching operation.

        Args:
            params: Tool parameters including operation, data, and rules.
            context: Execution context.

        Returns:
            Dictionary containing matching results.

        Raises:
            ValueError: If parameters are invalid.
        """
        operation = params.get("operation", "evaluate")

        logger.info("Executing rule matching", operation=operation)

        operations = {
            "evaluate": self._evaluate_rules,
            "match_all": self._match_all,
            "match_any": self._match_any,
            "score": self._score_rules,
            "validate": self._validate_rules,
            "filter": self._filter_data,
        }

        if operation not in operations:
            raise ValueError(f"Unknown operation: {operation}")

        result = operations[operation](params)

        logger.info("Rule matching complete", operation=operation)
        return result

    def _get_field_value(self, data: dict[str, Any], field_path: str) -> Any:
        """Get value from nested data using dot notation."""
        if not data or not field_path:
            return None

        parts = field_path.split(".")
        value = data

        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            elif isinstance(value, list):
                try:
                    idx = int(part)
                    value = value[idx] if 0 <= idx < len(value) else None
                except (ValueError, IndexError):
                    return None
            else:
                return None

            if value is None:
                return None

        return value

    def _evaluate_condition(self, value: Any, op: str, compare_value: Any) -> bool:
        """Evaluate a single condition."""
        if op not in OPERATORS:
            raise ValueError(f"Unknown operator: {op}")

        try:
            return OPERATORS[op](value, compare_value)
        except (TypeError, ValueError):
            return False

    def _evaluate_single_rule(self, data: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any]:
        """Evaluate a single rule against data."""
        field = rule.get("field", "")
        op = rule.get("operator", "eq")
        compare_value = rule.get("value")

        actual_value = self._get_field_value(data, field)
        matched = self._evaluate_condition(actual_value, op, compare_value)

        result: dict[str, Any] = {
            "rule_id": rule.get("id"),
            "field": field,
            "operator": op,
            "expected": compare_value,
            "actual": actual_value,
            "matched": matched,
        }

        if "message" in rule:
            result["message"] = rule["message"]
        if "weight" in rule:
            result["weight"] = rule["weight"]

        return result

    def _evaluate_rules(self, params: dict[str, Any]) -> dict[str, Any]:
        """Evaluate all rules against data."""
        data = params.get("data", {})
        rules = params.get("rules", [])
        rule_set = params.get("rule_set")
        stop_on_first_match = params.get("stop_on_first_match", False)
        stop_on_first_failure = params.get("stop_on_first_failure", False)
        include_unmatched = params.get("include_unmatched", True)

        if rule_set:
            return self._evaluate_rule_set(data, rule_set)

        if not rules:
            raise ValueError("Either 'rules' or 'rule_set' is required")

        results = []
        matched_count = 0
        failed_required = False

        for rule in rules:
            evaluation = self._evaluate_single_rule(data, rule)
            
            if evaluation["matched"]:
                matched_count += 1
                if stop_on_first_match:
                    results.append(evaluation)
                    break
            else:
                if rule.get("required", False):
                    failed_required = True
                if stop_on_first_failure:
                    results.append(evaluation)
                    break

            if include_unmatched or evaluation["matched"]:
                results.append(evaluation)

        return {
            "data": data,
            "results": results,
            "summary": {
                "total_rules": len(rules),
                "matched": matched_count,
                "unmatched": len(rules) - matched_count,
                "all_matched": matched_count == len(rules),
                "any_matched": matched_count > 0,
                "failed_required": failed_required,
            },
        }

    def _evaluate_rule_set(self, data: dict[str, Any], rule_set: dict[str, Any]) -> dict[str, Any]:
        """Evaluate a rule set with logical grouping."""
        name = rule_set.get("name", "unnamed")
        logic = rule_set.get("logic", "and")
        rules = rule_set.get("rules", [])
        groups = rule_set.get("groups", [])

        results = []
        for rule in rules:
            results.append(self._evaluate_single_rule(data, rule))

        group_results = []
        for group in groups:
            group_logic = group.get("logic", "and")
            group_rules = group.get("rules", [])
            group_evals = [self._evaluate_single_rule(data, r) for r in group_rules]
            
            if group_logic == "and":
                group_matched = all(e["matched"] for e in group_evals)
            else:
                group_matched = any(e["matched"] for e in group_evals)

            group_results.append({
                "logic": group_logic,
                "matched": group_matched,
                "evaluations": group_evals,
            })

        all_rule_matches = [r["matched"] for r in results]
        all_group_matches = [g["matched"] for g in group_results]
        all_matches = all_rule_matches + all_group_matches

        if logic == "and":
            overall_matched = all(all_matches) if all_matches else True
        else:
            overall_matched = any(all_matches) if all_matches else False

        return {
            "rule_set": name,
            "logic": logic,
            "matched": overall_matched,
            "rule_results": results,
            "group_results": group_results,
        }

    def _match_all(self, params: dict[str, Any]) -> dict[str, Any]:
        """Check if all rules match."""
        result = self._evaluate_rules(params)
        result["all_matched"] = result["summary"]["all_matched"]
        return result

    def _match_any(self, params: dict[str, Any]) -> dict[str, Any]:
        """Check if any rule matches."""
        result = self._evaluate_rules(params)
        result["any_matched"] = result["summary"]["any_matched"]
        return result

    def _score_rules(self, params: dict[str, Any]) -> dict[str, Any]:
        """Calculate weighted score based on matching rules."""
        data = params.get("data", {})
        rules = params.get("rules", [])

        if not rules:
            raise ValueError("Rules are required for scoring")

        total_weight = 0.0
        earned_weight = 0.0
        results = []

        for rule in rules:
            evaluation = self._evaluate_single_rule(data, rule)
            weight = rule.get("weight", 1.0)
            total_weight += weight

            if evaluation["matched"]:
                earned_weight += weight

            results.append(evaluation)

        score = (earned_weight / total_weight * 100) if total_weight > 0 else 0

        return {
            "data": data,
            "results": results,
            "scoring": {
                "score": round(score, 2),
                "earned_weight": earned_weight,
                "total_weight": total_weight,
                "percentage": round(score, 2),
            },
        }

    def _validate_rules(self, params: dict[str, Any]) -> dict[str, Any]:
        """Validate rule syntax without evaluating against data."""
        rules = params.get("rules", [])
        rule_set = params.get("rule_set")

        validation_results = []
        valid_count = 0

        rules_to_validate = rules
        if rule_set:
            rules_to_validate = rule_set.get("rules", [])
            for group in rule_set.get("groups", []):
                rules_to_validate.extend(group.get("rules", []))

        for i, rule in enumerate(rules_to_validate):
            errors = []

            if "field" not in rule:
                errors.append("Missing required field: 'field'")
            if "operator" not in rule:
                errors.append("Missing required field: 'operator'")
            elif rule["operator"] not in OPERATORS:
                errors.append(f"Invalid operator: {rule['operator']}")

            is_valid = len(errors) == 0
            if is_valid:
                valid_count += 1

            validation_results.append({
                "index": i,
                "rule_id": rule.get("id"),
                "valid": is_valid,
                "errors": errors,
            })

        return {
            "results": validation_results,
            "summary": {
                "total": len(rules_to_validate),
                "valid": valid_count,
                "invalid": len(rules_to_validate) - valid_count,
                "all_valid": valid_count == len(rules_to_validate),
            },
            "available_operators": list(OPERATORS.keys()),
        }

    def _filter_data(self, params: dict[str, Any]) -> dict[str, Any]:
        """Filter data list based on rules."""
        data_list = params.get("data_list", [])
        rules = params.get("rules", [])
        rule_set = params.get("rule_set")

        if not data_list:
            return {
                "matched": [],
                "unmatched": [],
                "summary": {"total": 0, "matched": 0, "unmatched": 0},
            }

        matched = []
        unmatched = []

        for item in data_list:
            if rule_set:
                result = self._evaluate_rule_set(item, rule_set)
                is_match = result["matched"]
            else:
                item_params = {"data": item, "rules": rules}
                result = self._evaluate_rules(item_params)
                is_match = result["summary"]["all_matched"]

            if is_match:
                matched.append(item)
            else:
                unmatched.append(item)

        return {
            "matched": matched,
            "unmatched": unmatched,
            "summary": {
                "total": len(data_list),
                "matched": len(matched),
                "unmatched": len(unmatched),
                "match_rate": round(len(matched) / len(data_list) * 100, 2) if data_list else 0,
            },
        }
