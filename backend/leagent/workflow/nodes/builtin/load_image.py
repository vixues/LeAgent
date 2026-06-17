"""Builtin node: load an image into a typed MediaRef (ComfyUI-style LoadImage).

This bridges the "FILE" widget input (file id or path) into the typed
``IO.Image`` socket used by the first-class art pipeline.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from leagent.file.tool_output import register_tool_artifact
from leagent.workflow.io import IO, Hidden, HiddenHolder, MediaRef, NodeOutput, Schema, to_gen_ui_tree
from leagent.workflow.nodes.base import WorkflowNode


async def _resolve_session_attachment(
    *,
    session_id: str | None,
    user_id: str | None,
    ref: str,
) -> dict[str, Any] | None:
    """Resolve a user-provided ref (id / filename / basename) against session attachments.

    ComfyUI's LoadImage works from an input directory picker. In LeAgent the
    closest equivalent is session attachments (already-uploaded files).
    """
    if not session_id:
        return None
    ref = (ref or "").strip()
    if not ref:
        return None

    try:
        from uuid import UUID

        sid = UUID(str(session_id))
    except Exception:  # noqa: BLE001
        return None

    try:
        from leagent.main import get_service_manager

        sm = get_service_manager()
        session_manager = getattr(sm, "session_manager", None)
        if session_manager is None:
            return None
        attachments = await session_manager.list_attachments(sid, user_id=user_id)
    except Exception:  # noqa: BLE001
        return None

    by_id: dict[str, Any] = {}
    by_name: dict[str, Any] = {}
    by_base: dict[str, Any] = {}
    for att in attachments or []:
        try:
            att_id = str(getattr(att, "id", "") or "")
            filename = str(getattr(att, "filename", "") or "")
            content_type = str(getattr(att, "content_type", "") or "")
        except Exception:  # noqa: BLE001
            continue
        if not att_id:
            continue
        if content_type and not content_type.lower().startswith("image/"):
            continue
        by_id[att_id] = att
        if filename:
            by_name[filename.casefold()] = att
            by_base[Path(filename).name.casefold()] = att

    hit = by_id.get(ref) or by_name.get(ref.casefold()) or by_base.get(Path(ref).name.casefold())
    if hit is None:
        return None
    return {
        "id": str(getattr(hit, "id", "") or ""),
        "filename": str(getattr(hit, "filename", "") or ""),
        "content_type": str(getattr(hit, "content_type", "") or ""),
        "preview_url": getattr(hit, "preview_url", None),
        "download_url": getattr(hit, "download_url", None),
    }


class LoadImageNode(WorkflowNode):
    """Load an image asset from a managed file id or a local path."""

    NODE_ID = "LoadImage"

    @classmethod
    def get_schema(cls) -> Schema:
        return Schema(
            node_id=cls.NODE_ID,
            display_name="Load image",
            category="builtin/media",
            description="Load an image into a typed IMAGE socket (MediaRef).",
            inputs=[
                IO.File.Input(
                    id="file",
                    accept="image/*",
                    tooltip="Managed file id or a local path to an image file.",
                ),
            ],
            outputs=[
                IO.Image.Output(id="image"),
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
            return NodeOutput(values=(None, "", False), error="LoadImage: missing 'file'")

        # 1) Prefer session attachment resolution (id / filename / basename).
        resolved = await _resolve_session_attachment(
            session_id=hidden.session_id,
            user_id=hidden.user_id,
            ref=value,
        )
        if isinstance(resolved, dict) and resolved.get("id"):
            ref = MediaRef(
                kind="image",
                file_id=str(resolved["id"]),
                preview_url=resolved.get("preview_url"),
                download_url=resolved.get("download_url"),
                mime=str(resolved.get("content_type") or ""),
                filename=str(resolved.get("filename") or ""),
            )
            return NodeOutput(
                values=(ref.to_dict(), ref.src or "", True),
                ui={"gen_ui": to_gen_ui_tree([ref], title="Loaded image")},
                metadata={"kind": "image", "file_id": ref.file_id, "source": "session_attachment"},
            )

        # When the value is an existing local path, register it as a managed artifact.
        path = Path(value)
        if path.exists() and path.is_file():
            data = path.read_bytes()
            guessed, _enc = mimetypes.guess_type(str(path))
            attachment = await register_tool_artifact(
                data,
                filename=path.name,
                content_type=guessed or None,
                session_id=hidden.session_id,
                user_id=hidden.user_id,
            )
            ref = MediaRef.from_artifact(attachment, kind="image", mime=guessed or "")
            if ref is None:
                return NodeOutput(values=(None, "", False), error="LoadImage: failed to register file")
        else:
            # Treat as managed file id (preferred in the UI): build a tolerant ref.
            ref = MediaRef(kind="image", file_id=value)

        return NodeOutput(
            values=(ref.to_dict(), ref.src or "", True),
            ui={"gen_ui": to_gen_ui_tree([ref], title="Loaded image")},
            metadata={"kind": "image", "file_id": ref.file_id},
        )


__all__ = ["LoadImageNode"]

