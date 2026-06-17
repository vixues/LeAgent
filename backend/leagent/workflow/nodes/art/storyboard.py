"""Storyboard orchestration nodes for multi-shot workflows.

Design:
- Each shot is a standalone node (`Art.Shot`) that can be wired to its own
  camera/control/image inputs.
- A storyboard node (`Art.Storyboard`) consumes an ARRAY of shot objects and
  produces an ARRAY of generated VIDEO MediaRefs (one per shot).

This keeps node-level connections per shot while still enabling batch
orchestration and independent control.
"""

from __future__ import annotations

from typing import Any, ClassVar

from leagent.workflow.io import IO, Hidden, HiddenHolder, MediaRef, NodeOutput, Schema, to_gen_ui_tree
from leagent.workflow.nodes.base import WorkflowNode


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class ShotNode(WorkflowNode):
    """A single storyboard shot spec with its own independent controls."""

    NODE_ID = "Art.Shot"

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id=cls.NODE_ID,
            display_name="Shot",
            category="art/storyboard",
            description="One shot specification (prompt + optional conditioning). Connect shots into Art.Storyboard.",
            inputs=[
                IO.String.Input(
                    id="name",
                    optional=True,
                    tooltip="Optional shot name (e.g. 'Establishing', 'Close-up').",
                ),
                IO.String.Input(
                    id="prompt",
                    multiline=True,
                    tooltip="Shot prompt. You can still template with ${var.*}.",
                ),
                IO.Image.Input(
                    id="image",
                    optional=True,
                    tooltip="Optional reference image for image-to-video.",
                ),
                IO.Object.Input(
                    id="camera",
                    optional=True,
                    tooltip="Optional camera rig from Art.CameraControl.",
                ),
                IO.Object.Input(
                    id="control",
                    optional=True,
                    tooltip="Optional ControlNet bundle (e.g. from Art.PoseControl).",
                ),
                IO.Int.Input(
                    id="duration",
                    optional=True,
                    default=3,
                    min=1,
                    max=20,
                    tooltip="Shot duration (seconds).",
                ),
                IO.Int.Input(
                    id="fps",
                    optional=True,
                    default=24,
                    min=8,
                    max=60,
                    tooltip="Frames per second.",
                ),
            ],
            outputs=[
                IO.Object.Output(id="shot"),
            ],
            hidden=[Hidden.UNIQUE_ID, Hidden.WORKFLOW_STATE],
        )

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        state = hidden.workflow_state
        prompt = inputs.get("prompt") or ""
        if state is not None and isinstance(prompt, str):
            prompt = state.resolve_template(prompt)
        prompt = str(prompt or "").strip()
        if not prompt:
            return NodeOutput(error="Art.Shot: missing 'prompt'")

        image_ref = MediaRef.from_dict(inputs.get("image"))
        shot: dict[str, Any] = {
            "type": "shot",
            "name": str(inputs.get("name") or "").strip() or None,
            "prompt": prompt,
            "duration": _as_int(inputs.get("duration"), 3),
            "fps": _as_int(inputs.get("fps"), 24),
        }
        if image_ref is not None:
            shot["image"] = image_ref.to_dict()
        if isinstance(inputs.get("camera"), dict):
            shot["camera"] = inputs["camera"]
        if isinstance(inputs.get("control"), dict):
            shot["controlnet"] = inputs["control"]
        return NodeOutput(values=(shot,))


class StoryboardNode(WorkflowNode):
    """Generate multiple shots as a storyboard (multi-shot orchestration)."""

    NODE_ID = "Art.Storyboard"
    DISPLAY_TITLE: ClassVar[str] = "Storyboard"

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id=cls.NODE_ID,
            display_name="Storyboard",
            category="art/storyboard",
            description="Generate a sequence of shots. Connect multiple Art.Shot outputs into the shots ARRAY input.",
            inputs=[
                IO.Array.Input(
                    id="shots",
                    tooltip="ARRAY of shot specs (connect multiple Art.Shot nodes).",
                ),
                IO.Combo.Input(
                    id="provider",
                    choices=["auto", "offline", "http_video"],
                    optional=True,
                    default="auto",
                    tooltip="Video backend (auto selects by capability).",
                ),
                IO.String.Input(
                    id="model",
                    optional=True,
                    tooltip="Optional model id (provider default when blank).",
                ),
                IO.Int.Input(
                    id="retry_count",
                    optional=True,
                    default=1,
                    min=0,
                    max=10,
                    tooltip="Retries per shot before failing.",
                ),
                IO.String.Input(
                    id="output",
                    optional=True,
                    tooltip="Optional state variable name to store the produced shot videos (ARRAY).",
                ),
            ],
            outputs=[
                IO.Array.Output(id="videos"),
                IO.Boolean.Output(id="success"),
            ],
            hidden=[Hidden.UNIQUE_ID, Hidden.WORKFLOW_STATE, Hidden.SESSION_ID, Hidden.USER_ID],
            not_idempotent=True,
        )

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        state = hidden.workflow_state
        raw_shots = inputs.get("shots")
        if not isinstance(raw_shots, list) or not raw_shots:
            return NodeOutput(error="Art.Storyboard: missing 'shots' (ARRAY)")

        provider = inputs.get("provider") or "auto"
        provider_arg = None if provider in ("auto", "", None) else str(provider)
        retry_count = int(inputs.get("retry_count") or 0)
        model = inputs.get("model")

        from leagent.llm.generation import get_generation_service

        svc = get_generation_service()
        out_refs: list[MediaRef] = []
        for idx, shot in enumerate(raw_shots):
            if not isinstance(shot, dict):
                return NodeOutput(error=f"Art.Storyboard: shot[{idx}] is not an object")
            prompt = str(shot.get("prompt") or "").strip()
            if not prompt:
                return NodeOutput(error=f"Art.Storyboard: shot[{idx}] missing prompt")
            params: dict[str, Any] = {}
            if model and isinstance(model, str) and model.strip():
                params["model"] = model.strip()
            params["duration"] = _as_int(shot.get("duration"), 3)
            params["fps"] = _as_int(shot.get("fps"), 24)
            if isinstance(shot.get("image"), dict):
                params["image"] = shot["image"]
            if isinstance(shot.get("camera"), dict):
                params["camera"] = shot["camera"]
            if isinstance(shot.get("controlnet"), dict):
                params["controlnet"] = shot["controlnet"]

            gen = await svc.generate(
                kind="video",
                prompt=prompt,
                provider=provider_arg,
                max_retries=retry_count,
                **params,
            )
            if not gen.success:
                return NodeOutput(error=gen.error or f"Art.Storyboard: shot[{idx}] generation failed")

            # Persist + MediaRef (reuse BaseGenerationNode approach).
            if gen.data is None and gen.meta.get("url"):
                ref = MediaRef(
                    kind="video",
                    preview_url=str(gen.meta["url"]),
                    mime=gen.mime,
                    filename=gen.filename,
                    meta={**(gen.meta or {}), "prompt": prompt, "provider": gen.provider, "model": gen.model},
                )
            else:
                from leagent.file.tool_output import register_tool_artifact

                attachment = await register_tool_artifact(
                    gen.data or b"",
                    filename=gen.filename or "video.mp4",
                    content_type=gen.mime or None,
                    session_id=hidden.session_id,
                    user_id=hidden.user_id,
                )
                ref = MediaRef.from_artifact(
                    attachment,
                    kind="video",
                    mime=gen.mime or "video/mp4",
                    meta={**(gen.meta or {}), "prompt": prompt, "provider": gen.provider, "model": gen.model},
                )
                if ref is None:
                    return NodeOutput(error=f"Art.Storyboard: shot[{idx}] failed to persist")

            out_refs.append(ref)

        videos = [r.to_dict() for r in out_refs]
        if state is not None and inputs.get("output"):
            state.set(str(inputs["output"]), videos)

        return NodeOutput(
            values=(videos, True),
            ui={"gen_ui": to_gen_ui_tree(out_refs, title=type(self).DISPLAY_TITLE)},
            metadata={"count": len(out_refs), "kind": "video"},
        )


STORYBOARD_NODES: list[type[WorkflowNode]] = [ShotNode, StoryboardNode]

__all__ = ["STORYBOARD_NODES", "ShotNode", "StoryboardNode"]

