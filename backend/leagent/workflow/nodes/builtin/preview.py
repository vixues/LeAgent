"""``PreviewNode`` — a professional artifact preview node (ComfyUI ``PreviewImage`` analogue).

A terminal-but-composable node that accepts any generated media artifact
(image / video / 3D mesh / audio) by reference and renders a rich preview on
the canvas: the asset itself plus filename, kind, dimensions, MIME, file size,
and a download link. It passes the asset straight through on an output socket
so it can be dropped *between* a generator/processor and a downstream consumer
(e.g. ``AssetExportNode``) without breaking the chain.

Assets travel by reference (``MediaRef``) — never inline base64 — so previewing
is free: the node only re-emits the existing ``/api/v1/files/{id}/preview`` URL
inside a ``NodeOutput.ui.gen_ui`` tree and exposes structured metadata that the
frontend renders as a professional artifact card.
"""

from __future__ import annotations

from typing import Any

from leagent.utils.logging import get_logger
from leagent.workflow.io import (
    IO,
    Hidden,
    HiddenHolder,
    MediaRef,
    NodeOutput,
    Schema,
)
from leagent.workflow.io.media import KIND_TO_GENUI
from leagent.workflow.nodes.base import WorkflowNode

logger = get_logger(__name__)


class PreviewNode(WorkflowNode):
    """Preview a generated media artifact (image / video / 3D / audio)."""

    NODE_ID = "Art.Preview"

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id=cls.NODE_ID,
            display_name="Artifact Preview",
            category="art/preview",
            description=(
                "Preview a generated media artifact (image, video, 3D mesh, or "
                "audio) with its filename, dimensions, type, and a download "
                "link. Passes the asset through so it can sit between a "
                "generator and a downstream consumer."
            ),
            inputs=[
                # Wildcard socket so *any* artifact output (IMAGE / VIDEO /
                # MESH3D / AUDIO — or anything else) snaps in without a
                # type-compat rejection on the canvas.
                IO.Any.Input(
                    id="asset",
                    optional=True,
                    tooltip="Generated media artifact to preview (image / video / 3D / audio).",
                ),
                IO.String.Input(
                    id="title",
                    optional=True,
                    tooltip="Optional caption shown above the preview.",
                ),
            ],
            outputs=[
                # Wildcard passthrough so the previewed asset keeps flowing to
                # any downstream consumer (export, conditioning, …).
                IO.Any.Output(id="asset"),
                IO.String.Output(id="preview_url"),
            ],
            hidden=[Hidden.UNIQUE_ID],
            is_output_node=True,
        )

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        ref = MediaRef.from_dict(inputs.get("asset"))
        if ref is None or not ref.src:
            # Nothing wired in yet — a benign no-op rather than a hard failure.
            return NodeOutput(
                values=(None, ""),
                metadata={"empty": True},
            )

        title = str(inputs.get("title") or "").strip() or self._default_title(ref)
        caption = self._caption(ref)
        download_url = ref.download_url or (
            f"/api/v1/files/{ref.file_id}/download" if ref.file_id else ref.src
        )
        size = ref.meta.get("size") or ref.meta.get("file_size_bytes")

        gen_ui = {
            "schemaVersion": "1",
            "root": {
                "kind": "Stack",
                "children": [
                    {"kind": "SectionHeader", "props": {"title": title}},
                    ref.gen_ui_node(caption=caption),
                ],
            },
        }

        logger.info(
            "artifact_preview",
            node_id=hidden.unique_id,
            kind=ref.kind,
            file_id=ref.file_id,
        )
        return NodeOutput(
            values=(ref.to_dict(), ref.src or ""),
            ui={"gen_ui": gen_ui},
            metadata={
                "kind": ref.kind,
                "genui_kind": KIND_TO_GENUI.get(ref.kind, "Image"),
                "filename": ref.filename,
                "mime": ref.mime,
                "width": ref.width,
                "height": ref.height,
                "src": ref.src,
                "preview_url": ref.src,
                "download_url": download_url,
                "file_id": ref.file_id,
                "file_size": size,
                "placeholder": bool(ref.meta.get("placeholder")),
            },
        )

    @staticmethod
    def _default_title(ref: MediaRef) -> str:
        labels = {
            "image": "Image",
            "video": "Video",
            "model3d": "3D model",
            "audio": "Audio",
            "vfx": "VFX sheet",
        }
        return labels.get(ref.kind, "Artifact")

    @staticmethod
    def _caption(ref: MediaRef) -> str:
        parts: list[str] = []
        if ref.filename:
            parts.append(ref.filename)
        if ref.width and ref.height:
            parts.append(f"{ref.width}\u00d7{ref.height}")
        if ref.mime:
            parts.append(ref.mime)
        return " \u00b7 ".join(parts)


__all__ = ["PreviewNode"]
