"""Contract tests for art control nodes (camera + ControlNet pose)."""

from __future__ import annotations

import pytest

from leagent.workflow.io.types import SOCKET_COLORS
from leagent.workflow.nodes import bootstrap as bootstrap_nodes
from leagent.workflow.nodes import get_registry
from leagent.workflow.nodes.art.control_nodes import CameraControlNode, PoseControlNode
from leagent.workflow.nodes.art.nodes import ImageGenNode


@pytest.fixture(scope="module")
async def registered_nodes():
    await bootstrap_nodes()
    return get_registry()


@pytest.mark.asyncio
async def test_control_nodes_registered(registered_nodes):
    snap = registered_nodes.snapshot()
    assert "Art.CameraControl" in snap
    assert "Art.PoseControl" in snap
    assert "LoadMesh3D" in snap
    assert "Art.Shot" in snap
    assert "Art.Storyboard" in snap


def test_image_gen_accepts_image_camera_control_sockets():
    info = ImageGenNode.get_schema().get_info_dict()
    optional = info["input"]["optional"]
    assert "image" in optional
    assert optional["image"][0] == "IMAGE"
    assert "camera" in optional
    assert optional["camera"][0] == "OBJECT"
    assert "control" in optional
    assert optional["control"][0] == "OBJECT"


def test_camera_control_outputs():
    info = CameraControlNode.get_schema().get_info_dict()
    assert "OBJECT" in info["output"]
    assert "IMAGE" in info["output"]
    assert SOCKET_COLORS["OBJECT"] in info["output_colors"]


def test_pose_control_requires_pose_image():
    info = PoseControlNode.get_schema().get_info_dict()
    required = info["input"]["required"]
    assert "pose" in required
    assert required["pose"][0] == "IMAGE"


@pytest.mark.asyncio
async def test_pose_control_passthrough():
    node = PoseControlNode()
    pose = {
        "kind": "image",
        "file_id": "pose-1",
        "preview_url": "/api/v1/files/pose-1/preview",
    }
    out = await node.execute(
        hidden=type("H", (), {"session_id": None, "user_id": None})(),
        pose=pose,
        strength=0.75,
        mode="openpose",
    )
    assert out.error is None
    control, pose_map = out.values
    assert control["type"] == "controlnet"
    assert control["strength"] == 0.75
    assert control["image"]["file_id"] == "pose-1"
    assert pose_map["file_id"] == "pose-1"


@pytest.mark.asyncio
async def test_camera_control_builds_spec():
    node = CameraControlNode()
    out = await node.execute(
        hidden=type("H", (), {"session_id": None, "user_id": None})(),
        preset="front",
        horizontal_angle=0,
        vertical_angle=0,
        zoom=5,
        fov=60,
    )
    assert out.error is None
    camera, view_prompt, preview = out.values
    assert camera["preset"] == "front"
    assert camera["azimuth"] == 0.0
    assert camera["fov"] == 60.0
    assert view_prompt.startswith("<sks>")
    assert "front view" in view_prompt
    assert preview is not None
