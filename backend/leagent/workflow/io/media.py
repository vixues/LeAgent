"""``MediaRef`` — the value object travelling across typed media sockets.

A :class:`MediaRef` is a storage-agnostic, *by-reference* handle to a
generated game-art asset (image, video, 3D mesh). It carries the managed
file id plus a preview URL so downstream nodes and the GenUI rendering
layer can display the asset without ever moving base64 bytes through the
graph (the canonical convention is ``/api/v1/files/{id}/preview``).

The wire form is a plain ``dict`` (``to_dict()``) so it serializes into
node outputs / workflow state cleanly; :meth:`from_dict` rehydrates it.
:meth:`from_artifact` builds one straight from the attachment dict
returned by :func:`leagent.file.tool_output.register_tool_artifact`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

MediaKind = Literal["image", "video", "model3d", "audio"]

#: ``io_type`` of the typed socket each media kind flows through.
KIND_TO_IO_TYPE: dict[str, str] = {
    "image": "IMAGE",
    "video": "VIDEO",
    "model3d": "MESH3D",
    "audio": "AUDIO",
}

#: GenUI component ``kind`` used to render each media kind on the canvas /
#: in chat. ``model3d`` maps to the new GLB viewer component.
KIND_TO_GENUI: dict[str, str] = {
    "image": "Image",
    "video": "Video",
    "model3d": "Model3D",
    "audio": "Image",  # audio falls back to a card; no dedicated player yet
}


@dataclass
class MediaRef:
    """Reference to one managed media asset produced by a workflow node."""

    kind: MediaKind = "image"
    file_id: str | None = None
    preview_url: str | None = None
    download_url: str | None = None
    mime: str = ""
    filename: str = ""
    width: int | None = None
    height: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def src(self) -> str | None:
        """Best display URL for the asset."""
        if self.preview_url:
            return self.preview_url
        if self.file_id:
            return f"/api/v1/files/{self.file_id}/preview"
        return None

    @property
    def io_type(self) -> str:
        return KIND_TO_IO_TYPE.get(self.kind, "*")

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "kind": self.kind,
            "file_id": self.file_id,
            "preview_url": self.preview_url,
            "download_url": self.download_url,
            "mime": self.mime,
            "filename": self.filename,
            "src": self.src,
        }
        if self.width is not None:
            out["width"] = self.width
        if self.height is not None:
            out["height"] = self.height
        if self.meta:
            out["meta"] = dict(self.meta)
        return out

    @classmethod
    def from_dict(cls, raw: Any) -> "MediaRef | None":
        """Rehydrate a MediaRef from its wire dict (tolerant of partials)."""
        if isinstance(raw, MediaRef):
            return raw
        if not isinstance(raw, dict):
            return None
        kind = str(raw.get("kind") or "image")
        return cls(
            kind=kind if kind in KIND_TO_IO_TYPE else "image",  # type: ignore[arg-type]
            file_id=raw.get("file_id"),
            preview_url=raw.get("preview_url") or raw.get("src"),
            download_url=raw.get("download_url"),
            mime=str(raw.get("mime") or ""),
            filename=str(raw.get("filename") or ""),
            width=raw.get("width"),
            height=raw.get("height"),
            meta=dict(raw.get("meta") or {}),
        )

    @classmethod
    def from_artifact(
        cls,
        attachment: dict[str, Any] | None,
        *,
        kind: MediaKind,
        mime: str = "",
        meta: dict[str, Any] | None = None,
    ) -> "MediaRef | None":
        """Build a MediaRef from a ``register_tool_artifact`` attachment dict."""
        if not isinstance(attachment, dict):
            return None
        file_id = str(attachment.get("id") or "") or None
        preview = attachment.get("preview_url") or attachment.get("preview_path")
        if not preview and file_id:
            preview = f"/api/v1/files/{file_id}/preview"
        return cls(
            kind=kind,
            file_id=file_id,
            preview_url=preview,
            download_url=attachment.get("download_url"),
            mime=mime or str(attachment.get("content_type") or ""),
            filename=str(attachment.get("filename") or attachment.get("name") or ""),
            meta=dict(meta or {}),
        )

    def gen_ui_node(self, *, caption: str | None = None) -> dict[str, Any]:
        """Render this asset as a GenUI component node (image/video/3D)."""
        comp = KIND_TO_GENUI.get(self.kind, "Image")
        props: dict[str, Any] = {"src": self.src or ""}
        if caption:
            props["caption"] = caption
        if self.filename and not caption:
            props["alt"] = self.filename
        if comp == "Image":
            props.setdefault("rounded", True)
            props.setdefault("maxHeight", 320)
        return {"kind": comp, "props": props}


def to_gen_ui_tree(refs: list[MediaRef], *, title: str | None = None) -> dict[str, Any]:
    """Wrap one or more MediaRefs into a GenUI asset tree (schemaVersion 1)."""
    children = [r.gen_ui_node() for r in refs if r.src]
    root_children: list[dict[str, Any]] = []
    if title:
        root_children.append({"kind": "SectionHeader", "props": {"title": title}})
    if len(children) > 1:
        root_children.append({"kind": "Grid", "props": {"columns": 2}, "children": children})
    else:
        root_children.extend(children)
    return {"schemaVersion": "1", "root": {"kind": "Stack", "children": root_children}}


__all__ = [
    "KIND_TO_GENUI",
    "KIND_TO_IO_TYPE",
    "MediaKind",
    "MediaRef",
    "to_gen_ui_tree",
]
