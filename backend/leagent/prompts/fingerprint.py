"""SHA-256 fingerprints for :class:`BuiltPrompt`.

With the source-based context system, fingerprinting is handled by
:class:`ContextManager`. These helpers remain for the fallback builder
path and for any caller that needs to hash a LayerResult list directly.
"""

from __future__ import annotations

import hashlib

from leagent.prompts.types import LayerResult

STABLE_SOURCE_IDS: tuple[str, ...] = (
    "identity",
    "capabilities",
    "policies",
    "environment",
    "project_memory",
    "user_instructions",
)


def _canonical(layers: list[LayerResult], names: tuple[str, ...]) -> str:
    index = {layer.name: layer for layer in layers}
    parts: list[str] = []
    for name in names:
        layer = index.get(name)
        if layer is None:
            continue
        parts.append(f"§{name}§\n{layer.body}")
    return "\n".join(parts)


def stable_fingerprint(layers: list[LayerResult], variant_key: str) -> str:
    canonical = variant_key + "\n" + _canonical(layers, STABLE_SOURCE_IDS)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def full_fingerprint(
    layers: list[LayerResult],
    variant_key: str,
    *,
    all_names: tuple[str, ...] | None = None,
) -> str:
    names = all_names or tuple(layer.name for layer in layers)
    canonical = variant_key + "\n" + _canonical(layers, names)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = ["STABLE_SOURCE_IDS", "full_fingerprint", "stable_fingerprint"]
