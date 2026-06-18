"""Builders that lift existing descriptors into :class:`CapabilityProfile`.

These mappers are the bridge that lets the three legacy systems feed one
unified registry without rewriting any of them:

* :func:`from_model_spec` — chat / embedding / image_gen / tts / asr models
  resolved from ``providers.yaml`` (:class:`leagent.llm.model_spec.ModelSpec`).
* :func:`from_domain_spec` — domain-model adapters
  (:class:`leagent.llm.domain_registry.DomainModelSpec`).
* :func:`from_generation_backend` — media generation strategies
  (:class:`leagent.llm.generation.base.GenerationBackend`).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .profile import BackendClass, CapabilityProfile, Modality, TaskType

# Map a generation *kind* to its (task, output-modality) pair.
_KIND_TO_TASK: dict[str, tuple[TaskType, Modality]] = {
    "image": (TaskType.IMAGE_GEN, Modality.IMAGE),
    "video": (TaskType.VIDEO_GEN, Modality.VIDEO),
    "model3d": (TaskType.MESH_GEN, Modality.MODEL3D),
    "vfx": (TaskType.VFX_GEN, Modality.VFX),
    "audio": (TaskType.AUDIO_GEN, Modality.AUDIO),
}

# Map a domain task string to the unified TaskType.
_DOMAIN_TASK_TO_TASK: dict[str, TaskType] = {
    "image_gen": TaskType.IMAGE_GEN,
    "video": TaskType.VIDEO_GEN,
    "video_gen": TaskType.VIDEO_GEN,
    "mesh_gen": TaskType.MESH_GEN,
    "tts": TaskType.TTS,
    "asr": TaskType.ASR,
}


def kind_to_task(kind: str) -> TaskType | None:
    pair = _KIND_TO_TASK.get(kind)
    return pair[0] if pair else None


def kind_to_output(kind: str) -> Modality | None:
    pair = _KIND_TO_TASK.get(kind)
    return pair[1] if pair else None


# ---------------------------------------------------------------------------
# Chat / embedding models (providers.yaml)
# ---------------------------------------------------------------------------


def from_model_spec(spec: Any) -> CapabilityProfile:
    """Build a profile from a :class:`leagent.llm.model_spec.ModelSpec`."""
    caps = spec.capabilities
    inputs = {Modality(m) for m in caps.input if _valid_modality(m)}
    outputs = {Modality(m) for m in caps.output if _valid_modality(m)}
    inputs = inputs or {Modality.TEXT}
    outputs = outputs or {Modality.TEXT}

    tasks: set[TaskType] = set()
    kind = spec.kind
    if kind == "chat":
        tasks.add(TaskType.CHAT)
        if Modality.IMAGE in inputs:
            tasks.add(TaskType.VISION)
    elif kind == "embedding":
        tasks.add(TaskType.EMBEDDING)
    elif kind == "image_gen":
        tasks.add(TaskType.IMAGE_GEN)
    elif kind == "tts":
        tasks.add(TaskType.TTS)
    elif kind == "asr":
        tasks.add(TaskType.ASR)

    if kind == "chat":
        backend_class = (
            BackendClass.MULTIMODAL_LLM if Modality.IMAGE in inputs else BackendClass.TEXT_LLM
        )
    elif kind == "embedding":
        backend_class = BackendClass.TEXT_LLM
    else:
        backend_class = BackendClass.DEDICATED_IMAGE if kind == "image_gen" else BackendClass.EXTERNAL_API

    return CapabilityProfile(
        id=f"{kind}:{spec.provider}:{spec.name}",
        provider=spec.provider,
        backend_class=backend_class,
        inputs=frozenset(inputs),
        outputs=frozenset(outputs),
        tasks=frozenset(tasks),
        default_model=spec.name,
        requires_credentials=True,
        supports_streaming=kind == "chat",
        cost_tier=2,
        metadata={
            "kind": kind,
            "tool_call": bool(caps.tool_call),
            "reasoning": bool(caps.reasoning),
            "context_window": int(getattr(spec, "context_window", 0) or 0),
        },
    )


# ---------------------------------------------------------------------------
# Domain-model adapters
# ---------------------------------------------------------------------------


def from_domain_spec(spec: Any, *, availability: Callable[[], bool] | None = None) -> CapabilityProfile:
    """Build a profile from a :class:`DomainModelSpec`."""
    task = _DOMAIN_TASK_TO_TASK.get(str(spec.task).lower())
    tasks = {task} if task is not None else set()

    output_mod = _domain_output_modality(spec.output)
    outputs = {output_mod} if output_mod else {Modality.TEXT}

    # Infer inputs from declared params (IMAGE/AUDIO io types) + always text.
    inputs: set[Modality] = {Modality.TEXT}
    for param in getattr(spec, "params", ()) or ():
        io_type = str(getattr(param, "io_type", "")).upper()
        if io_type == "IMAGE":
            inputs.add(Modality.IMAGE)
        elif io_type == "AUDIO":
            inputs.add(Modality.AUDIO)

    if str(spec.provider).lower() == "local":
        backend_class = BackendClass.LOCAL_PIPELINE
        cost_tier = 1
        requires_credentials = False
    else:
        backend_class = (
            BackendClass.DEDICATED_IMAGE if task == TaskType.IMAGE_GEN else BackendClass.EXTERNAL_API
        )
        cost_tier = 2
        requires_credentials = True

    return CapabilityProfile(
        id=f"domain:{spec.task}:{spec.provider}",
        provider=spec.provider,
        backend_class=backend_class,
        inputs=frozenset(inputs),
        outputs=frozenset(outputs),
        tasks=frozenset(tasks),
        default_model=getattr(spec, "model", "") or "",
        requires_credentials=requires_credentials,
        supports_progress=bool(getattr(spec, "supports_progress", False)),
        cost_tier=cost_tier,
        availability=availability,
        metadata={"domain_task": spec.task, "display_name": getattr(spec, "display_name", "")},
    )


# ---------------------------------------------------------------------------
# Generation backends
# ---------------------------------------------------------------------------


def from_generation_backend(backend: Any) -> CapabilityProfile:
    """Build a profile from a :class:`GenerationBackend` strategy."""
    tasks: set[TaskType] = set()
    outputs: set[Modality] = set()
    for kind in getattr(backend, "kinds", ()):  # e.g. ("image",)
        pair = _KIND_TO_TASK.get(kind)
        if pair:
            tasks.add(pair[0])
            outputs.add(pair[1])
    # Image backends can also serve the upscale role (image-conditioned).
    if TaskType.IMAGE_GEN in tasks:
        tasks.add(TaskType.UPSCALE)

    name = str(getattr(backend, "name", "")) or "unknown"
    if name == "offline":
        backend_class = BackendClass.OFFLINE
        cost_tier = 0
        requires_credentials = False
    elif name == "local":
        backend_class = BackendClass.LOCAL_PIPELINE
        cost_tier = 1
        requires_credentials = False
    elif name.startswith("http_"):
        backend_class = BackendClass.EXTERNAL_API
        cost_tier = 2
        requires_credentials = True
    else:
        backend_class = BackendClass.DEDICATED_IMAGE
        cost_tier = 2
        requires_credentials = True

    # Image conditioning support → accepts image input.
    inputs = {Modality.TEXT}
    if outputs & {Modality.IMAGE, Modality.VIDEO, Modality.MODEL3D, Modality.VFX}:
        inputs.add(Modality.IMAGE)

    available = getattr(backend, "available", None)
    return CapabilityProfile(
        id=f"gen:{name}",
        provider=name,
        backend_class=backend_class,
        inputs=frozenset(inputs),
        outputs=frozenset(outputs),
        tasks=frozenset(tasks),
        requires_credentials=requires_credentials,
        cost_tier=cost_tier,
        availability=available if callable(available) else None,
        metadata={"kinds": list(getattr(backend, "kinds", ()))},
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _valid_modality(value: Any) -> bool:
    try:
        Modality(str(value))
        return True
    except ValueError:
        return False


def _domain_output_modality(output: Any) -> Modality | None:
    mapping = {
        "text": Modality.TEXT,
        "image": Modality.IMAGE,
        "audio": Modality.AUDIO,
        "video": Modality.VIDEO,
        "model3d": Modality.MODEL3D,
    }
    return mapping.get(str(output).lower())


__all__ = [
    "from_domain_spec",
    "from_generation_backend",
    "from_model_spec",
    "kind_to_output",
    "kind_to_task",
]
