"""``BaseGenerationNode`` — Template Method base for art-asset nodes.

Hand-authored first-class generation nodes (image / video / 3D) subclass
this and declare only their *kind*, output socket, and node-specific
parameters. The base owns the shared execution skeleton:

1. resolve the prompt template against workflow state,
2. collect node params + any upstream :class:`MediaRef` conditioning,
3. call the unified :class:`GenerationService` (retries + failover),
4. register the produced bytes as a managed artifact (``FileRef``),
5. wrap it in a :class:`MediaRef` value object, write it to state, and
6. emit a ``NodeOutput.ui.gen_ui`` asset preview for the canvas.

No adapter, no factory — node authoring stays explicit and composable.
"""

from __future__ import annotations

import time
from typing import Any, ClassVar

import structlog

from leagent.llm.capabilities import (
    CapabilityContract,
    TaskType,
    kind_to_output,
    kind_to_task,
)
from leagent.workflow.io import (
    IO,
    Hidden,
    HiddenHolder,
    MediaRef,
    NodeOutput,
    OutputBase,
    Schema,
    to_gen_ui_tree,
)
from leagent.workflow.io.media import KIND_TO_IO_TYPE
from leagent.workflow.nodes.base import WorkflowNode

logger = structlog.get_logger(__name__)

#: Provider choices shared across art nodes; ``auto`` lets the service pick.
_COMMON_PROVIDERS = ["auto", "offline"]


def _media_output(kind: str, output_id: str) -> OutputBase:
    io_type = KIND_TO_IO_TYPE.get(kind, "*")
    if io_type == "IMAGE":
        return IO.Image.Output(id=output_id)
    if io_type == "VIDEO":
        return IO.Video.Output(id=output_id)
    if io_type == "MESH3D":
        return IO.Mesh3D.Output(id=output_id)
    if io_type == "AUDIO":
        return IO.Audio.Output(id=output_id)
    return IO.Any.Output(id=output_id)


class BaseGenerationNode(WorkflowNode):
    """Common skeleton for every generation node."""

    #: Media kind produced: ``image`` / ``video`` / ``model3d``.
    KIND: ClassVar[str] = "image"
    #: Output socket id (also the default state-variable hint).
    MEDIA_OUTPUT_ID: ClassVar[str] = "image"
    #: Fallback provider combo choices when the capability layer is offline.
    PROVIDERS: ClassVar[list[str]] = _COMMON_PROVIDERS
    #: Capability requirement this node binds against. When ``None`` it is
    #: derived from :attr:`KIND`; subclasses may pin extra input modalities.
    REQUIRES: ClassVar[CapabilityContract | None] = None

    # -- capability binding (decoupled from a single model) -------------

    @classmethod
    def capability_contract(cls) -> CapabilityContract:
        """The task + modality contract this node binds interchangeable models to."""
        if cls.REQUIRES is not None:
            return cls.REQUIRES
        task = kind_to_task(cls.KIND) or TaskType.IMAGE_GEN
        output = kind_to_output(cls.KIND)
        outputs = frozenset({output}) if output is not None else frozenset()
        return CapabilityContract(task=task, outputs=outputs)

    @classmethod
    def provider_choices(cls) -> list[str]:
        """Provider combo choices derived dynamically from the capability layer.

        A node is no longer hard-wired to a fixed provider list: every backend
        whose profile satisfies this node's contract becomes selectable, with
        ``auto`` (capability-driven selection) first and ``offline`` last.
        """
        choices = ["auto"]
        try:
            from leagent.llm.generation import get_generation_service

            providers = get_generation_service().palette_providers(cls.KIND)
        except Exception:  # noqa: BLE001 - fall back to static defaults
            providers = [p for p in cls.PROVIDERS if p != "auto"]
        for provider in providers:
            if provider not in choices:
                choices.append(provider)
        return choices

    # -- schema helpers (subclasses compose these) ----------------------

    @classmethod
    def _provider_input(cls) -> Any:
        return IO.Combo.Input(
            id="provider", choices=cls.provider_choices(), default="auto",
            optional=True,
            tooltip="Generation backend (auto = capability-driven selection).",
        )

    @classmethod
    def _model_input(cls) -> Any:
        return IO.String.Input(
            id="model", optional=True,
            tooltip="Optional model / checkpoint id (provider default when blank).",
        )

    @classmethod
    def _base_inputs(cls) -> list[Any]:
        return [
            IO.String.Input(
                id="prompt", multiline=True,
                tooltip="Text prompt describing the asset to generate.",
            ),
            cls._provider_input(),
            cls._model_input(),
            IO.Int.Input(
                id="retry_count", optional=True, default=2, min=0, max=10,
                tooltip="Per-backend retries before failover.",
            ),
            IO.String.Input(
                id="output", optional=True,
                tooltip="Optional state variable name to store the produced asset.",
            ),
        ]

    @classmethod
    def _media_output(cls) -> OutputBase:
        return _media_output(cls.KIND, cls.MEDIA_OUTPUT_ID)

    @classmethod
    def _base_outputs(cls) -> list[OutputBase]:
        return [
            cls._media_output(),
            IO.String.Output(id="preview_url"),
            IO.Boolean.Output(id="success"),
        ]

    @classmethod
    def _base_hidden(cls) -> list[Hidden]:
        return [
            Hidden.UNIQUE_ID,
            Hidden.WORKFLOW_STATE,
            Hidden.SESSION_ID,
            Hidden.USER_ID,
            Hidden.PROMPT,
        ]

    # -- overridable hooks ---------------------------------------------

    def collect_params(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Return generation params specific to this node (size, steps...)."""
        return {}

    def input_media(self, inputs: dict[str, Any]) -> MediaRef | None:
        """Return an upstream :class:`MediaRef` conditioning this generation."""
        return None

    def merge_conditioning_params(
        self, inputs: dict[str, Any], params: dict[str, Any]
    ) -> dict[str, Any]:
        """Fold camera / ControlNet objects from linked control nodes into params."""
        camera = inputs.get("camera")
        if isinstance(camera, dict) and camera:
            params["camera"] = camera
        control = inputs.get("control")
        if isinstance(control, dict) and control:
            params["controlnet"] = control
        return params

    # -- execution (Template Method) -----------------------------------

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        state = hidden.workflow_state
        prompt = inputs.get("prompt") or ""
        if state is not None and isinstance(prompt, str):
            prompt = state.resolve_template(prompt)
        prompt = str(prompt or "").strip()

        cond = self.input_media(inputs)
        if not prompt and cond is None:
            return NodeOutput(error=f"{type(self).NODE_ID}: missing 'prompt'")

        provider = inputs.get("provider") or "auto"
        provider_arg = None if provider in ("auto", "", None) else str(provider)
        retry_count = int(inputs.get("retry_count") or 0)

        params = self.collect_params(inputs)
        params = self.merge_conditioning_params(inputs, params)
        camera = params.get("camera")
        if isinstance(camera, dict) and camera:
            preset = camera.get("preset")
            if preset and preset != "custom":
                prompt = f"{prompt}, {preset} camera view".strip(", ")
            else:
                az = float(camera.get("azimuth", 0))
                el = float(camera.get("elevation", 0))
                prompt = f"{prompt}, view azimuth {az:.0f}° elevation {el:.0f}°".strip(", ")
        model = inputs.get("model")
        if isinstance(model, str) and model.strip():
            params["model"] = model.strip()
        if cond is not None:
            params["image"] = cond.to_dict()

        from leagent.llm.generation import get_generation_service

        svc = get_generation_service()
        start = time.monotonic()
        out = await svc.generate(
            kind=type(self).KIND,
            prompt=prompt or (cond.meta.get("prompt") if cond else "") or "asset",
            provider=provider_arg,
            max_retries=retry_count,
            **params,
        )
        duration_ms = int((time.monotonic() - start) * 1000)

        if not out.success:
            logger.warning("art_node_generation_failed", node=type(self).NODE_ID, error=out.error)
            return NodeOutput(
                values=(None, "", False),
                error=out.error or "generation failed",
                metadata={"duration_ms": duration_ms, "kind": type(self).KIND},
            )

        ref = await self._persist(out, hidden, prompt)
        if ref is None:
            return NodeOutput(values=(None, "", False), error="failed to persist asset")

        if state is not None and inputs.get("output"):
            state.set(str(inputs["output"]), ref.to_dict())

        self._emit_progress(hidden, ref)

        return NodeOutput(
            values=(ref.to_dict(), ref.src or "", True),
            ui={"gen_ui": to_gen_ui_tree([ref], title=type(self).DISPLAY_TITLE)},
            metadata={
                "duration_ms": duration_ms,
                "kind": type(self).KIND,
                "provider": out.provider,
                "model": out.model,
                "file_id": ref.file_id,
                "placeholder": bool(out.meta.get("placeholder")),
                "attempts": out.meta.get("attempts"),
            },
        )

    DISPLAY_TITLE: ClassVar[str] = "Generated asset"

    async def _persist(self, out: Any, hidden: HiddenHolder, prompt: str) -> MediaRef | None:
        meta = {"prompt": prompt, "provider": out.provider, "model": out.model, **out.meta}
        if out.data is None and out.meta.get("url"):
            return MediaRef(
                kind=type(self).KIND, preview_url=str(out.meta["url"]),
                mime=out.mime, filename=out.filename, meta=meta,
            )
        from leagent.file.tool_output import register_tool_artifact

        attachment = await register_tool_artifact(
            out.data or b"",
            filename=out.filename or f"{type(self).KIND}.bin",
            content_type=out.mime or None,
            session_id=hidden.session_id,
            user_id=hidden.user_id,
        )
        ref = MediaRef.from_artifact(attachment, kind=type(self).KIND, mime=out.mime, meta=meta)
        if ref is None:
            return None
        for key in ("width", "height"):
            if out.meta.get(key) is not None:
                setattr(ref, key, out.meta[key])
        return ref

    def _emit_progress(self, hidden: HiddenHolder, ref: MediaRef) -> None:
        progress = getattr(hidden, "progress", None)
        if progress is None:
            return
        try:
            progress.update(
                preview={"type": ref.kind, "name": ref.filename, "src": ref.src},
                node_id=hidden.unique_id,
            )
        except Exception:  # noqa: BLE001 - preview is best-effort
            logger.debug("art_node_progress_failed", node=type(self).NODE_ID)


__all__ = ["BaseGenerationNode"]
