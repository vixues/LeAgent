"""Core capability types — the single contract every backend derives from.

The capability layer unifies three previously separate descriptions of "a
model/backend with a capability profile":

* chat models (:class:`leagent.llm.model_spec.ModelCapabilities`),
* domain-model adapters (:class:`leagent.llm.domain_registry.DomainModelSpec`),
* generation backends (:class:`leagent.llm.generation.base.GenerationBackend`).

A :class:`CapabilityProfile` classifies one backend by *modality* (what it
consumes / produces), *task type* (the logical role it can fill) and
*backend class* (multimodal LLM / dedicated image model / external API /
local pipeline / offline). A :class:`CapabilityContract` is the dual: a
caller's requirement (a node, the chat router, a tool) that profiles are
matched against.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Modality(StrEnum):
    """A unit of input/output a backend can consume or produce."""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    MODEL3D = "model3d"
    PDF = "pdf"


class TaskType(StrEnum):
    """Logical role a backend can fill, spanning chat + generation."""

    CHAT = "chat"
    VISION = "vision"
    IMAGE_GEN = "image_gen"
    VIDEO_GEN = "video_gen"
    MESH_GEN = "mesh_gen"
    UPSCALE = "upscale"
    TTS = "tts"
    ASR = "asr"
    EMBEDDING = "embedding"


class BackendClass(StrEnum):
    """How a backend is realised — the capability-profile classifier."""

    #: Conversational model that natively handles multiple modalities.
    MULTIMODAL_LLM = "multimodal_llm"
    #: Text-only / single-modality conversational or embedding model.
    TEXT_LLM = "text_llm"
    #: Dedicated image-generation model (DALL-E, Wanx, ...).
    DEDICATED_IMAGE = "dedicated_image"
    #: External generation HTTP API (video / 3D services).
    EXTERNAL_API = "external_api"
    #: In-process local pipeline (diffusers, whisper, ...).
    LOCAL_PIPELINE = "local_pipeline"
    #: Always-available deterministic placeholder floor.
    OFFLINE = "offline"


def _as_modalities(values: Any) -> frozenset[Modality]:
    out: set[Modality] = set()
    for v in values or ():
        if isinstance(v, Modality):
            out.add(v)
            continue
        try:
            out.add(Modality(str(v)))
        except ValueError:
            continue
    return frozenset(out)


def _as_tasks(values: Any) -> frozenset[TaskType]:
    out: set[TaskType] = set()
    for v in values or ():
        if isinstance(v, TaskType):
            out.add(v)
            continue
        try:
            out.add(TaskType(str(v)))
        except ValueError:
            continue
    return frozenset(out)


@dataclass(frozen=True)
class CapabilityProfile:
    """Capability description for one registered backend.

    ``id`` is unique within a registry (e.g. ``image_gen:openai:dall-e-3`` or
    ``chat:openai:gpt-4o``). The optional ``availability`` callable lets the
    registry report runtime usability (credentials present, pipeline
    importable, ...) without the registry having to know provider internals.
    """

    id: str
    provider: str
    backend_class: BackendClass
    inputs: frozenset[Modality] = frozenset({Modality.TEXT})
    outputs: frozenset[Modality] = frozenset({Modality.TEXT})
    tasks: frozenset[TaskType] = frozenset()
    default_model: str = ""
    requires_credentials: bool = False
    supports_progress: bool = False
    supports_streaming: bool = False
    #: 0 = free/offline/local; higher = more expensive / rate-limited.
    cost_tier: int = 0
    availability: Callable[[], bool] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalise loosely-typed construction (str sets) into enums.
        object.__setattr__(self, "inputs", _as_modalities(self.inputs))
        object.__setattr__(self, "outputs", _as_modalities(self.outputs))
        object.__setattr__(self, "tasks", _as_tasks(self.tasks))

    def available(self) -> bool:
        """Whether this backend is usable right now."""
        if self.availability is None:
            return True
        try:
            return bool(self.availability())
        except Exception:  # noqa: BLE001 - availability probes are best-effort
            return False

    def supports_input(self, modality: Modality | str) -> bool:
        try:
            return Modality(str(modality)) in self.inputs
        except ValueError:
            return False

    def supports_output(self, modality: Modality | str) -> bool:
        try:
            return Modality(str(modality)) in self.outputs
        except ValueError:
            return False

    def supports_task(self, task: TaskType | str) -> bool:
        try:
            return TaskType(str(task)) in self.tasks
        except ValueError:
            return False

    @property
    def is_offline(self) -> bool:
        return self.backend_class == BackendClass.OFFLINE

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "backend_class": self.backend_class.value,
            "inputs": sorted(m.value for m in self.inputs),
            "outputs": sorted(m.value for m in self.outputs),
            "tasks": sorted(t.value for t in self.tasks),
            "default_model": self.default_model,
            "requires_credentials": self.requires_credentials,
            "supports_progress": self.supports_progress,
            "supports_streaming": self.supports_streaming,
            "cost_tier": self.cost_tier,
            "available": self.available(),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class CapabilityContract:
    """A caller's requirement matched against profiles.

    The contract is intentionally minimal: a task plus the modalities the
    caller needs the backend to accept (``inputs``) and produce (``outputs``).
    Empty modality sets mean "no constraint".
    """

    task: TaskType
    inputs: frozenset[Modality] = frozenset()
    outputs: frozenset[Modality] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.task, TaskType):
            object.__setattr__(self, "task", TaskType(str(self.task)))
        object.__setattr__(self, "inputs", _as_modalities(self.inputs))
        object.__setattr__(self, "outputs", _as_modalities(self.outputs))

    def matches(self, profile: CapabilityProfile) -> bool:
        if self.task not in profile.tasks:
            return False
        if not self.inputs <= profile.inputs:
            return False
        if not self.outputs <= profile.outputs:
            return False
        return True


__all__ = [
    "BackendClass",
    "CapabilityContract",
    "CapabilityProfile",
    "Modality",
    "TaskType",
]
