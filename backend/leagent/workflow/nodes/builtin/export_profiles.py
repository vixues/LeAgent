"""Engine export profiles — turn art assets into engine-ready bundles.

Each profile knows how a target engine wants assets laid out on disk and
which sidecar *import metadata* it expects so a dropped folder imports
cleanly:

* **Unity** — assets under ``Assets/``; each file gets a ``.meta`` sidecar
  with a deterministic GUID + importer block.
* **Unreal** — assets under ``Content/``; each file gets a ``.json`` import
  settings descriptor.
* **Godot** — assets at the project root; each file gets a ``.import`` ini.
* **generic** — flat layout, manifest only.

:func:`build_export_bundle` assembles a real ``.zip`` (manifest + assets +
sidecars) entirely in memory so the caller can register it as a single
downloadable managed artifact.
"""

from __future__ import annotations

import hashlib
import io
import json
import posixpath
import zipfile
from dataclasses import dataclass
from typing import Any

EXPORT_ENGINES = ("generic", "unity", "unreal", "godot")

#: 3D formats an engine prefers; used to annotate conversion hints.
_ENGINE_MESH_FORMAT = {
    "unity": "fbx",
    "unreal": "fbx",
    "godot": "glb",
    "generic": "glb",
}


@dataclass
class _Entry:
    name: str
    kind: str
    filename: str
    mime: str
    file_id: str
    url: str
    meta: dict[str, Any]


def _stable_guid(seed: str) -> str:
    """Deterministic 32-hex GUID (Unity uses 32 hex chars)."""
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:32]


def _asset_dir(engine: str) -> str:
    if engine == "unity":
        return "Assets"
    if engine == "unreal":
        return "Content"
    return ""


def _ext_of(entry: _Entry) -> str:
    if "." in entry.filename:
        return entry.filename.rsplit(".", 1)[-1].lower()
    return (entry.mime.split("/")[-1] or "bin").lower()


def _unity_meta(entry: _Entry, asset_path: str) -> bytes:
    guid = _stable_guid(f"{entry.file_id}:{asset_path}")
    if entry.kind in ("image", "vfx"):
        importer = "TextureImporter:\n  externalObjects: {}\n  serializedVersion: 12\n"
    elif entry.kind == "model3d":
        importer = "ModelImporter:\n  serializedVersion: 22200\n  internalIDToNameTable: []\n"
    elif entry.kind == "video":
        importer = "VideoClipImporter:\n  externalObjects: {}\n"
    else:
        importer = "DefaultImporter:\n  externalObjects: {}\n"
    return (
        f"fileFormatVersion: 2\nguid: {guid}\n{importer}"
        f"  userData: 'leagent:{entry.kind}'\n  assetBundleName: ''\n"
    ).encode("utf-8")


def _unreal_import(entry: _Entry) -> bytes:
    payload = {
        "AssetImportData": {
            "SourceFile": entry.filename,
            "AssetType": {
                "image": "Texture2D",
                "vfx": "Texture2D",
                "model3d": "StaticMesh",
                "video": "MediaSource",
            }.get(entry.kind, "Object"),
        },
        "FactoryName": "leagent",
        "Metadata": entry.meta,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")


def _godot_import(entry: _Entry, asset_path: str) -> bytes:
    importer = {
        "image": "texture",
        "vfx": "texture",
        "model3d": "scene",
        "video": "video_stream",
    }.get(entry.kind, "file")
    lines = [
        "[remap]",
        "",
        f'importer="{importer}"',
        f'type="{entry.kind}"',
        f'path="res://{asset_path}"',
        "",
        "[deps]",
        "",
        f'source_file="res://{asset_path}"',
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def build_export_bundle(
    *,
    name: str,
    entries: list[dict[str, Any]],
    engine: str,
    asset_bytes: dict[str, bytes] | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """Build a ``.zip`` bundle + its descriptor for the chosen *engine*.

    Args:
        name: Base name for the bundle.
        entries: Manifest entries (``kind``/``filename``/``mime``/``file_id``…).
        engine: One of :data:`EXPORT_ENGINES`.
        asset_bytes: Optional ``file_id -> raw bytes`` map. Assets whose bytes
            are available are written into the archive; the rest are recorded
            by reference (url + file_id) in the manifest.

    Returns:
        ``(zip_bytes, bundle_descriptor)`` where the descriptor lists the
        archive members and any 3D format-conversion hints.
    """
    engine = engine if engine in EXPORT_ENGINES else "generic"
    asset_bytes = asset_bytes or {}
    parsed = [
        _Entry(
            name=str(e.get("name") or name),
            kind=str(e.get("kind") or "image"),
            filename=str(e.get("filename") or f"{name}.bin"),
            mime=str(e.get("mime") or ""),
            file_id=str(e.get("file_id") or ""),
            url=str(e.get("url") or ""),
            meta=dict(e.get("meta") or {}),
        )
        for e in entries
    ]

    members: list[str] = []
    conversions: list[dict[str, str]] = []
    asset_dir = _asset_dir(engine)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest_entries: list[dict[str, Any]] = []
        for idx, entry in enumerate(parsed):
            ext = _ext_of(entry)
            base = entry.filename if entry.filename else f"{entry.name}_{idx}.{ext}"
            asset_path = posixpath.join(asset_dir, base) if asset_dir else base

            embedded = entry.file_id in asset_bytes
            if embedded:
                zf.writestr(asset_path, asset_bytes[entry.file_id])
                members.append(asset_path)

            # Format-conversion hint for meshes the engine prefers in another format.
            if entry.kind == "model3d":
                target = _ENGINE_MESH_FORMAT.get(engine, "glb")
                if target != ext:
                    conversions.append({"asset": asset_path, "from": ext, "to": target})

            # Per-engine import sidecar.
            sidecar_path = ""
            if engine == "unity":
                sidecar_path = asset_path + ".meta"
                zf.writestr(sidecar_path, _unity_meta(entry, asset_path))
            elif engine == "unreal":
                sidecar_path = asset_path + ".json"
                zf.writestr(sidecar_path, _unreal_import(entry))
            elif engine == "godot":
                sidecar_path = asset_path + ".import"
                zf.writestr(sidecar_path, _godot_import(entry, asset_path))
            if sidecar_path:
                members.append(sidecar_path)

            manifest_entries.append({
                "name": entry.name,
                "kind": entry.kind,
                "file_id": entry.file_id,
                "mime": entry.mime,
                "path": asset_path,
                "embedded": embedded,
                "url": entry.url,
                "import_metadata": sidecar_path or None,
            })

        manifest = {
            "name": name,
            "engine": engine,
            "asset_count": len(parsed),
            "embedded_count": sum(1 for e in manifest_entries if e["embedded"]),
            "assets": manifest_entries,
            "conversions": conversions,
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        members.append("manifest.json")

    descriptor = {
        "engine": engine,
        "members": members,
        "conversions": conversions,
        "asset_count": len(parsed),
        "embedded_count": manifest["embedded_count"],
    }
    return buf.getvalue(), descriptor


__all__ = ["EXPORT_ENGINES", "build_export_bundle"]
