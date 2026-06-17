"""Adapter base for workflow tools authored with the ``parameters_schema`` +
``_execute(context, **kwargs)`` convention.

``BaseTool`` exposes the canonical surface (``parameters`` property +
``execute(params, context)``). This thin base lets the workflow CRUD/save tools
keep their ergonomic ``_execute(self, context, **kwargs)`` signature while still
satisfying the abstract contract — without it the classes stay abstract and are
silently skipped at bootstrap.
"""

from __future__ import annotations

from typing import Any

from leagent.tools.base import BaseTool, ToolContext, ToolResult


class SchemaWorkflowTool(BaseTool):
    """``BaseTool`` subclass driven by ``parameters_schema`` + ``_execute``."""

    parameters_schema: dict[str, Any] = {"type": "object", "properties": {}}

    @property
    def parameters(self) -> dict[str, Any]:
        return self.parameters_schema

    async def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        return await self._execute(context, **(params or {}))

    async def _execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        raise NotImplementedError
