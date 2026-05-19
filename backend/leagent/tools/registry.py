"""Tool registry for LeAgent.

Provides centralized management of tools including registration, discovery,
retrieval, and schema generation for LLM function calling.
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import pkgutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from leagent.tools.base import BaseTool, ToolCategory

if TYPE_CHECKING:
    from types import ModuleType

logger = structlog.get_logger(__name__)


class ToolNotFoundError(Exception):
    """Raised when a requested tool is not found in the registry."""

    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        super().__init__(f"Tool not found: {tool_name}")


class ToolRegistrationError(Exception):
    """Raised when tool registration fails."""

    def __init__(self, tool_name: str, reason: str) -> None:
        self.tool_name = tool_name
        self.reason = reason
        super().__init__(f"Failed to register tool '{tool_name}': {reason}")


class ToolRegistry:
    """Central registry for all tools in the system.

    Manages tool registration, discovery, retrieval, and provides
    schemas for LLM function calling integration.

    Mirrors the reference architecture's tool pool assembly:
    - Alias-based lookup (``tool.aliases``)
    - Deny-rule filtering before schema generation
    - Enabled-check gating
    - Search-hint indexing for ToolSearch
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._aliases: dict[str, str] = {}  # alias → canonical name
        self._categories: dict[ToolCategory, list[str]] = {cat: [] for cat in ToolCategory}
        self._schema_generation: int = 0
        self._llm_tool_schema_cache: dict[str, list[dict[str, Any]]] = {}

    def register(self, tool: BaseTool, *, replace: bool = False) -> None:
        """Register a tool instance."""
        validation_error = self._validate_tool(tool)
        if validation_error:
            raise ToolRegistrationError(tool.name, validation_error)

        if tool.name in self._tools and not replace:
            raise ToolRegistrationError(tool.name, "Tool already registered (use replace=True to override)")

        if tool.name in self._tools:
            old_tool = self._tools[tool.name]
            if old_tool.category in self._categories:
                try:
                    self._categories[old_tool.category].remove(tool.name)
                except ValueError:
                    pass
            for alias, canonical in list(self._aliases.items()):
                if canonical == tool.name:
                    del self._aliases[alias]
            logger.info("Replacing existing tool", tool=tool.name)

        self._tools[tool.name] = tool
        self._categories[tool.category].append(tool.name)

        for alias in getattr(tool, "aliases", None) or []:
            self._aliases[alias] = tool.name

        logger.info(
            "Tool registered",
            tool=tool.name,
            category=tool.category.value,
            version=tool.version,
        )
        self._schema_generation += 1

    def _validate_tool(self, tool: BaseTool) -> str | None:
        """Validate a tool before registration.

        Returns:
            Error message if validation fails, None otherwise.
        """
        if not tool.name:
            return "Tool name is required"

        if not tool.name.replace("_", "").isalnum():
            return "Tool name must be alphanumeric with underscores only"

        if len(tool.name) > 64:
            return "Tool name must be 64 characters or less"

        if not tool.description:
            return "Tool description is required"

        if not isinstance(tool.parameters, dict):
            return "Tool parameters must be a JSON schema dictionary"

        if tool.parameters.get("type") != "object":
            return "Tool parameters schema must have type 'object'"

        return None

    def unregister(self, name: str) -> bool:
        """Unregister a tool by name.

        Args:
            name: The name of the tool to unregister.

        Returns:
            True if tool was unregistered, False if not found.
        """
        if name not in self._tools:
            return False

        tool = self._tools.pop(name)
        if tool.category in self._categories:
            self._categories[tool.category].remove(name)

        logger.info("Tool unregistered", tool=name)
        return True

    def _resolve_name(self, name: str) -> str:
        """Resolve an alias to the canonical tool name."""
        return self._aliases.get(name, name)

    def get(self, name: str) -> BaseTool:
        """Get a tool by name or alias."""
        canonical = self._resolve_name(name)
        if canonical not in self._tools:
            raise ToolNotFoundError(name)
        return self._tools[canonical]

    def get_optional(self, name: str) -> BaseTool | None:
        """Get a tool by name or alias, returning None if not found."""
        canonical = self._resolve_name(name)
        return self._tools.get(canonical)

    def find_by_name(self, name: str) -> BaseTool | None:
        """Find a tool by name, alias, or matches_name() (mirrors reference findToolByName)."""
        canonical = self._resolve_name(name)
        if canonical in self._tools:
            return self._tools[canonical]
        for tool in self._tools.values():
            if tool.matches_name(name):
                return tool
        return None

    def has(self, name: str) -> bool:
        """Check if a tool is registered (supports aliases)."""
        canonical = self._resolve_name(name)
        return canonical in self._tools

    def list_all(self) -> list[BaseTool]:
        """List all registered tools.

        Returns:
            List of all tool instances.
        """
        return list(self._tools.values())

    def list_tools(self) -> list[BaseTool]:
        """Alias for list_all() for compatibility with agent controller."""
        return self.list_all()

    def list_names(self) -> list[str]:
        """List all registered tool names.

        Returns:
            List of tool names.
        """
        return list(self._tools.keys())

    def list_by_category(self, category: ToolCategory) -> list[BaseTool]:
        """List tools in a specific category.

        Args:
            category: The category to filter by.

        Returns:
            List of tools in the category.
        """
        return [self._tools[name] for name in self._categories.get(category, [])]

    def get_categories(self) -> dict[ToolCategory, int]:
        """Get tool counts by category.

        Returns:
            Dictionary mapping categories to tool counts.
        """
        return {cat: len(names) for cat, names in self._categories.items()}

    def get_schemas(
        self,
        provider_format: str = "openai",
        tool_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Get tool schemas in a specific provider format.

        Args:
            provider_format: One of "openai", "anthropic", or "generic".
            tool_names: Optional list of specific tool names.

        Returns:
            List of schema dictionaries in the requested format.
        """
        if tool_names is None:
            tools = list(self._tools.values())
        else:
            tools = []
            for name in tool_names:
                if name not in self._tools:
                    raise ToolNotFoundError(name)
                tools.append(self._tools[name])

        schema_method = {
            "openai": "to_openai_schema",
            "anthropic": "to_anthropic_schema",
            "generic": "to_generic_schema",
        }.get(provider_format, "to_openai_schema")

        schemas = []
        for tool in tools:
            method = getattr(tool, schema_method, tool.to_openai_schema)
            schemas.append(method())
        return schemas

    def get_openai_schemas(self, tool_names: list[str] | None = None) -> list[dict[str, Any]]:
        """Get OpenAI function-calling schemas for tools."""
        if tool_names is None:
            tools = list(self._tools.values())
        else:
            tools = []
            for name in tool_names:
                canonical = self._resolve_name(name)
                if canonical not in self._tools:
                    raise ToolNotFoundError(name)
                tools.append(self._tools[canonical])

        return [tool.to_openai_schema() for tool in tools]

    # -- Filtering methods (mirrors reference getTools / filterToolsByDenyRules) --

    def get_enabled_tools(self) -> list[BaseTool]:
        """Return only tools whose ``is_enabled`` is True."""
        return [t for t in self._tools.values() if t.is_enabled]

    def filter_by_deny_rules(self, deny_patterns: list[str]) -> list[BaseTool]:
        """Return tools not matched by any deny pattern (mirrors filterToolsByDenyRules)."""
        import fnmatch

        result: list[BaseTool] = []
        for tool in self._tools.values():
            denied = any(fnmatch.fnmatch(tool.name, p) for p in deny_patterns)
            if not denied:
                result.append(tool)
        return result

    def _schema_cache_key(self, deny_patterns: list[str] | None, provider_format: str) -> str:
        """Content-addressed cache key based on actual tool state."""
        import hashlib

        parts = [
            str(self._schema_generation),
            provider_format,
            ",".join(sorted(deny_patterns or [])),
        ]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]

    def get_tools_for_llm(
        self,
        deny_patterns: list[str] | None = None,
        provider_format: str = "openai",
    ) -> list[dict[str, Any]]:
        """Assemble the tool pool for an LLM call: enabled + not-denied."""
        cache_key = self._schema_cache_key(deny_patterns, provider_format)
        hit = self._llm_tool_schema_cache.get(cache_key)
        if hit is not None:
            return hit

        tools = self.get_enabled_tools()
        if deny_patterns:
            import fnmatch
            tools = [
                t for t in tools
                if not any(fnmatch.fnmatch(t.name, p) for p in deny_patterns)
            ]
        schema_method = {
            "openai": "to_openai_schema",
            "anthropic": "to_anthropic_schema",
            "generic": "to_generic_schema",
        }.get(provider_format, "to_openai_schema")
        out = [getattr(t, schema_method)() for t in tools]
        self._llm_tool_schema_cache[cache_key] = out
        return out

    def search_tools(self, query: str) -> list[BaseTool]:
        """Keyword search across tool names, descriptions, and search_hints."""
        query_lower = query.lower()
        scored: list[tuple[int, BaseTool]] = []
        for tool in self._tools.values():
            score = 0
            if query_lower in tool.name.lower():
                score += 3
            if query_lower in tool.description.lower():
                score += 2
            hint = getattr(tool, "search_hint", "") or ""
            if hint and query_lower in hint.lower():
                score += 2
            if score > 0:
                scored.append((score, tool))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in scored]

    def filter_by_capabilities(
        self,
        allowed: set[str],
        *,
        require_all: bool = False,
    ) -> list[BaseTool]:
        """Return tools whose capabilities are a subset of (or overlap with) ``allowed``."""
        from leagent.tools.base import ToolCapability

        result: list[BaseTool] = []
        for tool in self._tools.values():
            caps = getattr(tool, "capabilities", set())
            if not caps:
                result.append(tool)
                continue
            if require_all:
                if caps.issubset(allowed):
                    result.append(tool)
            else:
                if caps & allowed:
                    result.append(tool)
        return result

    def load_from_module(self, module: ModuleType) -> int:
        """Load and register all tool classes from a module.

        Args:
            module: The module to scan for tool classes.

        Returns:
            Number of tools registered.
        """
        count = 0
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if self._is_concrete_tool_class(obj):
                try:
                    tool_instance = obj()
                    self.register(tool_instance)
                    count += 1
                except Exception as e:
                    logger.warning(
                        "Failed to instantiate tool",
                        class_name=name,
                        module=module.__name__,
                        error=str(e),
                    )
        return count

    def load_from_package(self, package_name: str) -> int:
        """Load tools from a package and all its submodules.

        Args:
            package_name: Fully qualified package name (e.g., 'leagent.tools.doc').

        Returns:
            Number of tools registered.
        """
        try:
            package = importlib.import_module(package_name)
        except ImportError as e:
            logger.error("Failed to import package", package=package_name, error=str(e))
            return 0

        count = 0

        if hasattr(package, "__path__"):
            for _, module_name, _ in pkgutil.walk_packages(
                package.__path__,
                prefix=f"{package_name}.",
            ):
                try:
                    module = importlib.import_module(module_name)
                    count += self.load_from_module(module)
                except ImportError as e:
                    logger.warning(
                        "Failed to import module",
                        module=module_name,
                        error=str(e),
                    )

        logger.info("Loaded tools from package", package=package_name, count=count)
        return count

    def load_from_directory(self, directory: str | Path) -> int:
        """Auto-discover and register tools from Python files in a directory.

        Recursively scans the directory for Python files and registers
        any concrete BaseTool subclasses found.

        Args:
            directory: Path to the directory to scan.

        Returns:
            Number of tools registered.
        """
        directory = Path(directory)
        if not directory.exists():
            logger.warning("Tool directory does not exist", path=str(directory))
            return 0

        count = 0
        for py_file in directory.rglob("*.py"):
            if py_file.name.startswith("_"):
                continue

            module_name = self._path_to_module_name(py_file, directory)
            if module_name:
                try:
                    spec = importlib.util.spec_from_file_location(module_name, py_file)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        count += self.load_from_module(module)
                except Exception as e:
                    logger.warning(
                        "Failed to load module from file",
                        file=str(py_file),
                        error=str(e),
                    )

        logger.info("Loaded tools from directory", path=str(directory), count=count)
        return count

    def discover_all(
        self,
        base_package: str = "leagent.tools",
        *,
        categories: list[str] | None = None,
    ) -> int:
        """Discover and register all tools from the standard tool packages.

        Args:
            base_package: The base package to scan.
            categories: Subpackage names under ``base_package`` to scan; default
                scans every standard category (including ``db``).

        Returns:
            Total number of tools registered.
        """
        tool_categories = categories or [
            "doc", "web", "data", "db", "gen", "image", "chart",
            "integration", "util", "canvas", "workflow", "code",
            "skills", "project",
        ]
        total = 0

        for category in tool_categories:
            package_name = f"{base_package}.{category}"
            total += self.load_from_package(package_name)

        logger.info("Tool discovery complete", total_tools=total)
        return total

    def _is_concrete_tool_class(self, cls: type) -> bool:
        """Check if a class is a concrete tool implementation."""
        return (
            inspect.isclass(cls)
            and issubclass(cls, BaseTool)
            and cls is not BaseTool
            and not inspect.isabstract(cls)
            and hasattr(cls, "name")
            and bool(getattr(cls, "name", ""))
        )

    def _path_to_module_name(self, file_path: Path, base_dir: Path) -> str | None:
        """Convert a file path to a module name."""
        try:
            relative = file_path.relative_to(base_dir)
            parts = list(relative.parts)
            parts[-1] = parts[-1].rsplit(".", 1)[0]
            return ".".join(parts)
        except ValueError:
            return None

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __iter__(self):
        return iter(self._tools.values())

    @classmethod
    def get_default(cls) -> ToolRegistry:
        """Return the process-wide :class:`ToolRegistry` singleton.

        Alias for :func:`get_registry` kept for symmetry with
        ``ToolExecutor.get_default`` and for the many callers (workflow
        worker, service manager) that historically assumed a classmethod
        factory was available.
        """
        return get_registry()


_default_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    """Get the default global tool registry.

    Returns:
        The singleton ToolRegistry instance.
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = ToolRegistry()
    return _default_registry


def reset_registry() -> None:
    """Reset the default global registry (mainly for testing)."""
    global _default_registry
    _default_registry = None
