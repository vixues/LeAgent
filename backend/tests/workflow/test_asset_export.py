"""Phase 4 — engine-ready asset export bundles.

Freezes the bundle contract ``AssetExportNode`` now delivers: a real
downloadable ``.zip`` (manifest + assets + per-engine import sidecars +
3D format-conversion hints), not just a JSON manifest of references.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from leagent.workflow.io import HiddenHolder, MediaRef
from leagent.workflow.nodes.builtin.asset_export import AssetExportNode
from leagent.workflow.nodes.builtin.export_profiles import (
    EXPORT_ENGINES,
    build_export_bundle,
)


def _entries() -> list[dict]:
    return [
        {"name": "hero", "kind": "image", "filename": "hero.png",
         "mime": "image/png", "file_id": "img1", "url": "/api/v1/files/img1/preview", "meta": {}},
        {"name": "hero", "kind": "model3d", "filename": "hero.glb",
         "mime": "model/gltf-binary", "file_id": "m1", "url": "/api/v1/files/m1/preview", "meta": {}},
    ]


def _open(zip_bytes: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(zip_bytes), "r")


def test_bundle_is_a_valid_zip_with_manifest():
    zip_bytes, desc = build_export_bundle(
        name="hero", entries=_entries(), engine="generic",
        asset_bytes={"img1": b"\x89PNG-fake", "m1": b"glTF-fake"},
    )
    zf = _open(zip_bytes)
    names = zf.namelist()
    assert "manifest.json" in names
    assert "hero.png" in names and "hero.glb" in names
    manifest = json.loads(zf.read("manifest.json"))
    assert manifest["engine"] == "generic"
    assert manifest["asset_count"] == 2
    assert manifest["embedded_count"] == 2
    assert desc["embedded_count"] == 2


def test_unity_profile_writes_meta_sidecars():
    zip_bytes, _ = build_export_bundle(
        name="hero", entries=_entries(), engine="unity",
        asset_bytes={"img1": b"x", "m1": b"y"},
    )
    names = _open(zip_bytes).namelist()
    assert "Assets/hero.png" in names
    assert "Assets/hero.png.meta" in names
    assert "Assets/hero.glb.meta" in names


def test_unreal_profile_writes_import_json_under_content():
    zip_bytes, _ = build_export_bundle(
        name="hero", entries=_entries(), engine="unreal",
        asset_bytes={"img1": b"x"},
    )
    zf = _open(zip_bytes)
    names = zf.namelist()
    assert "Content/hero.png" in names
    assert "Content/hero.png.json" in names
    descriptor = json.loads(zf.read("Content/hero.png.json"))
    assert descriptor["AssetImportData"]["AssetType"] == "Texture2D"


def test_godot_profile_writes_import_ini():
    zip_bytes, _ = build_export_bundle(
        name="hero", entries=_entries(), engine="godot",
        asset_bytes={"m1": b"y"},
    )
    zf = _open(zip_bytes)
    assert "hero.glb.import" in zf.namelist()
    body = zf.read("hero.glb.import").decode("utf-8")
    assert "[remap]" in body
    assert 'importer="scene"' in body


def test_mesh_format_conversion_hint_for_unity():
    # glb -> fbx conversion is flagged for Unity/Unreal.
    _, desc = build_export_bundle(
        name="hero", entries=_entries(), engine="unity", asset_bytes={},
    )
    conv = desc["conversions"]
    assert any(c["from"] == "glb" and c["to"] == "fbx" for c in conv)


def test_by_reference_when_bytes_missing():
    zip_bytes, desc = build_export_bundle(
        name="hero", entries=_entries(), engine="generic", asset_bytes={},
    )
    zf = _open(zip_bytes)
    # No raw asset bytes embedded, but manifest still lists them by reference.
    assert "hero.png" not in zf.namelist()
    manifest = json.loads(zf.read("manifest.json"))
    assert manifest["embedded_count"] == 0
    assert all(a["embedded"] is False for a in manifest["assets"])
    assert desc["embedded_count"] == 0


def test_all_engines_produce_a_bundle():
    for engine in EXPORT_ENGINES:
        zip_bytes, _ = build_export_bundle(
            name="hero", entries=_entries(), engine=engine, asset_bytes={"img1": b"x"},
        )
        assert "manifest.json" in _open(zip_bytes).namelist()


@pytest.mark.asyncio
async def test_export_node_registers_downloadable_bundle():
    node = AssetExportNode()
    hidden = HiddenHolder(unique_id="export-1")
    image = MediaRef(file_id="img1", preview_url="/api/v1/files/img1/preview",
                     kind="image", filename="hero.png", mime="image/png")
    mesh = MediaRef(file_id="m1", preview_url="/api/v1/files/m1/preview",
                    kind="model3d", filename="hero.glb", mime="model/gltf-binary")

    out = await node.execute(
        hidden=hidden,
        image=image.to_dict(),
        mesh=mesh.to_dict(),
        engine="unity",
        asset_name="hero",
    )
    manifest, assets, bundle_url = out.values
    assert manifest["engine"] == "unity"
    assert manifest["asset_count"] == 2
    assert manifest["bundle"] is not None
    assert manifest["bundle"]["file_id"]
    assert bundle_url
    assert out.metadata["bundle_file_id"]
