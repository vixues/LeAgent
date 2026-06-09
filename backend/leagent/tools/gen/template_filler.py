"""Template Filler Tool - Fill templates using Jinja2 engine.

Provides powerful template rendering with variable substitution, conditionals, and loops.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog

from leagent.tools.base import SyncTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)


class TemplateFillerTool(SyncTool):
    """Fill templates using Jinja2 template engine.

    Features:
    - Variable substitution with dot notation
    - Conditional content (if/else/elif)
    - Loop support (for loops)
    - Template inheritance and includes
    - Custom filters and functions
    - Multiple output formats
    - Safe/sandboxed rendering
    """

    name = "template_filler"
    description = (
        "Fill templates using Jinja2 engine with variable substitution, "
        "conditional content, loops, filters, and template inheritance."
    )
    category = ToolCategory.GEN
    version = "1.0.0"
    timeout_sec = 60
    aliases = ["template", "jinja", "fill_template"]
    search_hint = "template Jinja2 fill variable substitution conditional loop filter render"
    is_concurrency_safe = True
    is_read_only = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000
    path_params = ("template_path", "data_file")
    output_path_params = ("output_path",)

    def _enforce_path_sandbox(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> None:
        super()._enforce_path_sandbox(params, context)

        from leagent.file.sandbox import PathSandbox

        request_id = context.extra.get("request_id", context.session_id or "")
        for inc in params.get("include_paths") or []:
            if inc and isinstance(inc, str):
                PathSandbox.resolve_safe(
                    inc, context=context, tool_name=self.name,
                    request_id=str(request_id),
                )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "template_source": {
                    "type": "string",
                    "enum": ["file", "string", "url"],
                    "description": "Source type for template. Defaults to 'string'.",
                },
                "template_path": {
                    "type": "string",
                    "description": "Path to template file (for 'file' source).",
                },
                "template_string": {
                    "type": "string",
                    "description": "Template content as string (for 'string' source).",
                },
                "template_url": {
                    "type": "string",
                    "description": "URL to fetch template from (for 'url' source).",
                },
                "output_path": {
                    "type": "string",
                    "description": (
                        "Optional path to save rendered output; set only when the user "
                        "asked to save or export."
                    ),
                },
                "variables": {
                    "type": "object",
                    "description": "Variables to substitute in the template.",
                    "additionalProperties": {},
                },
                "data_file": {
                    "type": "string",
                    "description": "Path to JSON/YAML file containing variables.",
                },
                "strict_mode": {
                    "type": "boolean",
                    "description": "Raise error on undefined variables. Defaults to false.",
                },
                "autoescape": {
                    "type": "boolean",
                    "description": "Auto-escape HTML characters. Defaults to true.",
                },
                "trim_blocks": {
                    "type": "boolean",
                    "description": "Remove first newline after block tags. Defaults to true.",
                },
                "lstrip_blocks": {
                    "type": "boolean",
                    "description": "Strip leading whitespace from block tags. Defaults to true.",
                },
                "custom_filters": {
                    "type": "object",
                    "description": "Custom filter definitions as {name: python_expression}.",
                    "additionalProperties": {"type": "string"},
                },
                "globals": {
                    "type": "object",
                    "description": "Global variables available in all templates.",
                    "additionalProperties": {},
                },
                "include_paths": {
                    "type": "array",
                    "description": "Additional paths to search for template includes.",
                    "items": {"type": "string"},
                },
                "output_format": {
                    "type": "string",
                    "enum": ["text", "html", "json", "yaml", "markdown"],
                    "description": "Expected output format for validation. Defaults to 'text'.",
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Filling template"

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Render a template with the provided variables.

        Args:
            params: Tool parameters including template source, variables, and options.
            context: Execution context.

        Returns:
            Dictionary containing rendered output and metadata.

        Raises:
            FileNotFoundError: If template file doesn't exist.
            ValueError: If template configuration is invalid.
            RuntimeError: If template rendering fails.
        """
        try:
            from jinja2 import (
                BaseLoader,
                ChoiceLoader,
                Environment,
                FileSystemLoader,
                StrictUndefined,
                Undefined,
                select_autoescape,
            )
            from jinja2.exceptions import TemplateError, TemplateSyntaxError, UndefinedError
        except ImportError as e:
            raise RuntimeError(
                "Jinja2 is not installed. Install with: pip install jinja2"
            ) from e

        template_source = params.get("template_source", "string")
        strict_mode = params.get("strict_mode", False)
        autoescape = params.get("autoescape", True)
        trim_blocks = params.get("trim_blocks", True)
        lstrip_blocks = params.get("lstrip_blocks", True)
        output_format = params.get("output_format", "text")
        output_path = params.get("output_path")

        logger.info(
            "Rendering template",
            source=template_source,
            output_format=output_format,
        )

        variables = self._load_variables(params)

        loaders: list[BaseLoader] = []

        if template_source == "file" and params.get("template_path"):
            template_path = Path(params["template_path"])
            if not template_path.exists():
                raise FileNotFoundError(f"Template file not found: {template_path}")
            loaders.append(FileSystemLoader(str(template_path.parent)))

        for include_path in params.get("include_paths", []):
            path = Path(include_path)
            if path.exists() and path.is_dir():
                loaders.append(FileSystemLoader(str(path)))

        loader = ChoiceLoader(loaders) if loaders else None

        undefined_class = StrictUndefined if strict_mode else Undefined

        if autoescape:
            autoescape_config = select_autoescape(
                enabled_extensions=("html", "htm", "xml"),
                default_for_string=output_format in ("html", "xml"),
            )
        else:
            autoescape_config = False

        env = Environment(
            loader=loader,
            undefined=undefined_class,
            autoescape=autoescape_config,
            trim_blocks=trim_blocks,
            lstrip_blocks=lstrip_blocks,
        )

        self._register_builtin_filters(env)
        self._register_custom_filters(env, params.get("custom_filters", {}))

        for name, value in params.get("globals", {}).items():
            env.globals[name] = value

        env.globals["now"] = self._get_current_datetime
        env.globals["env"] = self._get_env_var

        try:
            if template_source == "file":
                template_path = Path(params["template_path"])
                template = env.get_template(template_path.name)
            elif template_source == "string":
                template_string = params.get("template_string", "")
                if not template_string:
                    raise ValueError("template_string is required for 'string' source")
                template = env.from_string(template_string)
            elif template_source == "url":
                template_url = params.get("template_url")
                if not template_url:
                    raise ValueError("template_url is required for 'url' source")
                template_string = self._fetch_url(template_url)
                template = env.from_string(template_string)
            else:
                raise ValueError(f"Unknown template source: {template_source}")

        except TemplateSyntaxError as e:
            raise ValueError(f"Template syntax error at line {e.lineno}: {e.message}") from e

        try:
            rendered = template.render(**variables)
        except UndefinedError as e:
            raise ValueError(f"Undefined variable in template: {e}") from e
        except TemplateError as e:
            raise RuntimeError(f"Template rendering error: {e}") from e

        if output_format == "json":
            try:
                json.loads(rendered)
            except json.JSONDecodeError as e:
                logger.warning("Rendered output is not valid JSON", error=str(e))

        result: dict[str, Any] = {
            "success": True,
            "rendered": rendered,
            "rendered_length": len(rendered),
            "variables_used": list(variables.keys()),
            "output_format": output_format,
        }

        if output_path:
            # Tier B: write to the sandbox-validated, user-directed output path.
            # The managed-store copy (chat file workspace) is registered by the
            # artifact pipeline (ArtifactRegistrar) from ``output_path``.
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(rendered, encoding="utf-8")
            result["output_path"] = str(output_file)
            result["file_size_bytes"] = output_file.stat().st_size

        logger.info(
            "Template rendered successfully",
            rendered_length=len(rendered),
            output_path=output_path,
        )

        return result

    def _load_variables(self, params: dict[str, Any]) -> dict[str, Any]:
        """Load and merge variables from multiple sources."""
        variables: dict[str, Any] = {}

        if params.get("data_file"):
            data_path = Path(params["data_file"])
            if not data_path.exists():
                raise FileNotFoundError(f"Data file not found: {data_path}")

            content = data_path.read_text(encoding="utf-8")

            if data_path.suffix in (".yaml", ".yml"):
                try:
                    import yaml
                    file_vars = yaml.safe_load(content)
                except ImportError:
                    raise RuntimeError("PyYAML is not installed. Install with: pip install pyyaml")
            elif data_path.suffix == ".json":
                file_vars = json.loads(content)
            else:
                raise ValueError(f"Unsupported data file format: {data_path.suffix}")

            if isinstance(file_vars, dict):
                variables.update(file_vars)

        if params.get("variables"):
            variables.update(params["variables"])

        return variables

    def _register_builtin_filters(self, env: Any) -> None:
        """Register built-in custom filters."""
        import re
        from datetime import datetime

        def format_date(value: Any, fmt: str = "%Y-%m-%d") -> str:
            if isinstance(value, str):
                try:
                    value = datetime.fromisoformat(value)
                except ValueError:
                    return str(value)
            if isinstance(value, datetime):
                return value.strftime(fmt)
            return str(value)

        def format_currency(value: Any, symbol: str = "$", decimals: int = 2) -> str:
            try:
                num = float(value)
                return f"{symbol}{num:,.{decimals}f}"
            except (ValueError, TypeError):
                return str(value)

        def format_number(value: Any, decimals: int = 0, thousands_sep: str = ",") -> str:
            try:
                num = float(value)
                if decimals == 0:
                    formatted = f"{int(num):,}".replace(",", thousands_sep)
                else:
                    formatted = f"{num:,.{decimals}f}".replace(",", thousands_sep)
                return formatted
            except (ValueError, TypeError):
                return str(value)

        def slugify(value: str) -> str:
            value = value.lower().strip()
            value = re.sub(r"[^\w\s-]", "", value)
            value = re.sub(r"[-\s]+", "-", value)
            return value

        def truncate_words(value: str, num_words: int = 20, end: str = "...") -> str:
            words = value.split()
            if len(words) <= num_words:
                return value
            return " ".join(words[:num_words]) + end

        def to_json(value: Any, indent: int | None = None) -> str:
            return json.dumps(value, indent=indent, ensure_ascii=False, default=str)

        def from_json(value: str) -> Any:
            return json.loads(value)

        def dict_get(d: dict[str, Any], key: str, default: Any = None) -> Any:
            keys = key.split(".")
            result = d
            for k in keys:
                if isinstance(result, dict):
                    result = result.get(k, default)
                else:
                    return default
            return result

        def pluralize(value: int, singular: str = "", plural: str = "s") -> str:
            if value == 1:
                return singular
            return plural

        def default_if_none(value: Any, default: Any = "") -> Any:
            return default if value is None else value

        def format_filesize(value: int) -> str:
            for unit in ["B", "KB", "MB", "GB", "TB"]:
                if abs(value) < 1024.0:
                    return f"{value:.1f} {unit}"
                value //= 1024
            return f"{value:.1f} PB"

        env.filters["format_date"] = format_date
        env.filters["format_currency"] = format_currency
        env.filters["format_number"] = format_number
        env.filters["slugify"] = slugify
        env.filters["truncate_words"] = truncate_words
        env.filters["to_json"] = to_json
        env.filters["from_json"] = from_json
        env.filters["dict_get"] = dict_get
        env.filters["pluralize"] = pluralize
        env.filters["default_if_none"] = default_if_none
        env.filters["format_filesize"] = format_filesize

    def _register_custom_filters(
        self,
        env: Any,
        custom_filters: dict[str, str],
    ) -> None:
        """Register custom filters from expressions."""
        safe_builtins = {
            "len": len,
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "list": list,
            "dict": dict,
            "set": set,
            "tuple": tuple,
            "min": min,
            "max": max,
            "sum": sum,
            "abs": abs,
            "round": round,
            "sorted": sorted,
            "reversed": reversed,
            "enumerate": enumerate,
            "zip": zip,
            "map": map,
            "filter": filter,
            "range": range,
            "True": True,
            "False": False,
            "None": None,
        }

        for name, expression in custom_filters.items():
            try:
                if expression.startswith("lambda"):
                    func = eval(expression, {"__builtins__": safe_builtins}, {})
                    env.filters[name] = func
                else:
                    def make_filter(expr: str) -> Any:
                        def custom_filter(value: Any) -> Any:
                            return eval(expr, {"__builtins__": safe_builtins}, {"value": value})
                        return custom_filter
                    env.filters[name] = make_filter(expression)

                logger.debug("Registered custom filter", name=name)
            except Exception as e:
                logger.warning(
                    "Failed to register custom filter",
                    name=name,
                    error=str(e),
                )

    def _get_current_datetime(self, fmt: str | None = None) -> str:
        """Get current datetime, optionally formatted."""
        from datetime import datetime

        now = datetime.now()
        if fmt:
            return now.strftime(fmt)
        return now.isoformat()

    def _get_env_var(self, name: str, default: str = "") -> str:
        """Get environment variable value."""
        import os
        return os.environ.get(name, default)

    def _fetch_url(self, url: str) -> str:
        """Fetch template content from URL."""
        import urllib.request
        import urllib.error

        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                return response.read().decode("utf-8")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Failed to fetch template from URL: {e}") from e
