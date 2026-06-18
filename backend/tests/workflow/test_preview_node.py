"""Contract + behaviour tests for the ``Art.Preview`` artifact preview node.

The preview node is a professional, ComfyUI ``PreviewImage``-style node: it
accepts any media artifact by reference, renders a GenUI preview, exposes
structured metadata (filename / dims / mime / download), and passes the asset
through so it can sit between a generator and a downstream consumer.
"""

from __future__ import annotations

import pytest

from leagent.services.gen_ui.schema import validate_ui_tree
from leagent.workflow.io import HiddenHolder, MediaRef
from leagent.workflow.io.types import WILDCARD_TYPE
from leagent.workflow.nodes import bootstrap as bootstrap_nodes
from leagent.workflow.nodes import get_registry
from leagent.workflow.nodes.builtin.preview import PreviewNode


@pytest.fixture(scope="module")
async def registered_nodes():
    await bootstrap_nodes()
    return get_registry()


@pytest.mark.asyncio
async def test_preview_node_is_registered(registered_nodes):
    assert "Art.Preview" in registered_nodes.snapshot()


def test_preview_accepts_any_artifact_and_passes_through():
    info = PreviewNode.define_schema().get_info_dict()
    assert info["output_node"] is True
    # The asset socket is a wildcard so any media output (IMAGE / VIDEO /
    # MESH3D / AUDIO) snaps in without a canvas type-compat rejection. It is
    # optional so an unconnected preview node never blocks a run.
    asset_type, _opts = info["input"]["optional"]["asset"]
    assert asset_type == WILDCARD_TYPE
    # Passthrough output is wildcard so the asset keeps flowing downstream.
    assert info["output"][0] == WILDCARD_TYPE
    assert info["output_name"][0] == "asset"


@pytest.mark.asyncio
async def test_preview_emits_genui_and_rich_metadata():
    node = PreviewNode()
    ref = MediaRef(
        kind="image",
        file_id="img1",
        preview_url="/api/v1/files/img1/preview",
        filename="hero.png",
        width=1024,
        height=768,
        mime="image/png",
    )
    out = await node.execute(hidden=HiddenHolder(unique_id="n1"), asset=ref.to_dict())

    # Passthrough value is the same MediaRef dict.
    assert out.values[0]["file_id"] == "img1"
    assert out.values[1] == "/api/v1/files/img1/preview"

    md = out.metadata
    assert md["kind"] == "image"
    assert md["filename"] == "hero.png"
    assert md["width"] == 1024 and md["height"] == 768
    assert md["download_url"] == "/api/v1/files/img1/download"

    tree = out.ui["gen_ui"]
    validate_ui_tree(tree, max_depth=12, max_nodes=128)
    media = tree["root"]["children"][1]
    assert media["kind"] == "Image"
    assert media["props"]["src"] == "/api/v1/files/img1/preview"


@pytest.mark.asyncio
async def test_preview_preserves_audio_kind():
    node = PreviewNode()
    ref = MediaRef(
        kind="audio",
        file_id="aud1",
        preview_url="/api/v1/files/aud1/preview",
        filename="vo.wav",
        mime="audio/wav",
    )
    out = await node.execute(hidden=HiddenHolder(unique_id="n2"), asset=ref.to_dict())
    assert out.metadata["kind"] == "audio"


@pytest.mark.asyncio
async def test_preview_with_no_asset_is_benign_noop():
    node = PreviewNode()
    out = await node.execute(hidden=HiddenHolder(unique_id="n3"), asset=None)
    assert out.error is None
    assert out.values[0] is None
    assert out.metadata.get("empty") is True
