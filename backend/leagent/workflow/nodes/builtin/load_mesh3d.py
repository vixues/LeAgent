"""Builtin node: load a 3D mesh into a typed MediaRef (ComfyUI-style LoadMesh)."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from leagent.file.tool_output import register_tool_artifact
from leagent.workflow.io import IO, Hidden, HiddenHolder, MediaRef, NodeOutput, Schema, to_gen_ui_tree
from leagent.workflow.nodes.base import WorkflowNode

_MESH_MIMES = frozenset(
    {
        "model/gltf-binary",
        "model/gltf+json",
        "application/octet-stream",
    }
)
_MESH_EXTS = frozenset({".glb", ".gltf", ".obj", ".fbx"})


def _guess_mesh_mime(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".glb":
        return "model/gltf-binary"
    if ext == ".gltf":
        return "model/gltf+json"
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "model/gltf-binary"


class LoadMesh3DNode(WorkflowNode):
    """Load a 3D mesh asset from a managed file id or a local path."""

    NODE_ID = "LoadMesh3D"

    @classmethod
    def get_schema(cls) -> Schema:
        return Schema(
            node_id=cls.NODE_ID,
            display_name="Load 3D mesh",
            category="builtin/media",
            description="Load a GLB/GLTF/OBJ mesh into a typed MESH3D socket (MediaRef).",
            inputs=[
                IO.File.Input(
                    id="file",
                    accept=".glb,.gltf,.obj,model/gltf-binary,model/gltf+json",
                    tooltip="Managed file id or a local path to a 3D mesh.",
                ),
            ],
            outputs=[
                IO.Mesh3D.Output(id="mesh"),
                IO.String.Output(id="preview_url"),
                IO.Boolean.Output(id="success"),
            ],
            hidden=[
                Hidden.SESSION_ID,
                Hidden.USER_ID,
            ],
        )

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        raw = inputs.get("file")
        value = str(raw or "").strip()
        if not value:
            return NodeOutput(values=(None, "", False), error="LoadMesh3D: missing 'file'")

        path = Path(value)
        if path.exists() and path.is_file():
            if path.suffix.lower() not in _MESH_EXTS:
                return NodeOutput(
                    values=(None, "", False),
                    error=f"LoadMesh3D: unsupported extension {path.suffix}",
                )
            data = path.read_bytes()
            mime = _guess_mesh_mime(path)
            attachment = await register_tool_artifact(
                data,
                filename=path.name,
                content_type=mime,
                session_id=hidden.session_id,
                user_id=hidden.user_id,
            )
            ref = MediaRef.from_artifact(attachment, kind="model3d", mime=mime)
            if ref is None:
                return NodeOutput(values=(None, "", False), error="LoadMesh3D: failed to register file")
        else:
            ref = MediaRef(kind="model3d", file_id=value)

        return NodeOutput(
            values=(ref.to_dict(), ref.src or "", True),
            ui={"gen_ui": to_gen_ui_tree([ref], title="Loaded mesh")},
            metadata={"kind": "model3d", "file_id": ref.file_id},
        )


__all__ = ["LoadMesh3DNode"]
