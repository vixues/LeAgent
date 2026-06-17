"""Art pipeline control nodes — camera rig + ControlNet-style pose conditioning.

These are composable preprocessor nodes (ComfyUI-style) that output typed
``OBJECT`` sockets consumed by :class:`~leagent.workflow.nodes.art.nodes.ImageGenNode`,
:class:`~leagent.workflow.nodes.art.nodes.Mesh3DNode`, and
:class:`~leagent.workflow.nodes.art.nodes.VideoGenNode`.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar

from leagent.llm.generation.placeholders import color_from_prompt, solid_png
from leagent.workflow.io import IO, Hidden, HiddenHolder, MediaRef, NodeOutput, Schema, to_gen_ui_tree
from leagent.workflow.nodes.base import WorkflowNode

_CAMERA_PRESETS: dict[str, tuple[float, float]] = {
    "front": (0.0, 0.0),
    "side": (90.0, 0.0),
    "back": (180.0, 0.0),
    "three_quarter": (45.0, 15.0),
    "top": (0.0, 90.0),
    "bottom": (0.0, -90.0),
    "isometric": (45.0, 35.0),
}


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _build_camera_spec(inputs: dict[str, Any]) -> dict[str, Any]:
    preset = str(inputs.get("preset") or "custom").strip().lower()
    if preset in _CAMERA_PRESETS and preset != "custom":
        azimuth, elevation = _CAMERA_PRESETS[preset]
    else:
        azimuth = _float(inputs.get("horizontal_angle") or inputs.get("azimuth"), 45.0)
        elevation = _float(inputs.get("vertical_angle") or inputs.get("elevation"), 0.0)
        elevation = max(-30.0, min(60.0, elevation))

    roll = _float(inputs.get("roll"), 0.0)
    zoom = _float(inputs.get("zoom"), 5.0)
    zoom = max(0.0, min(10.0, zoom))
    distance = _float(inputs.get("distance"), 1.5 + (zoom / 10.0) * 6.5)
    fov = _float(inputs.get("fov"), 50.0)
    target = [
        _float(inputs.get("target_x"), 0.0),
        _float(inputs.get("target_y"), 0.0),
        _float(inputs.get("target_z"), 0.0),
    ]

    az_rad = math.radians(azimuth)
    el_rad = math.radians(elevation)
    eye = [
        target[0] + distance * math.cos(el_rad) * math.sin(az_rad),
        target[1] + distance * math.sin(el_rad),
        target[2] + distance * math.cos(el_rad) * math.cos(az_rad),
    ]

    return {
        "preset": preset,
        "azimuth": azimuth,
        "elevation": elevation,
        "horizontal_angle": azimuth,
        "vertical_angle": elevation,
        "zoom": zoom,
        "roll": roll,
        "distance": distance,
        "fov": fov,
        "target": target,
        "eye": eye,
        "up": [0.0, 1.0, 0.0],
        "camera_view": bool(inputs.get("camera_view")),
    }


def _nearest_azimuth_label(degrees: float) -> str:
    presets = [
        (0, "front view"),
        (45, "front-right quarter view"),
        (90, "right side view"),
        (135, "back-right quarter view"),
        (180, "back view"),
        (225, "back-left quarter view"),
        (270, "left side view"),
        (315, "front-left quarter view"),
    ]
    d = degrees % 360.0
    best = presets[0][1]
    best_diff = 360.0
    for deg, label in presets:
        diff = min(abs(d - deg), 360.0 - abs(d - deg))
        if diff < best_diff:
            best_diff = diff
            best = label
    return best


def _nearest_elevation_label(degrees: float) -> str:
    clamped = max(-30.0, min(60.0, degrees))
    presets = [(-30, "low-angle shot"), (0, "eye-level shot"), (30, "elevated shot"), (60, "high-angle shot")]
    best = presets[1][1]
    best_diff = 90.0
    for deg, label in presets:
        diff = abs(clamped - deg)
        if diff < best_diff:
            best_diff = diff
            best = label
    return best


def _zoom_to_distance_label(zoom: float) -> str:
    z = max(0.0, min(10.0, zoom))
    if z < 3.5:
        return "wide shot"
    if z < 7.0:
        return "medium shot"
    return "close-up"


def _qwen_view_prompt(spec: dict[str, Any]) -> str:
    """Qwen-Image-Edit multi-angle LoRA prompt (ComfyUI-qwenmultiangle)."""
    az = float(spec.get("horizontal_angle") or spec.get("azimuth") or 0)
    el = float(spec.get("vertical_angle") or spec.get("elevation") or 0)
    zoom = float(spec.get("zoom") or 5.0)
    return (
        f"<sks> {_nearest_azimuth_label(az)} "
        f"{_nearest_elevation_label(el)} "
        f"{_zoom_to_distance_label(zoom)}"
    )


def _camera_view_prompt(spec: dict[str, Any]) -> str:
    style = str(spec.get("prompt_style") or "qwen").strip().lower()
    if style == "qwen":
        return _qwen_view_prompt(spec)
    preset = spec.get("preset")
    if preset and preset != "custom":
        return f"camera preset {preset}, fov {spec['fov']:.0f}°"
    return (
        f"camera azimuth {spec['azimuth']:.0f}°, elevation {spec['elevation']:.0f}°, "
        f"roll {spec['roll']:.0f}°, distance {spec['distance']:.1f}, fov {spec['fov']:.0f}°"
    )


class CameraControlNode(WorkflowNode):
    """Professional 3D camera rig — sets the desired generation viewpoint."""

    NODE_ID = "Art.CameraControl"
    DISPLAY_TITLE: ClassVar[str] = "Camera view"

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id=cls.NODE_ID,
            display_name="3D Camera Control",
            category="art/control",
            description=(
                "Define the desired render / generation camera (azimuth, elevation, FOV). "
                "Connect the ``camera`` output to ImageGen, Mesh3D, or VideoGen nodes."
            ),
            inputs=[
                IO.Mesh3D.Input(
                    id="mesh",
                    optional=True,
                    tooltip="Optional reference mesh — preview uses its file id when set.",
                ),
                IO.Image.Input(
                    id="image",
                    optional=True,
                    tooltip="Optional reference image for framing.",
                ),
                IO.Combo.Input(
                    id="preset",
                    optional=True,
                    default="three_quarter",
                    choices=[
                        "custom",
                        "front",
                        "side",
                        "back",
                        "three_quarter",
                        "top",
                        "bottom",
                        "isometric",
                    ],
                    tooltip="Quick viewpoint presets (overrides azimuth/elevation unless custom).",
                ),
                IO.Float.Input(
                    id="horizontal_angle",
                    optional=True,
                    default=45.0,
                    min=0.0,
                    max=360.0,
                    step=1.0,
                    display="slider",
                    tooltip="Horizontal orbit angle (0–360°), Qwen multi-angle compatible.",
                ),
                IO.Float.Input(
                    id="vertical_angle",
                    optional=True,
                    default=0.0,
                    min=-30.0,
                    max=60.0,
                    step=1.0,
                    display="slider",
                    tooltip="Vertical tilt (-30° low-angle … 60° high-angle).",
                ),
                IO.Float.Input(
                    id="zoom",
                    optional=True,
                    default=5.0,
                    min=0.0,
                    max=10.0,
                    step=0.1,
                    display="slider",
                    tooltip="Camera distance / zoom (0 wide … 10 close-up).",
                ),
                IO.Boolean.Input(
                    id="camera_view",
                    optional=True,
                    default=False,
                    tooltip="Preview from the camera indicator perspective.",
                ),
                IO.Float.Input(
                    id="azimuth",
                    optional=True,
                    default=45.0,
                    min=0.0,
                    max=360.0,
                    step=1.0,
                    display="slider",
                    tooltip="Horizontal orbit angle in degrees (0 = front).",
                ),
                IO.Float.Input(
                    id="elevation",
                    optional=True,
                    default=0.0,
                    min=-30.0,
                    max=60.0,
                    step=1.0,
                    display="slider",
                    tooltip="Vertical tilt in degrees (0 = horizon, 90 = top-down).",
                ),
                IO.Float.Input(
                    id="roll",
                    optional=True,
                    default=0.0,
                    min=-180.0,
                    max=180.0,
                    step=1.0,
                    display="slider",
                    tooltip="Camera roll in degrees.",
                ),
                IO.Float.Input(
                    id="distance",
                    optional=True,
                    default=2.5,
                    min=0.1,
                    max=20.0,
                    step=0.1,
                    display="slider",
                    tooltip="Camera distance from the look-at target.",
                ),
                IO.Float.Input(
                    id="fov",
                    optional=True,
                    default=50.0,
                    min=15.0,
                    max=120.0,
                    step=1.0,
                    display="slider",
                    tooltip="Vertical field of view in degrees.",
                ),
                IO.Float.Input(id="target_x", optional=True, default=0.0, step=0.1, tooltip="Look-at X."),
                IO.Float.Input(id="target_y", optional=True, default=0.0, step=0.1, tooltip="Look-at Y."),
                IO.Float.Input(id="target_z", optional=True, default=0.0, step=0.1, tooltip="Look-at Z."),
            ],
            outputs=[
                IO.Object.Output(id="camera", tooltip="Camera rig consumed by generation nodes."),
                IO.String.Output(id="view_prompt", tooltip="Natural-language view hint for prompts."),
                IO.Image.Output(id="preview", tooltip="Offline preview frame tinted by viewpoint."),
            ],
            hidden=[
                Hidden.UNIQUE_ID,
                Hidden.SESSION_ID,
                Hidden.USER_ID,
            ],
        )

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        spec = _build_camera_spec(inputs)
        view_prompt = _camera_view_prompt(spec)

        mesh_ref = MediaRef.from_dict(inputs.get("mesh"))
        image_ref = MediaRef.from_dict(inputs.get("image"))
        if mesh_ref is not None:
            spec["reference_mesh"] = mesh_ref.to_dict()
        if image_ref is not None:
            spec["reference_image"] = image_ref.to_dict()

        seed = f"cam-{spec['azimuth']:.0f}-{spec['elevation']:.0f}-{spec['fov']:.0f}"
        rgb = color_from_prompt(seed)
        preview_bytes = solid_png(256, 256, rgb)
        from leagent.file.tool_output import register_tool_artifact

        attachment = await register_tool_artifact(
            preview_bytes,
            filename="camera_preview.png",
            content_type="image/png",
            session_id=hidden.session_id,
            user_id=hidden.user_id,
        )
        preview_ref = MediaRef.from_artifact(attachment, kind="image", mime="image/png", meta={"camera": spec})
        preview_dict = preview_ref.to_dict() if preview_ref else None

        ui_items = [preview_ref] if preview_ref else []
        return NodeOutput(
            values=(spec, view_prompt, preview_dict),
            ui={"gen_ui": to_gen_ui_tree(ui_items, title=type(self).DISPLAY_TITLE)} if ui_items else None,
            metadata={"camera": spec},
        )


class PoseControlNode(WorkflowNode):
    """ControlNet-style pose / structure conditioning for image generation."""

    NODE_ID = "Art.PoseControl"
    DISPLAY_TITLE: ClassVar[str] = "Pose control"

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id=cls.NODE_ID,
            display_name="ControlNet Pose",
            category="art/control",
            description=(
                "Apply OpenPose-style structural control to image generation. "
                "Connect a skeleton / pose map image and wire ``control`` into Art.ImageGen."
            ),
            inputs=[
                IO.Image.Input(
                    id="pose",
                    tooltip="OpenPose / skeleton control map (connect a loaded image or canvas asset).",
                ),
                IO.Float.Input(
                    id="strength",
                    optional=True,
                    default=0.8,
                    min=0.0,
                    max=1.0,
                    step=0.05,
                    display="slider",
                    tooltip="ControlNet conditioning strength (0 = off, 1 = full).",
                ),
                IO.Combo.Input(
                    id="mode",
                    optional=True,
                    default="openpose",
                    choices=["openpose", "dwpose", "canny", "depth", "normal"],
                    tooltip="Control preprocessor / model family.",
                ),
                IO.Int.Input(
                    id="start_percent",
                    optional=True,
                    default=0,
                    min=0,
                    max=100,
                    tooltip="Apply control from this diffusion step (%).",
                ),
                IO.Int.Input(
                    id="end_percent",
                    optional=True,
                    default=100,
                    min=0,
                    max=100,
                    tooltip="Apply control until this diffusion step (%).",
                ),
            ],
            outputs=[
                IO.Object.Output(id="control", tooltip="ControlNet bundle for Art.ImageGen."),
                IO.Image.Output(id="pose_map", tooltip="Normalized pose map passed through."),
            ],
            hidden=[
                Hidden.UNIQUE_ID,
                Hidden.SESSION_ID,
                Hidden.USER_ID,
            ],
        )

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        pose_ref = MediaRef.from_dict(inputs.get("pose"))
        if pose_ref is None:
            return NodeOutput(error="Art.PoseControl: missing 'pose' image input")

        strength = _float(inputs.get("strength"), 0.8)
        mode = str(inputs.get("mode") or "openpose").strip().lower()
        start_percent = int(inputs.get("start_percent") or 0)
        end_percent = int(inputs.get("end_percent") or 100)

        control = {
            "type": "controlnet",
            "mode": mode,
            "strength": max(0.0, min(strength, 1.0)),
            "start_percent": max(0, min(start_percent, 100)),
            "end_percent": max(0, min(end_percent, 100)),
            "image": pose_ref.to_dict(),
        }
        pose_map = pose_ref.to_dict()

        return NodeOutput(
            values=(control, pose_map),
            ui={"gen_ui": to_gen_ui_tree([pose_ref], title=type(self).DISPLAY_TITLE)},
            metadata={"controlnet": control},
        )


ART_CONTROL_NODES: list[type[WorkflowNode]] = [
    CameraControlNode,
    PoseControlNode,
]

__all__ = [
    "ART_CONTROL_NODES",
    "CameraControlNode",
    "PoseControlNode",
]
