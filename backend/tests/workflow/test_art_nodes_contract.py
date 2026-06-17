"""Wire-contract tests for the first-class art-asset node pack.

These freeze the composability contract the canvas + GenUI layers rely on:

* the ``Art.*`` generation nodes register (ComfyUI ``NodeExtension`` style),
* they expose typed media sockets (IMAGE / VIDEO / MESH3D) so they snap
  together on the canvas, and
* a produced :class:`MediaRef` lowers to the matching GenUI component kind
  (``Image`` / ``Video`` / ``Model3D``) that the frontend registry renders.
"""

from __future__ import annotations

import pytest

from leagent.services.gen_ui.schema import list_component_catalog, validate_ui_tree
from leagent.workflow.io import MediaRef, to_gen_ui_tree
from leagent.workflow.io.media import KIND_TO_GENUI, KIND_TO_IO_TYPE
from leagent.workflow.io.types import SOCKET_COLORS
from leagent.workflow.nodes import bootstrap as bootstrap_nodes
from leagent.workflow.nodes import get_registry
from leagent.workflow.nodes.art.nodes import (
    ImageGenNode,
    Mesh3DNode,
    UpscaleNode,
    VideoGenNode,
)

ART_NODE_IDS = (
    "Art.ImageGen",
    "Art.VideoGen",
    "Art.Mesh3D",
    "Art.Upscale",
    "Art.CameraControl",
    "Art.PoseControl",
)


@pytest.fixture(scope="module")
async def registered_nodes():
    await bootstrap_nodes()
    return get_registry()


@pytest.mark.asyncio
async def test_art_nodes_are_registered(registered_nodes):
    snap = registered_nodes.snapshot()
    for node_id in ART_NODE_IDS:
        assert node_id in snap, f"{node_id} not registered (ArtNodeExtension missing?)"


def test_image_node_outputs_image_socket():
    info = ImageGenNode.get_schema().get_info_dict()
    assert "IMAGE" in info["output"]
    assert SOCKET_COLORS["IMAGE"] in info["output_colors"]


def test_video_node_outputs_video_socket():
    info = VideoGenNode.get_schema().get_info_dict()
    assert "VIDEO" in info["output"]
    assert SOCKET_COLORS["VIDEO"] in info["output_colors"]


def test_mesh_node_outputs_mesh3d_socket():
    info = Mesh3DNode.get_schema().get_info_dict()
    assert "MESH3D" in info["output"]
    assert SOCKET_COLORS["MESH3D"] in info["output_colors"]


def test_image_gen_accepts_optional_reference_image():
    info = ImageGenNode.get_schema().get_info_dict()
    optional = info["input"]["optional"]
    assert "image" in optional
    assert optional["image"][0] == "IMAGE"
    assert optional["image"][1]["color"] == SOCKET_COLORS["IMAGE"]


def test_mesh_and_video_accept_image_conditioning():
    # Image -> 3D / video composability: both take an optional IMAGE input.
    for node_cls in (Mesh3DNode, VideoGenNode, UpscaleNode):
        info = node_cls.get_schema().get_info_dict()
        bucket = info["input"]["optional"] if node_cls is not UpscaleNode else info["input"]["required"]
        assert "image" in bucket, node_cls.NODE_ID
        img_type, img_opts = bucket["image"]
        assert img_type == "IMAGE"
        assert img_opts["color"] == SOCKET_COLORS["IMAGE"]


@pytest.mark.parametrize(
    ("kind", "expected"),
    [("image", "Image"), ("video", "Video"), ("model3d", "Model3D")],
)
def test_media_kind_lowers_to_genui_component(kind: str, expected: str):
    assert KIND_TO_GENUI[kind] == expected
    ref = MediaRef(file_id="f1", preview_url="/api/v1/files/f1/preview", kind=kind)
    node = ref.gen_ui_node()
    assert node["kind"] == expected
    assert node["props"]["src"] == "/api/v1/files/f1/preview"


def test_to_gen_ui_tree_validates_against_schema():
    refs = [
        MediaRef(file_id="img", preview_url="/api/v1/files/img/preview", kind="image"),
        MediaRef(file_id="vid", preview_url="/api/v1/files/vid/preview", kind="video"),
        MediaRef(file_id="m", preview_url="/api/v1/files/m/preview", kind="model3d"),
    ]
    tree = to_gen_ui_tree(refs, title="Assets")
    # Must satisfy the GenUI tree JSON schema (depth/node budget generous).
    validate_ui_tree(tree, max_depth=12, max_nodes=128)


def test_genui_catalog_exposes_media_kinds():
    kinds = {entry["kind"] for entry in list_component_catalog()}
    assert {"Image", "Video", "Model3D"}.issubset(kinds)


def test_kind_to_io_type_mapping_is_consistent():
    assert KIND_TO_IO_TYPE["image"] == "IMAGE"
    assert KIND_TO_IO_TYPE["video"] == "VIDEO"
    assert KIND_TO_IO_TYPE["model3d"] == "MESH3D"


# -- capability-driven binding (Phase 2) ------------------------------------


def test_image_node_binds_to_multiple_interchangeable_providers():
    """A node is no longer hard-wired to one model: its provider combo is
    derived from every backend whose capability profile satisfies the node's
    contract, with ``auto`` first and ``offline`` last."""
    info = ImageGenNode.get_schema().get_info_dict()
    provider_type, _ = info["input"]["optional"]["provider"]
    # COMBO wire type becomes the choices list.
    assert provider_type[0] == "auto"
    assert provider_type[-1] == "offline"
    # Local diffusion + dedicated image providers are all bindable.
    assert {"local", "openai", "dashscope"}.issubset(set(provider_type))
    # More than one interchangeable real backend (decoupled from a single model).
    assert len([p for p in provider_type if p not in ("auto", "offline")]) >= 2


def test_nodes_expose_optional_model_input():
    for node_cls in (ImageGenNode, UpscaleNode, VideoGenNode, Mesh3DNode):
        info = node_cls.get_schema().get_info_dict()
        assert "model" in info["input"]["optional"], node_cls.NODE_ID


def test_node_capability_contract_matches_kind():
    from leagent.llm.capabilities import Modality, TaskType

    contract = ImageGenNode.capability_contract()
    assert contract.task == TaskType.IMAGE_GEN
    assert Modality.IMAGE in contract.outputs
    assert VideoGenNode.capability_contract().task == TaskType.VIDEO_GEN
    assert Mesh3DNode.capability_contract().task == TaskType.MESH_GEN
