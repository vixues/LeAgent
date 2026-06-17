"""Factory that lifts registered domain models into ``Model.<task>.<provider>``
workflow nodes.

Domain models are non-chat capabilities (image generation, TTS, ASR, and
future video) exposed through the LLM service's task router. This factory
mirrors :mod:`leagent.workflow.nodes.tool_factory` and
:mod:`leagent.workflow.nodes.agent_node_factory`: each registered domain
provider/model becomes a first-class palette node whose schema is derived
from the adapter's parameter schema and whose typed ``IMAGE``/``AUDIO``/
``FILE`` sockets wire into the graph.

``register_domain_model_nodes`` resolves the process-wide
:class:`~leagent.llm.domain_registry.DomainModelRegistry`, registers the
built-in adapters (for providers with configured credentials) plus any
``leagent.domain_models`` entry-point plugins, and lifts each adapter into a
node via :func:`leagent.workflow.nodes.domain_model_nodes.build_domain_model_node`.
It is safe to call with no adapters configured (returns an empty list).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from leagent.workflow.nodes.registry import NodeRegistry

logger = structlog.get_logger(__name__)

_NODE_ID_PREFIX = "Model."

#: Domain-model tasks that are now served by *first-class* art nodes
#: (``Art.ImageGen`` / ``Art.VideoGen`` / ``Art.Mesh3D``) instead of the
#: auto-generated ``Model.<task>.<provider>`` factory shim. We deliberately
#: stop lifting these adapters into workflow nodes — the adapters remain
#: available to the LLM service's ``generate_image`` path, but the canvas
#: composes art via the hand-authored, typed-socket art pack. Audio
#: (``tts`` / ``asr``) is intentionally retained on the factory path.
_DEPRECATED_FACTORY_TASKS = {"image_gen", "video", "mesh_gen"}


def _spec_task(spec: Any) -> str:
    """Best-effort extraction of the domain task for an adapter/spec."""
    inner = getattr(spec, "spec", None)
    task = getattr(inner, "task", None) or getattr(spec, "task", None)
    return str(task or "").lower()


def register_domain_model_nodes(
    node_registry: NodeRegistry,
    domain_registry: Any | None = None,
) -> list[str]:
    """Register one ``Model.<task>.<provider>`` node per domain model.

    Args:
        node_registry: the workflow node registry to populate.
        domain_registry: the domain-model/provider registry. When ``None``
            the function resolves the process-wide registry lazily; if that
            is unavailable (Phase 1, before adapters land) it no-ops.

    Returns:
        The list of registered node ids (empty until adapters are wired).
    """
    if domain_registry is None:
        try:
            from leagent.llm.domain_models import register_builtin_domain_models
            from leagent.llm.domain_registry import (
                get_domain_registry,
                load_domain_model_plugins,
            )

            domain_registry = get_domain_registry()
            register_builtin_domain_models(domain_registry)
            load_domain_model_plugins()
        except Exception:  # noqa: BLE001 - domain registry is optional
            logger.debug("domain_model_registry_unavailable", exc_info=True)
            return []

    builder = None
    try:
        from leagent.workflow.nodes.domain_model_nodes import build_domain_model_node

        builder = build_domain_model_node
    except Exception:  # noqa: BLE001 - node builder lands with the adapters
        logger.debug("domain_model_node_builder_unavailable")
        return []

    registered: list[str] = []
    skipped_art: list[str] = []
    for spec in _iter_domain_specs(domain_registry):
        if _spec_task(spec) in _DEPRECATED_FACTORY_TASKS:
            # Art tasks are served by the first-class art node pack.
            skipped_art.append(_spec_task(spec))
            continue
        try:
            cls = builder(spec)
            node_registry.register(
                cls, module_path=f"domain_model_factory:{cls.NODE_ID}"
            )
            registered.append(cls.NODE_ID)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "domain_model_node_failed",
                model=getattr(spec, "name", spec),
                error=str(exc),
                exc_info=True,
            )

    logger.info(
        "domain_model_nodes_registered",
        count=len(registered),
        skipped_art=len(skipped_art),
    )
    return registered


def _iter_domain_specs(domain_registry: Any) -> list[Any]:
    """Best-effort enumeration of a domain registry's model specs."""
    for attr in ("all", "list_models", "specs"):
        fn = getattr(domain_registry, attr, None)
        if callable(fn):
            try:
                return list(fn())
            except Exception:  # noqa: BLE001
                continue
    return []


__all__ = ["register_domain_model_nodes"]
