"""YAML rule loader with hot-reload support."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any, Callable

import structlog
import yaml
from pydantic import ValidationError as PydanticValidationError
from watchfiles import Change, awatch

from leagent.exceptions.rule import RuleLoadError, RuleValidationError
from leagent.rules.base import RuleDefinition, RuleSet, RuleType

logger = structlog.get_logger(__name__)


class RuleValidator:
    """Validates rule definitions for correctness."""

    REQUIRED_PARAMS: dict[RuleType, list[str]] = {
        RuleType.COMPARE: ["left", "operator", "right"],
        RuleType.DATE_RANGE: ["date", "start", "end"],
        RuleType.THRESHOLD: ["value"],
        RuleType.CONTAINS_ALL: ["source", "required"],
        RuleType.DATE_DIFF: ["from_date", "to_date"],
        RuleType.REGEX_MATCH: ["value", "pattern"],
        RuleType.CROSS_VALIDATE: ["fields", "validation_type"],
        RuleType.LLM_JUDGE: ["prompt", "criteria"],
    }

    VALID_OPERATORS = {"==", "!=", "<", ">", "<=", ">=", "in", "not_in", "contains", "not_contains"}
    VALID_CROSS_VALIDATION_TYPES = {
        "all_equal",
        "all_different",
        "sum_equals",
        "at_least_one_present",
        "all_present",
        "mutex",
        "conditional",
    }

    def validate_rule(self, rule: RuleDefinition) -> list[str]:
        """Validate a single rule definition.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors: list[str] = []

        rule_type = rule.condition.type
        params = rule.condition.params

        required = self.REQUIRED_PARAMS.get(rule_type, [])
        for param in required:
            if param not in params:
                errors.append(f"Rule '{rule.id}': Missing required param '{param}' for {rule_type.value}")

        if rule_type == RuleType.COMPARE:
            operator = params.get("operator", "==")
            if operator not in self.VALID_OPERATORS:
                errors.append(
                    f"Rule '{rule.id}': Invalid operator '{operator}'. "
                    f"Valid operators: {self.VALID_OPERATORS}"
                )

        elif rule_type == RuleType.CROSS_VALIDATE:
            vtype = params.get("validation_type")
            if vtype and vtype not in self.VALID_CROSS_VALIDATION_TYPES:
                errors.append(
                    f"Rule '{rule.id}': Invalid validation_type '{vtype}'. "
                    f"Valid types: {self.VALID_CROSS_VALIDATION_TYPES}"
                )

            if vtype == "conditional":
                for req in ["condition_field", "condition_value", "required_fields"]:
                    if req not in params:
                        errors.append(
                            f"Rule '{rule.id}': Conditional cross-validation requires '{req}'"
                        )

            if vtype == "sum_equals" and "target" not in params:
                errors.append(
                    f"Rule '{rule.id}': sum_equals validation requires 'target' param"
                )

        elif rule_type == RuleType.THRESHOLD:
            if not any(k in params for k in ["min", "max", "min_exclusive", "max_exclusive"]):
                errors.append(
                    f"Rule '{rule.id}': Threshold requires at least one of: "
                    "min, max, min_exclusive, max_exclusive"
                )

        return errors

    def validate_rule_set(self, rule_set: RuleSet) -> list[str]:
        """Validate a rule set and all its rules.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors: list[str] = []

        rule_ids = [r.id for r in rule_set.rules]
        duplicates = [rid for rid in rule_ids if rule_ids.count(rid) > 1]
        if duplicates:
            errors.append(
                f"RuleSet '{rule_set.id}': Duplicate rule IDs: {set(duplicates)}"
            )

        for rule in rule_set.rules:
            errors.extend(self.validate_rule(rule))

        return errors


class RuleLoader:
    """Loads rules from YAML files with validation."""

    def __init__(self, validator: RuleValidator | None = None) -> None:
        self._validator = validator or RuleValidator()
        self._file_hashes: dict[Path, str] = {}

    def load_file(self, file_path: Path | str) -> RuleSet:
        """Load a rule set from a YAML file.

        Args:
            file_path: Path to the YAML file.

        Returns:
            Parsed and validated RuleSet.

        Raises:
            RuleLoadError: If file cannot be read.
            RuleValidationError: If rules are invalid.
        """
        path = Path(file_path)

        if not path.exists():
            raise RuleLoadError(
                f"Rule file not found: {path}",
                details={"path": str(path)},
            )

        if not path.suffix.lower() in (".yaml", ".yml"):
            raise RuleLoadError(
                f"Invalid file extension: {path.suffix}. Expected .yaml or .yml",
                details={"path": str(path)},
            )

        try:
            content = path.read_text(encoding="utf-8")
            self._file_hashes[path] = self._compute_hash(content)
        except OSError as e:
            raise RuleLoadError(
                f"Cannot read rule file: {e}",
                details={"path": str(path)},
            )

        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            raise RuleLoadError(
                f"Invalid YAML syntax: {e}",
                details={"path": str(path), "error": str(e)},
            )

        if not isinstance(data, dict):
            raise RuleValidationError(
                "Rule file must contain a mapping at root level",
                details={"path": str(path), "got": type(data).__name__},
            )

        try:
            rule_set = RuleSet.model_validate(data)
        except PydanticValidationError as e:
            raise RuleValidationError(
                f"Invalid rule structure: {e}",
                details={"path": str(path), "errors": e.errors()},
            )

        validation_errors = self._validator.validate_rule_set(rule_set)
        if validation_errors:
            raise RuleValidationError(
                f"Rule validation failed with {len(validation_errors)} errors",
                details={"path": str(path), "errors": validation_errors},
            )

        logger.info(
            "Loaded rule set",
            rule_set_id=rule_set.id,
            rule_count=len(rule_set.rules),
            path=str(path),
        )

        return rule_set

    def load_directory(
        self,
        directory: Path | str,
        recursive: bool = True,
    ) -> dict[str, RuleSet]:
        """Load all rule sets from a directory.

        Args:
            directory: Directory path to scan.
            recursive: Whether to scan subdirectories.

        Returns:
            Dictionary mapping rule set IDs to RuleSets.
        """
        dir_path = Path(directory)

        if not dir_path.exists():
            raise RuleLoadError(
                f"Rule directory not found: {dir_path}",
                details={"path": str(dir_path)},
            )

        if not dir_path.is_dir():
            raise RuleLoadError(
                f"Path is not a directory: {dir_path}",
                details={"path": str(dir_path)},
            )

        pattern = "**/*.yaml" if recursive else "*.yaml"
        yaml_files = list(dir_path.glob(pattern))
        yaml_files.extend(dir_path.glob(pattern.replace(".yaml", ".yml")))

        rule_sets: dict[str, RuleSet] = {}
        load_errors: list[dict[str, Any]] = []

        for file_path in yaml_files:
            try:
                rule_set = self.load_file(file_path)
                if rule_set.id in rule_sets:
                    load_errors.append({
                        "path": str(file_path),
                        "error": f"Duplicate rule set ID: {rule_set.id}",
                    })
                else:
                    rule_sets[rule_set.id] = rule_set
            except (RuleLoadError, RuleValidationError) as e:
                load_errors.append({
                    "path": str(file_path),
                    "error": str(e),
                    "details": e.details,
                })

        if load_errors:
            logger.warning(
                "Some rule files failed to load",
                error_count=len(load_errors),
                errors=load_errors,
            )

        logger.info(
            "Loaded rules from directory",
            directory=str(dir_path),
            rule_set_count=len(rule_sets),
            total_rules=sum(len(rs.rules) for rs in rule_sets.values()),
        )

        return rule_sets

    def has_changed(self, file_path: Path | str) -> bool:
        """Check if a file has changed since last load."""
        path = Path(file_path)
        if path not in self._file_hashes:
            return True

        try:
            content = path.read_text(encoding="utf-8")
            current_hash = self._compute_hash(content)
            return current_hash != self._file_hashes[path]
        except OSError:
            return True

    def _compute_hash(self, content: str) -> str:
        """Compute SHA256 hash of content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()


class RuleWatcher:
    """Watches rule directories for changes and triggers reloads.

    Supports hot-reloading of rules when files change.
    """

    def __init__(
        self,
        directories: list[Path | str],
        on_change: Callable[[Path, Change], None],
        debounce_ms: int = 500,
    ) -> None:
        """Initialize the rule watcher.

        Args:
            directories: Directories to watch.
            on_change: Callback when a rule file changes.
            debounce_ms: Debounce time in milliseconds.
        """
        self._directories = [Path(d) for d in directories]
        self._on_change = on_change
        self._debounce_ms = debounce_ms
        self._watch_task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Start watching for file changes."""
        if self._watch_task and not self._watch_task.done():
            logger.warning("Rule watcher already running")
            return

        self._stop_event.clear()
        self._watch_task = asyncio.create_task(self._watch_loop())

        logger.info(
            "Started rule file watcher",
            directories=[str(d) for d in self._directories],
        )

    async def stop(self) -> None:
        """Stop watching for file changes."""
        if not self._watch_task:
            return

        self._stop_event.set()

        try:
            await asyncio.wait_for(self._watch_task, timeout=5.0)
        except asyncio.TimeoutError:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass

        self._watch_task = None
        logger.info("Stopped rule file watcher")

    @property
    def is_running(self) -> bool:
        """Check if the watcher is currently running."""
        return self._watch_task is not None and not self._watch_task.done()

    async def _watch_loop(self) -> None:
        """Main watch loop."""
        watch_paths = [str(d) for d in self._directories if d.exists()]

        if not watch_paths:
            logger.warning("No valid directories to watch")
            return

        try:
            async for changes in awatch(
                *watch_paths,
                debounce=self._debounce_ms,
                stop_event=self._stop_event,
            ):
                for change_type, path_str in changes:
                    path = Path(path_str)

                    if path.suffix.lower() not in (".yaml", ".yml"):
                        continue

                    logger.debug(
                        "Rule file change detected",
                        path=str(path),
                        change_type=change_type.name,
                    )

                    try:
                        self._on_change(path, change_type)
                    except Exception:
                        logger.exception(
                            "Error in rule change callback",
                            path=str(path),
                            change_type=change_type.name,
                        )

        except asyncio.CancelledError:
            logger.debug("Rule watcher cancelled")
            raise
        except Exception:
            logger.exception("Rule watcher error")


class HotReloadingRuleLoader:
    """Rule loader with automatic hot-reload support.

    Combines RuleLoader and RuleWatcher for automatic reloading.
    """

    def __init__(self, directories: list[Path | str] | None = None) -> None:
        """Initialize the hot-reloading loader.

        Args:
            directories: Directories to watch for rule changes.
        """
        self._loader = RuleLoader()
        self._directories = [Path(d) for d in (directories or [])]
        self._rule_sets: dict[str, RuleSet] = {}
        self._file_to_rule_set: dict[Path, str] = {}
        self._watcher: RuleWatcher | None = None
        self._reload_callbacks: list[Callable[[str, RuleSet | None], None]] = []

    def add_directory(self, directory: Path | str) -> None:
        """Add a directory to watch."""
        self._directories.append(Path(directory))

    def on_reload(self, callback: Callable[[str, RuleSet | None], None]) -> None:
        """Register a callback for rule reloads.

        Callback receives (rule_set_id, rule_set) where rule_set is None on deletion.
        """
        self._reload_callbacks.append(callback)

    async def load_all(self) -> dict[str, RuleSet]:
        """Load all rules from configured directories."""
        self._rule_sets.clear()
        self._file_to_rule_set.clear()

        for directory in self._directories:
            if not directory.exists():
                logger.warning("Rule directory does not exist", directory=str(directory))
                continue

            for yaml_file in list(directory.glob("**/*.yaml")) + list(directory.glob("**/*.yml")):
                try:
                    rule_set = self._loader.load_file(yaml_file)
                    self._rule_sets[rule_set.id] = rule_set
                    self._file_to_rule_set[yaml_file] = rule_set.id
                except (RuleLoadError, RuleValidationError) as e:
                    logger.warning(
                        "Failed to load rule file",
                        path=str(yaml_file),
                        error=str(e),
                    )

        return self._rule_sets

    async def start_watching(self) -> None:
        """Start watching for file changes."""
        if self._watcher:
            await self._watcher.stop()

        self._watcher = RuleWatcher(
            directories=self._directories,
            on_change=self._handle_change,
        )
        await self._watcher.start()

    async def stop_watching(self) -> None:
        """Stop watching for file changes."""
        if self._watcher:
            await self._watcher.stop()
            self._watcher = None

    def get_rule_set(self, rule_set_id: str) -> RuleSet | None:
        """Get a rule set by ID."""
        return self._rule_sets.get(rule_set_id)

    def list_rule_sets(self) -> list[str]:
        """List all loaded rule set IDs."""
        return list(self._rule_sets.keys())

    def _handle_change(self, path: Path, change_type: Change) -> None:
        """Handle a file change event."""
        if change_type == Change.deleted:
            self._handle_deletion(path)
        else:
            self._handle_modification(path)

    def _handle_deletion(self, path: Path) -> None:
        """Handle a file deletion."""
        rule_set_id = self._file_to_rule_set.pop(path, None)
        if rule_set_id and rule_set_id in self._rule_sets:
            del self._rule_sets[rule_set_id]
            logger.info("Rule set removed due to file deletion", rule_set_id=rule_set_id)

            for callback in self._reload_callbacks:
                try:
                    callback(rule_set_id, None)
                except Exception:
                    logger.exception("Error in reload callback")

    def _handle_modification(self, path: Path) -> None:
        """Handle a file modification or creation."""
        try:
            rule_set = self._loader.load_file(path)

            old_id = self._file_to_rule_set.get(path)
            if old_id and old_id != rule_set.id and old_id in self._rule_sets:
                del self._rule_sets[old_id]

            self._rule_sets[rule_set.id] = rule_set
            self._file_to_rule_set[path] = rule_set.id

            logger.info(
                "Rule set reloaded",
                rule_set_id=rule_set.id,
                path=str(path),
            )

            for callback in self._reload_callbacks:
                try:
                    callback(rule_set.id, rule_set)
                except Exception:
                    logger.exception("Error in reload callback")

        except (RuleLoadError, RuleValidationError) as e:
            logger.warning(
                "Failed to reload rule file",
                path=str(path),
                error=str(e),
            )
