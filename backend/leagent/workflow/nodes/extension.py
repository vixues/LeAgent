"""``NodeExtension`` — the entry-point-style packaging contract for node packs.

A third-party package exposes::

    from leagent.workflow.nodes.extension import NodeExtension
    class MyPack(NodeExtension):
        async def get_node_list(self): ...

    async def leagent_entrypoint() -> NodeExtension:
        return MyPack()

``nodes.loader`` discovers packs via:
1. installed Python entrypoint group ``leagent.workflow.nodes``,
2. filesystem scan of ``leagent/workflow/nodes/builtin/`` and
   ``config/workflow/custom_nodes/``.

This mirrors ComfyUI's ``ComfyExtension`` but trimmed to async-first.
"""

from __future__ import annotations

import abc
from typing import Any

from .base import WorkflowNode


class NodeExtension(abc.ABC):
    """Abstract bundle of nodes + lifecycle hooks."""

    name: str = ""
    version: str = "0.0.0"

    async def on_load(self, context: dict[str, Any] | None = None) -> None:
        """Called after the registry installs this extension's nodes."""

    async def on_unload(self, context: dict[str, Any] | None = None) -> None:
        """Called before the registry removes this extension's nodes."""

    @abc.abstractmethod
    async def get_node_list(self) -> list[type[WorkflowNode]]:
        """Return node classes to register."""
