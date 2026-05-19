"""Rule engine for executing rules against data."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from leagent.exceptions.rule import (
    RuleEvaluationError,
    RuleSetNotFoundError,
)
from leagent.rules.base import (
    CompositeCondition,
    LogicalOperator,
    RuleCondition,
    RuleDefinition,
    RuleResult,
    RuleSet,
    RuleSetResult,
    RuleType,
    Severity,
    resolve_all_templates,
)
from leagent.rules.evaluator import EvaluatorRegistry, LLMJudgeEvaluator
from leagent.rules.loader import HotReloadingRuleLoader, RuleLoader

if TYPE_CHECKING:
    from leagent.llm.service import LLMService

logger = structlog.get_logger(__name__)


class RuleEngine:
    """Engine for loading and executing rules against data.

    The engine manages rule sets, evaluators, and provides batch
    evaluation capabilities.

    Example:
        engine = RuleEngine()
        await engine.load_rules("/path/to/rules")

        result = await engine.evaluate("expense_rules", {
            "amount": 1500,
            "category": "travel",
            "date": "2024-01-15",
        })

        if not result.passed:
            for failure in result.get_failed_rules():
                print(f"Rule {failure.rule_name} failed: {failure.message}")
    """

    def __init__(
        self,
        llm_service: LLMService | None = None,
        hot_reload: bool = False,
    ) -> None:
        """Initialize the rule engine.

        Args:
            llm_service: LLM service for LLM-based evaluators.
            hot_reload: Enable hot-reloading of rules.
        """
        self._evaluators = EvaluatorRegistry()
        self._rule_sets: dict[str, RuleSet] = {}
        self._llm_service = llm_service
        self._hot_reload = hot_reload
        self._loader: RuleLoader | HotReloadingRuleLoader | None = None

        if llm_service:
            self._configure_llm_evaluator(llm_service)

    def _configure_llm_evaluator(self, llm_service: LLMService) -> None:
        """Configure the LLM judge evaluator with the service."""
        evaluator = self._evaluators.get(RuleType.LLM_JUDGE)
        if isinstance(evaluator, LLMJudgeEvaluator):
            evaluator.set_llm_service(llm_service)

    def set_llm_service(self, llm_service: LLMService) -> None:
        """Set or update the LLM service."""
        self._llm_service = llm_service
        self._configure_llm_evaluator(llm_service)

    async def load_rules(
        self,
        directory: Path | str,
        recursive: bool = True,
    ) -> int:
        """Load rules from a directory.

        Args:
            directory: Directory containing rule YAML files.
            recursive: Whether to scan subdirectories.

        Returns:
            Number of rule sets loaded.
        """
        dir_path = Path(directory)

        if self._hot_reload:
            self._loader = HotReloadingRuleLoader([dir_path])
            self._loader.on_reload(self._on_rule_reload)
            self._rule_sets = await self._loader.load_all()
            await self._loader.start_watching()
        else:
            loader = RuleLoader()
            self._rule_sets = loader.load_directory(dir_path, recursive=recursive)
            self._loader = loader

        logger.info(
            "Rules loaded",
            rule_set_count=len(self._rule_sets),
            total_rules=sum(len(rs.rules) for rs in self._rule_sets.values()),
            hot_reload=self._hot_reload,
        )

        return len(self._rule_sets)

    def _on_rule_reload(self, rule_set_id: str, rule_set: RuleSet | None) -> None:
        """Handle rule set reload callback."""
        if rule_set is None:
            self._rule_sets.pop(rule_set_id, None)
            logger.info("Rule set unloaded", rule_set_id=rule_set_id)
        else:
            self._rule_sets[rule_set_id] = rule_set
            logger.info(
                "Rule set updated",
                rule_set_id=rule_set_id,
                rule_count=len(rule_set.rules),
            )

    async def stop(self) -> None:
        """Stop the engine and cleanup resources."""
        if isinstance(self._loader, HotReloadingRuleLoader):
            await self._loader.stop_watching()

    def register_rule_set(self, rule_set: RuleSet) -> None:
        """Register a rule set programmatically.

        Args:
            rule_set: Rule set to register.
        """
        self._rule_sets[rule_set.id] = rule_set
        logger.debug(
            "Rule set registered",
            rule_set_id=rule_set.id,
            rule_count=len(rule_set.rules),
        )

    def unregister_rule_set(self, rule_set_id: str) -> bool:
        """Unregister a rule set.

        Args:
            rule_set_id: ID of rule set to unregister.

        Returns:
            True if removed, False if not found.
        """
        if rule_set_id in self._rule_sets:
            del self._rule_sets[rule_set_id]
            return True
        return False

    def get_rule_set(self, rule_set_id: str) -> RuleSet | None:
        """Get a rule set by ID."""
        return self._rule_sets.get(rule_set_id)

    def list_rule_sets(self) -> list[str]:
        """List all registered rule set IDs."""
        return list(self._rule_sets.keys())

    def find_applicable_rules(
        self,
        context: dict[str, Any],
        *,
        tags: list[str] | None = None,
    ) -> list[RuleSet]:
        """Find rule sets applicable to the given context.

        Matches rule sets whose tags overlap with the provided tags or
        context keys. Returns all enabled rule sets when no filter is
        given.

        Args:
            context: Arbitrary context dict (task data, metadata, etc.).
            tags: Explicit tag filter. When omitted, falls back to
                  ``context.get("tags")`` or returns all enabled sets.

        Returns:
            List of matching RuleSet objects.
        """
        search_tags = set(tags or context.get("tags", []) or [])
        results: list[RuleSet] = []
        for rs in self._rule_sets.values():
            if not rs.enabled:
                continue
            if not search_tags:
                results.append(rs)
            elif search_tags.intersection(rs.tags):
                results.append(rs)
        return results

    async def safe_load_directory(self, directory: Path | str) -> int:
        """Load rules from *directory*, returning 0 if it doesn't exist."""
        dir_path = Path(directory)
        if not dir_path.exists() or not dir_path.is_dir():
            return 0
        has_yaml = any(dir_path.glob("*.yaml")) or any(dir_path.glob("*.yml"))
        if not has_yaml:
            return 0
        return await self.load_rules(dir_path)

    async def evaluate(
        self,
        rule_set_id: str,
        data: dict[str, Any],
        *,
        tags: list[str] | None = None,
        skip_disabled: bool = True,
        fail_fast: bool = False,
    ) -> RuleSetResult:
        """Evaluate a rule set against data.

        Args:
            rule_set_id: ID of rule set to evaluate.
            data: Data context for evaluation.
            tags: Only evaluate rules with these tags.
            skip_disabled: Skip disabled rules.
            fail_fast: Stop on first error-severity failure.

        Returns:
            Aggregated result of all rule evaluations.

        Raises:
            RuleSetNotFoundError: If rule set doesn't exist.
        """
        rule_set = self._rule_sets.get(rule_set_id)
        if not rule_set:
            raise RuleSetNotFoundError(
                f"Rule set not found: {rule_set_id}",
                details={"available": list(self._rule_sets.keys())},
            )

        if not rule_set.enabled:
            logger.debug("Skipping disabled rule set", rule_set_id=rule_set_id)
            return RuleSetResult(
                rule_set_id=rule_set_id,
                passed=True,
                total_rules=0,
                results=[],
            )

        rules = rule_set.get_enabled_rules() if skip_disabled else rule_set.rules

        if tags:
            tag_set = set(tags)
            rules = [r for r in rules if tag_set.intersection(r.tags)]

        start_time = time.perf_counter()
        results: list[RuleResult] = []
        error_count = 0
        warning_count = 0
        info_count = 0

        for rule in rules:
            result = await self._evaluate_rule(rule, data)
            results.append(result)

            if not result.passed:
                if result.severity == Severity.ERROR:
                    error_count += 1
                    if fail_fast:
                        break
                elif result.severity == Severity.WARNING:
                    warning_count += 1
                else:
                    info_count += 1

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        return RuleSetResult(
            rule_set_id=rule_set_id,
            passed=error_count == 0,
            total_rules=len(results),
            error_count=error_count,
            warning_count=warning_count,
            info_count=info_count,
            results=results,
            execution_time_ms=elapsed_ms,
        )

    async def evaluate_rule(
        self,
        rule: RuleDefinition,
        data: dict[str, Any],
    ) -> RuleResult:
        """Evaluate a single rule against data.

        Args:
            rule: Rule to evaluate.
            data: Data context for evaluation.

        Returns:
            Result of the rule evaluation.
        """
        return await self._evaluate_rule(rule, data)

    async def _evaluate_rule(
        self,
        rule: RuleDefinition,
        data: dict[str, Any],
    ) -> RuleResult:
        """Internal rule evaluation."""
        start_time = time.perf_counter()

        try:
            resolved_params = resolve_all_templates(rule.condition.params, data)

            evaluator = self._evaluators.get(rule.condition.type)

            if isinstance(evaluator, LLMJudgeEvaluator):
                passed, message, details = await evaluator.evaluate_async(
                    resolved_params, data
                )
            else:
                passed, message, details = evaluator.evaluate(resolved_params, data)

            if not passed and message is None:
                message = rule.message

            resolved_message = self._resolve_message(rule.message, data, details)

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            return RuleResult(
                rule_id=rule.id,
                rule_name=rule.name,
                passed=passed,
                severity=rule.severity,
                message=resolved_message if not passed else None,
                details=details,
                execution_time_ms=elapsed_ms,
            )

        except RuleEvaluationError as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.warning(
                "Rule evaluation error",
                rule_id=rule.id,
                error=str(e),
            )
            return RuleResult(
                rule_id=rule.id,
                rule_name=rule.name,
                passed=False,
                severity=Severity.ERROR,
                message=f"Evaluation error: {e.message}",
                details=e.details,
                execution_time_ms=elapsed_ms,
            )

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                "Unexpected rule evaluation error",
                rule_id=rule.id,
                error=str(e),
            )
            return RuleResult(
                rule_id=rule.id,
                rule_name=rule.name,
                passed=False,
                severity=Severity.ERROR,
                message=f"Unexpected error: {e}",
                details={"exception": str(e)},
                execution_time_ms=elapsed_ms,
            )

    def _resolve_message(
        self,
        message: str,
        data: dict[str, Any],
        details: dict[str, Any],
    ) -> str:
        """Resolve placeholders in error message."""
        combined = {**data, **details}

        import re

        def replace(match: re.Match) -> str:
            key = match.group(1).strip()
            if key in combined:
                return str(combined[key])
            if "." in key:
                parts = key.split(".")
                val = combined
                for p in parts:
                    if isinstance(val, dict) and p in val:
                        val = val[p]
                    else:
                        return match.group(0)
                return str(val)
            return match.group(0)

        return re.sub(r"\{\{([^}]+)\}\}", replace, message)

    async def evaluate_composite(
        self,
        condition: CompositeCondition,
        data: dict[str, Any],
    ) -> tuple[bool, list[RuleResult]]:
        """Evaluate a composite condition.

        Args:
            condition: Composite condition to evaluate.
            data: Data context for evaluation.

        Returns:
            Tuple of (passed, list of individual results).
        """
        results: list[RuleResult] = []

        if condition.operator == LogicalOperator.NOT:
            if not condition.conditions:
                return True, results

            inner = condition.conditions[0]
            if isinstance(inner, CompositeCondition):
                passed, inner_results = await self.evaluate_composite(inner, data)
                results.extend(inner_results)
                return not passed, results
            else:
                rule = self._condition_to_rule(inner, "not_condition")
                result = await self._evaluate_rule(rule, data)
                results.append(result)
                return not result.passed, results

        elif condition.operator == LogicalOperator.AND:
            all_passed = True
            for cond in condition.conditions:
                if isinstance(cond, CompositeCondition):
                    passed, inner_results = await self.evaluate_composite(cond, data)
                    results.extend(inner_results)
                    if not passed:
                        all_passed = False
                else:
                    rule = self._condition_to_rule(cond, f"and_condition_{len(results)}")
                    result = await self._evaluate_rule(rule, data)
                    results.append(result)
                    if not result.passed:
                        all_passed = False
            return all_passed, results

        else:
            any_passed = False
            for cond in condition.conditions:
                if isinstance(cond, CompositeCondition):
                    passed, inner_results = await self.evaluate_composite(cond, data)
                    results.extend(inner_results)
                    if passed:
                        any_passed = True
                else:
                    rule = self._condition_to_rule(cond, f"or_condition_{len(results)}")
                    result = await self._evaluate_rule(rule, data)
                    results.append(result)
                    if result.passed:
                        any_passed = True
            return any_passed, results

    def _condition_to_rule(
        self,
        condition: RuleCondition,
        rule_id: str,
    ) -> RuleDefinition:
        """Convert a standalone condition to a rule definition."""
        return RuleDefinition(
            id=rule_id,
            name=f"Condition: {condition.type.value}",
            condition=condition,
            severity=Severity.ERROR,
            message="Condition failed",
        )

    async def evaluate_batch(
        self,
        rule_set_id: str,
        data_items: list[dict[str, Any]],
        *,
        tags: list[str] | None = None,
        skip_disabled: bool = True,
        concurrency: int = 10,
    ) -> list[RuleSetResult]:
        """Evaluate a rule set against multiple data items.

        Args:
            rule_set_id: ID of rule set to evaluate.
            data_items: List of data contexts to evaluate.
            tags: Only evaluate rules with these tags.
            skip_disabled: Skip disabled rules.
            concurrency: Maximum concurrent evaluations.

        Returns:
            List of results, one per data item.
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def evaluate_with_limit(data: dict[str, Any]) -> RuleSetResult:
            async with semaphore:
                return await self.evaluate(
                    rule_set_id,
                    data,
                    tags=tags,
                    skip_disabled=skip_disabled,
                )

        tasks = [evaluate_with_limit(data) for data in data_items]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed: list[RuleSetResult] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "Batch evaluation failed for item",
                    index=i,
                    error=str(result),
                )
                processed.append(
                    RuleSetResult(
                        rule_set_id=rule_set_id,
                        passed=False,
                        total_rules=0,
                        error_count=1,
                        results=[
                            RuleResult(
                                rule_id="batch_error",
                                rule_name="Batch Error",
                                passed=False,
                                severity=Severity.ERROR,
                                message=str(result),
                            )
                        ],
                    )
                )
            else:
                processed.append(result)

        return processed

    def summarize_results(
        self,
        results: list[RuleSetResult],
    ) -> dict[str, Any]:
        """Generate a summary of batch evaluation results.

        Args:
            results: List of rule set results.

        Returns:
            Summary statistics dictionary.
        """
        total_items = len(results)
        passed_items = sum(1 for r in results if r.passed)
        failed_items = total_items - passed_items

        total_rules_evaluated = sum(r.total_rules for r in results)
        total_errors = sum(r.error_count for r in results)
        total_warnings = sum(r.warning_count for r in results)

        failed_rule_counts: dict[str, int] = {}
        for result in results:
            for rule_result in result.get_failed_rules():
                failed_rule_counts[rule_result.rule_id] = (
                    failed_rule_counts.get(rule_result.rule_id, 0) + 1
                )

        top_failures = sorted(
            failed_rule_counts.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:10]

        return {
            "total_items": total_items,
            "passed_items": passed_items,
            "failed_items": failed_items,
            "pass_rate": passed_items / total_items if total_items > 0 else 0.0,
            "total_rules_evaluated": total_rules_evaluated,
            "total_errors": total_errors,
            "total_warnings": total_warnings,
            "top_failures": [
                {"rule_id": rule_id, "failure_count": count}
                for rule_id, count in top_failures
            ],
        }
