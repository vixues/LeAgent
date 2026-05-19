"""Rule evaluators for different rule types."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog

from leagent.exceptions.rule import RuleEvaluationError
from leagent.rules.base import Operator, RuleEvaluator, RuleType

if TYPE_CHECKING:
    from leagent.llm.service import LLMService

logger = structlog.get_logger(__name__)


_FALLBACK_RULE_JUDGE_PROMPT = (
    "You are a rule evaluation judge. Analyze the given data and criteria "
    "to determine if the rule passes or fails.\n\n"
    "Respond ONLY with a valid JSON object in this exact format:\n"
    "{\n"
    '    "pass": true/false,\n'
    '    "reason": "Brief explanation",\n'
    '    "confidence": 0.0-1.0\n'
    "}\n\n"
    "Be strict and objective in your evaluation."
)


def _load_rule_judge_prompt() -> str:
    """Fetch the ``rule_judge`` template from the prompt registry.

    Falls back to the legacy inline string when the registry or template
    file is unavailable (e.g. unit tests that stub out
    :mod:`leagent.prompts`) so judge evaluation degrades gracefully
    instead of raising in production.
    """
    try:
        from leagent.prompts import get_prompt_registry

        variant = get_prompt_registry().get("rule_judge")
        body = (variant.body or "").strip()
        return body or _FALLBACK_RULE_JUDGE_PROMPT
    except Exception as exc:  # noqa: BLE001 — optional dependency
        logger.debug("rule_judge_template_missing", error=str(exc))
        return _FALLBACK_RULE_JUDGE_PROMPT


def _parse_date(value: Any) -> date | datetime:
    """Parse various date formats into datetime or date objects."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())

    if not isinstance(value, str):
        raise RuleEvaluationError(
            f"Cannot parse date from type {type(value).__name__}",
            details={"value": str(value)},
        )

    formats = [
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue

    raise RuleEvaluationError(
        f"Unable to parse date: {value}",
        details={"value": value, "supported_formats": formats},
    )


def _to_comparable(value: Any) -> Any:
    """Convert value to comparable type for comparisons."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return value.lower()
    return value


class CompareEvaluator(RuleEvaluator):
    """Evaluator for comparison operations (==, !=, <, >, <=, >=, in, not_in)."""

    rule_type = RuleType.COMPARE

    OPERATORS: dict[str, Any] = {
        "==": lambda a, b: a == b,
        "!=": lambda a, b: a != b,
        "<": lambda a, b: a < b,
        ">": lambda a, b: a > b,
        "<=": lambda a, b: a <= b,
        ">=": lambda a, b: a >= b,
        "in": lambda a, b: a in (b if isinstance(b, (list, tuple, set)) else [b]),
        "not_in": lambda a, b: a not in (b if isinstance(b, (list, tuple, set)) else [b]),
        "contains": lambda a, b: b in a if isinstance(a, (str, list, tuple, set)) else False,
        "not_contains": lambda a, b: b not in a if isinstance(a, (str, list, tuple, set)) else True,
    }

    def evaluate(
        self,
        params: dict[str, Any],
        data: dict[str, Any],
    ) -> tuple[bool, str | None, dict[str, Any]]:
        """Evaluate a comparison condition.

        Params accept two conventions:
            - ``field`` / ``value`` — field is resolved from *data*
            - ``left`` / ``right`` — used as literals unless they match data keys
        """
        field = params.get("field")
        if field is not None:
            left = data.get(field, params.get("left"))
            right = params.get("value", params.get("right"))
        else:
            left = params.get("left")
            right = params.get("right")
        operator = params.get("operator", "==")

        if operator not in self.OPERATORS:
            raise RuleEvaluationError(
                f"Unknown operator: {operator}",
                details={"supported_operators": list(self.OPERATORS.keys())},
            )

        left_comparable = _to_comparable(left)
        right_comparable = _to_comparable(right)

        try:
            passed = self.OPERATORS[operator](left_comparable, right_comparable)
        except TypeError as e:
            return False, f"Type comparison error: {e}", {
                "left": left,
                "right": right,
                "operator": operator,
            }

        details = {
            "left": left,
            "right": right,
            "operator": operator,
            "compared_as": {"left": left_comparable, "right": right_comparable},
        }

        if not passed:
            return False, f"Comparison failed: {left} {operator} {right}", details

        return True, None, details


class DateRangeEvaluator(RuleEvaluator):
    """Evaluator for checking if a date falls within a range."""

    rule_type = RuleType.DATE_RANGE

    def evaluate(
        self,
        params: dict[str, Any],
        data: dict[str, Any],
    ) -> tuple[bool, str | None, dict[str, Any]]:
        """Evaluate if date is within range.

        Required params:
            - date: The date to check
            - start: Range start (inclusive)
            - end: Range end (inclusive)

        Optional params:
            - inclusive_start: Whether start is inclusive (default: True)
            - inclusive_end: Whether end is inclusive (default: True)
        """
        date_val = _parse_date(params.get("date"))
        start = _parse_date(params.get("start"))
        end = _parse_date(params.get("end"))

        inclusive_start = params.get("inclusive_start", True)
        inclusive_end = params.get("inclusive_end", True)

        details = {
            "date": date_val.isoformat(),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "inclusive_start": inclusive_start,
            "inclusive_end": inclusive_end,
        }

        start_ok = date_val >= start if inclusive_start else date_val > start
        end_ok = date_val <= end if inclusive_end else date_val < end

        passed = start_ok and end_ok

        if not passed:
            message = f"Date {date_val.date()} is not within range [{start.date()}, {end.date()}]"
            return False, message, details

        return True, None, details


class ThresholdEvaluator(RuleEvaluator):
    """Evaluator for numeric threshold checks."""

    rule_type = RuleType.THRESHOLD

    def evaluate(
        self,
        params: dict[str, Any],
        data: dict[str, Any],
    ) -> tuple[bool, str | None, dict[str, Any]]:
        """Evaluate if value is within thresholds.

        Required params:
            - value: The numeric value to check

        Optional params:
            - min: Minimum allowed value (inclusive)
            - max: Maximum allowed value (inclusive)
            - min_exclusive: Minimum value (exclusive)
            - max_exclusive: Maximum value (exclusive)
        """
        try:
            value = float(params.get("value", 0))
        except (ValueError, TypeError) as e:
            return False, f"Cannot convert value to number: {e}", {"raw_value": params.get("value")}

        details: dict[str, Any] = {"value": value}
        violations = []

        if "min" in params:
            min_val = float(params["min"])
            details["min"] = min_val
            if value < min_val:
                violations.append(f"value {value} is below minimum {min_val}")

        if "max" in params:
            max_val = float(params["max"])
            details["max"] = max_val
            if value > max_val:
                violations.append(f"value {value} exceeds maximum {max_val}")

        if "min_exclusive" in params:
            min_ex = float(params["min_exclusive"])
            details["min_exclusive"] = min_ex
            if value <= min_ex:
                violations.append(f"value {value} must be greater than {min_ex}")

        if "max_exclusive" in params:
            max_ex = float(params["max_exclusive"])
            details["max_exclusive"] = max_ex
            if value >= max_ex:
                violations.append(f"value {value} must be less than {max_ex}")

        if violations:
            return False, "; ".join(violations), details

        return True, None, details


class ContainsAllEvaluator(RuleEvaluator):
    """Evaluator for checking if a collection contains all required items."""

    rule_type = RuleType.CONTAINS_ALL

    def evaluate(
        self,
        params: dict[str, Any],
        data: dict[str, Any],
    ) -> tuple[bool, str | None, dict[str, Any]]:
        """Evaluate if source contains all required items.

        Required params:
            - source: The collection to check (list, set, or dict keys)
            - required: Items that must be present

        Optional params:
            - case_sensitive: Whether to do case-sensitive comparison (default: True)
        """
        source = params.get("source", [])
        required = params.get("required", [])
        case_sensitive = params.get("case_sensitive", True)

        if isinstance(source, dict):
            source = list(source.keys())
        elif isinstance(source, str):
            source = [source]

        if isinstance(required, str):
            required = [required]

        if not case_sensitive:
            source_set = {str(s).lower() for s in source}
            required_set = {str(r).lower() for r in required}
        else:
            source_set = set(source)
            required_set = set(required)

        missing = required_set - source_set
        details = {
            "source": list(source),
            "required": list(required),
            "missing": list(missing),
            "case_sensitive": case_sensitive,
        }

        if missing:
            return False, f"Missing required items: {missing}", details

        return True, None, details


class RegexMatchEvaluator(RuleEvaluator):
    """Evaluator for regex pattern matching."""

    rule_type = RuleType.REGEX_MATCH

    def evaluate(
        self,
        params: dict[str, Any],
        data: dict[str, Any],
    ) -> tuple[bool, str | None, dict[str, Any]]:
        """Evaluate if value matches regex pattern.

        Required params:
            - value: The string to match
            - pattern: The regex pattern

        Optional params:
            - flags: Regex flags (i=ignore case, m=multiline, s=dotall)
            - must_match: Whether it must match (True) or must not match (False)
        """
        value = str(params.get("value", ""))
        pattern = params.get("pattern", "")
        flags_str = params.get("flags", "")
        must_match = params.get("must_match", True)

        flags = 0
        if "i" in flags_str:
            flags |= re.IGNORECASE
        if "m" in flags_str:
            flags |= re.MULTILINE
        if "s" in flags_str:
            flags |= re.DOTALL

        details = {
            "value": value[:200] if len(value) > 200 else value,
            "pattern": pattern,
            "flags": flags_str,
            "must_match": must_match,
        }

        try:
            match = re.search(pattern, value, flags)
            matched = match is not None
        except re.error as e:
            return False, f"Invalid regex pattern: {e}", details

        if must_match:
            if not matched:
                return False, f"Value does not match pattern '{pattern}'", details
        else:
            if matched:
                return False, f"Value should not match pattern '{pattern}'", details

        if match:
            details["matched_text"] = match.group()
            details["match_span"] = match.span()

        return True, None, details


class DateDiffEvaluator(RuleEvaluator):
    """Evaluator for checking date differences."""

    rule_type = RuleType.DATE_DIFF

    def evaluate(
        self,
        params: dict[str, Any],
        data: dict[str, Any],
    ) -> tuple[bool, str | None, dict[str, Any]]:
        """Evaluate if date difference is within bounds.

        Required params:
            - from_date: Start date
            - to_date: End date

        Optional params:
            - max_days: Maximum allowed difference in days
            - min_days: Minimum required difference in days
            - unit: Difference unit (days, hours, minutes) - default: days
        """
        from_date = _parse_date(params.get("from_date"))
        to_date = _parse_date(params.get("to_date"))
        unit = params.get("unit", "days")

        delta = to_date - from_date

        if unit == "hours":
            diff_value = delta.total_seconds() / 3600
        elif unit == "minutes":
            diff_value = delta.total_seconds() / 60
        else:
            diff_value = delta.days

        details = {
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "diff_value": diff_value,
            "unit": unit,
        }

        violations = []

        if "max_days" in params:
            max_val = float(params["max_days"])
            details["max_days"] = max_val
            if diff_value > max_val:
                violations.append(f"Difference of {diff_value} {unit} exceeds maximum {max_val}")

        if "min_days" in params:
            min_val = float(params["min_days"])
            details["min_days"] = min_val
            if diff_value < min_val:
                violations.append(f"Difference of {diff_value} {unit} is below minimum {min_val}")

        if violations:
            return False, "; ".join(violations), details

        return True, None, details


class CrossValidateEvaluator(RuleEvaluator):
    """Evaluator for cross-field validation."""

    rule_type = RuleType.CROSS_VALIDATE

    def evaluate(
        self,
        params: dict[str, Any],
        data: dict[str, Any],
    ) -> tuple[bool, str | None, dict[str, Any]]:
        """Evaluate cross-field validation rules.

        Required params:
            - fields: List of field paths to validate together
            - validation_type: Type of cross-validation

        Supported validation_types:
            - all_equal: All fields must have equal values
            - all_different: All fields must have different values
            - sum_equals: Sum of numeric fields must equal target
            - at_least_one_present: At least one field must be non-empty
            - all_present: All fields must be non-empty
            - mutex: Only one field can be non-empty
            - conditional: If condition field has value, then other fields required
        """
        fields = params.get("fields", [])
        validation_type = params.get("validation_type", "all_present")

        details = {
            "fields": fields,
            "validation_type": validation_type,
            "field_values": {},
        }

        field_values = {}
        for field_path in fields:
            value = self._get_field_value(data, field_path)
            field_values[field_path] = value
            details["field_values"][field_path] = value

        if validation_type == "all_equal":
            values = list(field_values.values())
            if len(set(map(str, values))) > 1:
                return False, f"Fields have different values: {field_values}", details

        elif validation_type == "all_different":
            values = list(field_values.values())
            if len(values) != len(set(map(str, values))):
                return False, f"Some fields have duplicate values: {field_values}", details

        elif validation_type == "sum_equals":
            target = params.get("target", 0)
            try:
                total = sum(float(v) for v in field_values.values() if v is not None)
            except (ValueError, TypeError) as e:
                return False, f"Cannot sum non-numeric fields: {e}", details
            details["sum"] = total
            details["target"] = target
            if abs(total - float(target)) > 1e-9:
                return False, f"Sum {total} does not equal target {target}", details

        elif validation_type == "at_least_one_present":
            if not any(self._is_present(v) for v in field_values.values()):
                return False, "At least one field must be present", details

        elif validation_type == "all_present":
            missing = [f for f, v in field_values.items() if not self._is_present(v)]
            if missing:
                details["missing_fields"] = missing
                return False, f"Missing required fields: {missing}", details

        elif validation_type == "mutex":
            present = [f for f, v in field_values.items() if self._is_present(v)]
            if len(present) > 1:
                details["multiple_present"] = present
                return False, f"Only one field should be present, found: {present}", details

        elif validation_type == "conditional":
            condition_field = params.get("condition_field")
            condition_value = params.get("condition_value")
            required_fields = params.get("required_fields", [])

            condition_actual = self._get_field_value(data, condition_field)
            details["condition_field"] = condition_field
            details["condition_value"] = condition_value
            details["condition_actual"] = condition_actual

            if condition_actual == condition_value:
                missing = [
                    f for f in required_fields
                    if not self._is_present(self._get_field_value(data, f))
                ]
                if missing:
                    details["missing_conditional"] = missing
                    return (
                        False,
                        f"When {condition_field}={condition_value}, these fields are required: {missing}",
                        details,
                    )

        return True, None, details

    def _get_field_value(self, data: dict[str, Any], path: str) -> Any:
        """Get value from nested data using dot notation."""
        keys = path.split(".")
        current = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current

    def _is_present(self, value: Any) -> bool:
        """Check if a value is considered 'present' (not empty)."""
        if value is None:
            return False
        if isinstance(value, str) and not value.strip():
            return False
        if isinstance(value, (list, dict, set)) and not value:
            return False
        return True


class LLMJudgeEvaluator(RuleEvaluator):
    """Evaluator that uses LLM for complex judgments.

    Used for ambiguous cases where rule-based logic isn't sufficient.
    """

    rule_type = RuleType.LLM_JUDGE

    def __init__(self, llm_service: LLMService | None = None) -> None:
        self._llm_service = llm_service

    def set_llm_service(self, llm_service: LLMService) -> None:
        """Set the LLM service for making judgments."""
        self._llm_service = llm_service

    async def evaluate_async(
        self,
        params: dict[str, Any],
        data: dict[str, Any],
    ) -> tuple[bool, str | None, dict[str, Any]]:
        """Evaluate using LLM judgment (async version).

        Required params:
            - prompt: The judgment prompt template
            - criteria: Clear criteria for pass/fail

        Optional params:
            - tier: LLM tier to use (default: tier2)
            - temperature: Sampling temperature (default: 0.0)
            - max_tokens: Maximum response tokens (default: 500)
        """
        from leagent.llm.base import ChatMessage

        if not self._llm_service:
            raise RuleEvaluationError(
                "LLM service not configured for LLM judge evaluator",
                details={"hint": "Call set_llm_service() before evaluation"},
            )

        prompt = params.get("prompt", "")
        criteria = params.get("criteria", "")
        tier = params.get("tier", "tier2")
        temperature = float(params.get("temperature", 0.0))
        max_tokens = int(params.get("max_tokens", 500))

        system_prompt = _load_rule_judge_prompt()

        user_prompt = f"""Evaluate the following:

PROMPT: {prompt}

CRITERIA: {criteria}

DATA: {json.dumps(data, indent=2, default=str)}

Respond with your judgment in JSON format."""

        details = {
            "prompt": prompt,
            "criteria": criteria,
            "tier": tier,
            "temperature": temperature,
        }

        try:
            response = await self._llm_service.complete(
                messages=[
                    ChatMessage.system(system_prompt),
                    ChatMessage.user(user_prompt),
                ],
                tier=tier,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            content = response.content or ""
            details["llm_response"] = content

            json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
            if not json_match:
                logger.warning("LLM judge returned non-JSON response", response=content)
                return False, "LLM returned invalid response format", details

            judgment = json.loads(json_match.group())
            passed = judgment.get("pass", False)
            reason = judgment.get("reason", "")
            confidence = judgment.get("confidence", 0.0)

            details["judgment"] = judgment
            details["confidence"] = confidence

            if not passed:
                return False, reason, details

            return True, None, details

        except Exception as e:
            logger.exception("LLM judge evaluation failed", error=str(e))
            return False, f"LLM evaluation failed: {e}", details

    def evaluate(
        self,
        params: dict[str, Any],
        data: dict[str, Any],
    ) -> tuple[bool, str | None, dict[str, Any]]:
        """Synchronous wrapper - raises error since LLM calls are async."""
        raise RuleEvaluationError(
            "LLMJudgeEvaluator requires async evaluation. Use evaluate_async() instead.",
            details={"hint": "Call engine.evaluate() with await for LLM rules"},
        )


class EvaluatorRegistry:
    """Registry of available rule evaluators."""

    def __init__(self) -> None:
        self._evaluators: dict[RuleType, RuleEvaluator] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register built-in evaluators."""
        self.register(CompareEvaluator())
        self.register(DateRangeEvaluator())
        self.register(ThresholdEvaluator())
        self.register(ContainsAllEvaluator())
        self.register(RegexMatchEvaluator())
        self.register(DateDiffEvaluator())
        self.register(CrossValidateEvaluator())
        self.register(LLMJudgeEvaluator())

    def register(self, evaluator: RuleEvaluator) -> None:
        """Register an evaluator for a rule type."""
        self._evaluators[evaluator.rule_type] = evaluator

    def get(self, rule_type: RuleType) -> RuleEvaluator:
        """Get evaluator for a rule type."""
        if rule_type not in self._evaluators:
            raise RuleEvaluationError(
                f"No evaluator registered for rule type: {rule_type}",
                details={"available_types": list(self._evaluators.keys())},
            )
        return self._evaluators[rule_type]

    def has(self, rule_type: RuleType) -> bool:
        """Check if an evaluator is registered for a rule type."""
        return rule_type in self._evaluators

    def list_types(self) -> list[RuleType]:
        """List all registered rule types."""
        return list(self._evaluators.keys())
