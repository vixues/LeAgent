"""Rule engine package for LeAgent.

This module provides a flexible rule engine for validating data against
configurable rules. Rules can be defined in YAML files and support various
evaluation types including comparisons, date ranges, thresholds, regex
matching, and LLM-based judgments.

Example:
    from leagent.rules import RuleEngine, RuleSet, RuleDefinition

    # Create engine
    engine = RuleEngine()

    # Load rules from directory
    await engine.load_rules("/path/to/rules")

    # Evaluate data
    result = await engine.evaluate("expense_rules", {
        "amount": 1500,
        "category": "travel",
    })

    if not result.passed:
        for failure in result.get_failed_rules():
            print(f"{failure.rule_name}: {failure.message}")
"""

from leagent.rules.base import (
    CompositeCondition,
    LogicalOperator,
    Operator,
    RuleCondition,
    RuleDefinition,
    RuleEvaluator,
    RuleResult,
    RuleSet,
    RuleSetResult,
    RuleType,
    Severity,
    resolve_all_templates,
    resolve_template,
)
from leagent.rules.engine import RuleEngine
from leagent.rules.evaluator import (
    CompareEvaluator,
    ContainsAllEvaluator,
    CrossValidateEvaluator,
    DateDiffEvaluator,
    DateRangeEvaluator,
    EvaluatorRegistry,
    LLMJudgeEvaluator,
    RegexMatchEvaluator,
    ThresholdEvaluator,
)
from leagent.rules.loader import (
    HotReloadingRuleLoader,
    RuleLoader,
    RuleValidator,
    RuleWatcher,
)

__all__ = [
    # Base classes
    "CompositeCondition",
    "LogicalOperator",
    "Operator",
    "RuleCondition",
    "RuleDefinition",
    "RuleEvaluator",
    "RuleResult",
    "RuleSet",
    "RuleSetResult",
    "RuleType",
    "Severity",
    # Template resolution
    "resolve_all_templates",
    "resolve_template",
    # Engine
    "RuleEngine",
    # Evaluators
    "CompareEvaluator",
    "ContainsAllEvaluator",
    "CrossValidateEvaluator",
    "DateDiffEvaluator",
    "DateRangeEvaluator",
    "EvaluatorRegistry",
    "LLMJudgeEvaluator",
    "RegexMatchEvaluator",
    "ThresholdEvaluator",
    # Loaders
    "HotReloadingRuleLoader",
    "RuleLoader",
    "RuleValidator",
    "RuleWatcher",
]
