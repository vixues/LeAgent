"""Model capability and task routing types for providers.yaml v2."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

ModelKind = Literal["chat", "embedding", "image_gen", "tts", "asr"]

VALID_INPUT_MODALITIES = frozenset({"text", "image", "audio", "pdf"})
VALID_OUTPUT_MODALITIES = frozenset({"text", "image", "audio"})


class ModelTask(StrEnum):
    """Logical LLM invocation roles."""

    CHAT = "chat"
    FAST = "fast"
    VISION = "vision"
    COMPRESSION = "compression"
    TITLE = "title"
    EMBEDDING = "embedding"
    IMAGE_GEN = "image_gen"
    TTS = "tts"
    ASR = "asr"


@dataclass(frozen=True)
class ModelCapabilities:
    """Capability matrix for a single model."""

    input: frozenset[str] = frozenset({"text"})
    output: frozenset[str] = frozenset({"text"})
    tool_call: bool = False
    reasoning: bool = False

    def supports_input(self, modality: str) -> bool:
        return modality in self.input

    def supports_output(self, modality: str) -> bool:
        return modality in self.output

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> ModelCapabilities:
        if not isinstance(raw, dict):
            return cls()
        inp = raw.get("input")
        out = raw.get("output")
        input_set = frozenset(str(x) for x in inp if isinstance(x, str)) if isinstance(inp, list) else frozenset({"text"})
        output_set = frozenset(str(x) for x in out if isinstance(x, str)) if isinstance(out, list) else frozenset({"text"})
        if not input_set:
            input_set = frozenset({"text"})
        if not output_set:
            output_set = frozenset({"text"})
        return cls(
            input=input_set,
            output=output_set,
            tool_call=bool(raw.get("tool_call")),
            reasoning=bool(raw.get("reasoning")),
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "input": sorted(self.input),
            "output": sorted(self.output),
        }
        if self.tool_call:
            d["tool_call"] = True
        if self.reasoning:
            d["reasoning"] = True
        return d


@dataclass(frozen=True)
class ModelSpec:
    """Resolved model metadata from providers.yaml."""

    name: str
    provider: str
    kind: ModelKind = "chat"
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    context_window: int = 0
    limits: dict[str, Any] = field(default_factory=dict)
    pricing: dict[str, float] = field(default_factory=dict)
    enabled: bool = True
    description: str = ""

    @classmethod
    def from_provider_entry(
        cls,
        provider_name: str,
        raw: dict[str, Any],
    ) -> ModelSpec:
        name = str(raw.get("name") or "").strip()
        kind_raw = str(raw.get("kind") or "chat").strip().lower()
        kind: ModelKind = (
            kind_raw if kind_raw in ("chat", "embedding", "image_gen", "tts", "asr") else "chat"
        )
        caps = ModelCapabilities.from_dict(raw.get("capabilities") if isinstance(raw.get("capabilities"), dict) else None)
        # Legacy bool flags → capabilities (used only by migrate CLI, not runtime)
        if raw.get("supports_tools"):
            caps = ModelCapabilities(
                input=caps.input,
                output=caps.output,
                tool_call=True,
                reasoning=caps.reasoning or bool(raw.get("supports_thinking")),
            )
        if raw.get("supports_vision") and "image" not in caps.input:
            caps = ModelCapabilities(
                input=frozenset(set(caps.input) | {"image"}),
                output=caps.output,
                tool_call=caps.tool_call,
                reasoning=caps.reasoning or bool(raw.get("supports_thinking")),
            )
        pricing_raw = raw.get("pricing") if isinstance(raw.get("pricing"), dict) else {}
        pricing: dict[str, float] = {}
        for key in ("input_per_1m", "output_per_1m"):
            val = pricing_raw.get(key)
            if val is not None:
                pricing[key] = float(val)
        if not pricing:
            for key in ("price_input_per_1m", "price_output_per_1m"):
                val = raw.get(key)
                if val is not None:
                    pricing["input_per_1m" if "input" in key else "output_per_1m"] = float(val)
        limits = raw.get("limits") if isinstance(raw.get("limits"), dict) else {}
        return cls(
            name=name,
            provider=provider_name,
            kind=kind,
            capabilities=caps,
            context_window=int(raw.get("context_window") or 0),
            limits=dict(limits),
            pricing=pricing,
            enabled=raw.get("enabled", True) is not False,
            description=str(raw.get("description") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "kind": self.kind,
            "enabled": self.enabled,
            "capabilities": self.capabilities.to_dict(),
        }
        if self.context_window:
            d["context_window"] = self.context_window
        if self.limits:
            d["limits"] = self.limits
        if self.pricing:
            d["pricing"] = self.pricing
        if self.description:
            d["description"] = self.description
        return d


@dataclass(frozen=True)
class TaskBinding:
    """One entry under routing.tasks."""

    provider: str = ""
    model: str = ""
    inherit: str = ""
    max_tokens: int = 0
    temperature: float = 0.0
    timeout: float = 0.0

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> TaskBinding:
        if not isinstance(raw, dict):
            return cls()
        return cls(
            provider=str(raw.get("provider") or "").strip(),
            model=str(raw.get("model") or "").strip(),
            inherit=str(raw.get("inherit") or "").strip(),
            max_tokens=int(raw.get("max_tokens") or 0),
            temperature=float(raw.get("temperature") or 0.0),
            timeout=float(raw.get("timeout") or 0.0),
        )


@dataclass
class ResolvedModel:
    """Output of TaskResolver.resolve()."""

    task: ModelTask
    provider: str
    model: str
    spec: ModelSpec
    reason: str
    max_tokens: int = 4096
    temperature: float = 0.1
    timeout: float = 120.0
