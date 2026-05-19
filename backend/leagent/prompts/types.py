"""Typed shapes used by the prompt builder.

These dataclasses are the I/O boundary between :class:`PromptBuilder`,
the per-layer collectors, and the call sites that consume the final
system prompt (controller, query engine, workflows).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RenderTarget(str, Enum):
    """Which provider shape the final :class:`BuiltPrompt` is rendered for.

    * ``OPENAI`` — single ``{"role": "system", "content": str}`` message.
    * ``ANTHROPIC`` — optionally splits on cache boundaries so the
      renderer can emit ``cache_control: {"type": "ephemeral"}`` markers.
    * ``PLAIN`` — return just the concatenated string (used by the
      plan-execute controller and the rule judge).
    """

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    PLAIN = "plain"


@dataclass(slots=True)
class PromptVariant:
    """One template variant loaded from ``prompts/templates/``.

    Variants are the unit the registry keys on. A template file's YAML
    front-matter supplies ``name``, an optional ``variant`` (defaults to
    ``default``), plus runtime knobs (layer toggles, budgets, tags) and
    a rendered ``body`` (markdown without the front-matter).

    ``body`` is treated as the L0 Persona layer's source text. Jinja-lite
    ``{{var}}`` substitution is applied at collection time using
    :attr:`PromptContext.template_vars`.
    """

    name: str
    variant: str = "default"
    body: str = ""
    layers: list[str] = field(
        default_factory=lambda: [
            "persona",
            "capabilities",
            "policies",
            "environment",
            "project_memory",
            "recall",
            "session_state",
            "turn_extras",
        ]
    )
    budget_chars: dict[str, int] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    policies: list[str] = field(default_factory=list)
    requires_tools: list[str] = field(default_factory=list)
    description: str = ""
    source_path: str = ""

    @property
    def key(self) -> str:
        """Unique key used by the registry cache."""
        return f"{self.name}:{self.variant}"


@dataclass(slots=True)
class LayerResult:
    """Output of one collector function.

    Attributes:
        name: One of the eight canonical layer names.
        body: The rendered text for this layer (may be empty — empty
            layers are skipped by the renderer).
        tokens: Approximate token count (``len(body) // 3``) — cheap
            heuristic used by the budget enforcer.
        truncated: Set when the budget enforcer trimmed this layer.
        cache_boundary: When True, a provider-aware renderer may place
            a cache-control marker *after* this layer.
        metadata: Free-form per-layer data (retained for observability
            in the ``prompt_build`` structlog event).
    """

    name: str
    body: str = ""
    tokens: int = 0
    truncated: bool = False
    cache_boundary: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.body.strip()


@dataclass(slots=True)
class BuiltPrompt:
    """The final assembled prompt handed back to the agent runtime.

    Callers generally read :attr:`system_text` and feed it into their
    LLM call directly. :attr:`messages` is supplied for providers where
    the system prompt carries cache-control markers (Anthropic); in that
    case each list element is a content block for a *single* system
    message.

    The fingerprint pair (:attr:`stable_hash` / :attr:`full_hash`) lets
    the session manager persist cache identities across turns.
    """

    system_text: str
    messages: list[dict[str, Any]]
    layers: list[LayerResult]
    render_target: RenderTarget
    stable_hash: str
    full_hash: str
    total_chars: int
    truncations: list[str] = field(default_factory=list)
    variant_key: str = ""

    def layer(self, name: str) -> LayerResult | None:
        for layer in self.layers:
            if layer.name == name:
                return layer
        return None

    def layer_bytes(self) -> dict[str, int]:
        return {layer.name: len(layer.body) for layer in self.layers}
