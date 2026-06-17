"""Discover + register node classes into a :class:`NodeRegistry`.

Discovery sources, applied in order:

1. **Built-ins** — :mod:`leagent.workflow.nodes.builtin` (curated list).
2. **Entrypoints** — installed Python distributions exposing an entrypoint
   in the ``leagent.workflow.nodes`` group. The target must be either a
   :class:`NodeExtension` subclass, an instance of one, or a coroutine
   returning an instance (mirroring ``leagent_entrypoint``).
3. **Filesystem** — ``.py`` modules under a user directory (e.g.
   ``~/.leagent/workflow/custom_nodes/``). A file may expose either
   module-level ``NODE_CLASSES: list[type[WorkflowNode]]`` or an
   async ``leagent_entrypoint() -> NodeExtension``.

Each module also supports an optional ``prestartup_script.py`` executed
before the module is imported (matches the pattern used in larger node
ecosystems).
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import os
import sys
from pathlib import Path
from typing import Any, Iterable

import structlog

try:  # importlib.metadata is stdlib; older interpreters fall back
    from importlib.metadata import entry_points
except ImportError:  # pragma: no cover
    from importlib_metadata import entry_points  # type: ignore

from .base import WorkflowNode
from .extension import NodeExtension
from .registry import NodeRegistry, get_registry

logger = structlog.get_logger(__name__)

ENTRYPOINT_GROUP = "leagent.workflow.nodes"


async def load_builtins(registry: NodeRegistry | None = None) -> list[str]:
    """Register all built-in node classes. Idempotent."""
    reg = registry or get_registry()
    from . import builtin  # local import to avoid circularity
    registered: list[str] = []
    for cls in builtin.BUILTIN_NODES:
        reg.register(cls, module_path=f"builtin:{cls.__module__}")
        registered.append(cls.NODE_ID)
    logger.info("builtin_nodes_registered", count=len(registered))
    return registered


async def load_art_pack(registry: NodeRegistry | None = None) -> list[str]:
    """Register the first-class game-art node pack (generation nodes).

    Loaded as a :class:`NodeExtension` bundle rather than auto-generated
    from adapters — node authoring stays explicit and composable.
    """
    reg = registry or get_registry()
    from .art import ArtNodeExtension  # local import to avoid circularity

    extension = ArtNodeExtension()
    registered: list[str] = []
    for cls in await extension.get_node_list():
        reg.register(cls, module_path=f"art:{extension.name}")
        registered.append(cls.NODE_ID or cls.__name__)
    try:
        await extension.on_load({"registry": reg})
    except Exception:  # noqa: BLE001
        logger.warning("art_extension_on_load_failed", exc_info=True)
    logger.info("art_nodes_registered", count=len(registered))
    return registered


async def load_entrypoints(registry: NodeRegistry | None = None) -> list[str]:
    """Load any installed ``leagent.workflow.nodes`` entry points."""
    reg = registry or get_registry()
    registered: list[str] = []
    try:
        eps = entry_points(group=ENTRYPOINT_GROUP)
    except TypeError:  # older API shape
        eps = entry_points().get(ENTRYPOINT_GROUP, [])  # type: ignore
    for ep in eps:
        try:
            target = ep.load()
            extension = await _resolve_extension(target)
            if extension is None:
                continue
            nodes = await extension.get_node_list()
            module_path = f"entrypoint:{ep.name}"
            for cls in nodes:
                reg.register(cls, module_path=module_path)
                registered.append(cls.NODE_ID or cls.__name__)
            try:
                await extension.on_load({"registry": reg})
            except Exception:  # noqa: BLE001
                logger.warning("extension_on_load_failed", name=ep.name, exc_info=True)
        except Exception:  # noqa: BLE001
            logger.error("entrypoint_load_failed", name=str(ep), exc_info=True)
    return registered


async def load_directory(
    path: str | Path,
    registry: NodeRegistry | None = None,
    *,
    run_prestartup: bool = True,
) -> list[str]:
    """Load every ``*.py`` file or package under ``path`` as a node module."""
    reg = registry or get_registry()
    root = Path(path).expanduser()
    if not root.exists() or not root.is_dir():
        return []
    registered: list[str] = []
    for child in sorted(root.iterdir()):
        if child.name.startswith("_"):
            continue
        if run_prestartup:
            prestart = child / "prestartup_script.py" if child.is_dir() else None
            if prestart and prestart.exists():
                _run_file(prestart)
        try:
            registered.extend(await _load_module(child, reg))
        except Exception:  # noqa: BLE001
            logger.error("node_module_load_failed", path=str(child), exc_info=True)
    return registered


async def _load_module(path: Path, registry: NodeRegistry) -> list[str]:
    """Load a single file-or-package node module."""
    if path.is_dir():
        init_py = path / "__init__.py"
        if not init_py.exists():
            return []
        spec = importlib.util.spec_from_file_location(f"leagent_custom.{path.name}", init_py)
    elif path.suffix == ".py":
        spec = importlib.util.spec_from_file_location(f"leagent_custom.{path.stem}", path)
    else:
        return []

    if spec is None or spec.loader is None:
        return []

    module_path = f"fs:{path}"
    # Remove any previously registered nodes from this same file (hot-reload).
    registry.unregister_module(module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[attr-defined]

    node_classes: list[type[WorkflowNode]] = []
    candidate_attr = getattr(module, "NODE_CLASSES", None)
    if isinstance(candidate_attr, Iterable):
        for cls in candidate_attr:
            if isinstance(cls, type) and issubclass(cls, WorkflowNode):
                node_classes.append(cls)

    ep = getattr(module, "leagent_entrypoint", None)
    if callable(ep):
        ext = await _resolve_extension(ep() if not inspect.iscoroutinefunction(ep) else await ep())
        if ext is not None:
            node_classes.extend(await ext.get_node_list())

    registered: list[str] = []
    for cls in node_classes:
        registry.register(cls, module_path=module_path)
        registered.append(cls.NODE_ID or cls.__name__)
    if registered:
        logger.info("custom_nodes_loaded", path=str(path), count=len(registered))
    return registered


async def _resolve_extension(target: Any) -> NodeExtension | None:
    """Accept a class, instance, sync factory, or coroutine factory."""
    if target is None:
        return None
    if inspect.iscoroutine(target):
        target = await target
    if inspect.isclass(target) and issubclass(target, NodeExtension):
        return target()
    if isinstance(target, NodeExtension):
        return target
    if callable(target):
        result = target()
        if inspect.iscoroutine(result):
            result = await result
        if isinstance(result, NodeExtension):
            return result
    logger.warning("entrypoint_unexpected_target", target=repr(target))
    return None


def _run_file(path: Path) -> None:
    spec = importlib.util.spec_from_file_location(f"leagent_prestart.{path.stem}", path)
    if spec is None or spec.loader is None:
        return
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        logger.error("prestartup_script_failed", path=str(path), exc_info=True)


async def bootstrap(
    *,
    registry: NodeRegistry | None = None,
    custom_dirs: Iterable[str | Path] | None = None,
    tool_registry: Any | None = None,
    agent_registry: Any | None = None,
) -> dict[str, list[str]]:
    """One-shot bootstrap: built-ins + entrypoints + custom dirs + tool/agent nodes.

    If ``tool_registry`` is provided, every tool it contains is lifted
    into a dedicated ``Tool.<name>`` workflow node via
    :func:`leagent.workflow.nodes.tool_factory.register_tool_nodes`.

    If ``agent_registry`` is provided (or omitted, in which case the
    process-wide registry is used), every agent definition is lifted into a
    dedicated ``Agent.<name>`` node via
    :func:`leagent.workflow.nodes.agent_node_factory.register_agent_nodes`.
    """
    reg = registry or get_registry()
    summary: dict[str, list[str]] = {}
    summary["builtin"] = await load_builtins(reg)
    summary["art"] = await load_art_pack(reg)
    summary["entrypoints"] = await load_entrypoints(reg)
    dirs = list(custom_dirs or [])
    env_dir = os.environ.get("LEAGENT_CUSTOM_NODES_DIR")
    if env_dir:
        dirs.append(env_dir)
    for d in dirs:
        summary.setdefault("fs", []).extend(await load_directory(d, reg))
    if tool_registry is not None:
        from .tool_factory import register_tool_nodes
        summary["tools"] = register_tool_nodes(reg, tool_registry)
    try:
        from .agent_node_factory import register_agent_nodes

        if agent_registry is None:
            from leagent.runtime import get_agent_registry

            agent_registry = get_agent_registry()
        summary["agents"] = register_agent_nodes(reg, agent_registry)
    except Exception:  # noqa: BLE001 - agent nodes are optional palette extras
        logger.warning("agent_node_bootstrap_failed", exc_info=True)

    try:
        from .domain_model_factory import register_domain_model_nodes

        summary["domain_models"] = register_domain_model_nodes(reg)
    except Exception:  # noqa: BLE001 - domain-model nodes are optional palette extras
        logger.warning("domain_model_node_bootstrap_failed", exc_info=True)

    try:
        from leagent.llm.capabilities.bootstrap import bootstrap_capabilities

        caps = bootstrap_capabilities()
        summary["capabilities"] = [*caps.get("generation", []), *caps.get("domain", [])]
    except Exception:  # noqa: BLE001 - capability registry is optional discovery surface
        logger.warning("capability_bootstrap_failed", exc_info=True)
    return summary


def bootstrap_sync(**kwargs: Any) -> dict[str, list[str]]:
    """Synchronous wrapper for environments without an event loop yet."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            raise RuntimeError("bootstrap_sync called from a running loop")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(bootstrap(**kwargs))
