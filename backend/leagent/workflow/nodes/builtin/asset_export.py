"""``AssetExportNode`` — collate generated assets into an engine manifest.

Terminal art-pipeline node. It gathers the typed media assets wired into
it (image / video / mesh), builds an engine-import *manifest* (path, mime,
kind, filename), writes it to state, and emits a GenUI asset gallery so
the final deliverables render together. Assets are already managed files
(registered upstream), so this node only references them — no re-write.
"""

from __future__ import annotations

from typing import Any

import structlog

from leagent.workflow.io import (
    IO,
    Hidden,
    HiddenHolder,
    MediaRef,
    NodeOutput,
    Schema,
    to_gen_ui_tree,
)

from leagent.workflow.nodes.base import WorkflowNode

logger = structlog.get_logger(__name__)


class AssetExportNode(WorkflowNode):
    NODE_ID = "AssetExportNode"

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="AssetExportNode",
            display_name="Asset Export",
            category="art/export",
            description=(
                "Collate generated image / video / 3D assets into an "
                "engine-ready manifest and render them as a gallery."
            ),
            inputs=[
                IO.Image.Input(id="image", optional=True, tooltip="Image asset to export."),
                IO.Video.Input(id="video", optional=True, tooltip="Video asset to export."),
                IO.Mesh3D.Input(id="mesh", optional=True, tooltip="3D mesh asset to export."),
                IO.String.Input(id="asset_name", optional=True, default="asset",
                                tooltip="Base name for the exported asset bundle."),
                IO.String.Input(id="output", optional=True,
                                tooltip="Optional state variable to store the manifest."),
            ],
            outputs=[
                IO.Object.Output(id="manifest"),
                IO.Array.Output(id="assets"),
            ],
            hidden=[Hidden.UNIQUE_ID, Hidden.WORKFLOW_STATE],
            is_output_node=True,
            not_idempotent=True,
        )

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        name = str(inputs.get("asset_name") or "asset")
        refs: list[MediaRef] = []
        for slot in ("image", "video", "mesh"):
            ref = MediaRef.from_dict(inputs.get(slot))
            if ref is not None and ref.src:
                refs.append(ref)

        assets = [self._manifest_entry(name, ref) for ref in refs]
        manifest = {
            "name": name,
            "asset_count": len(assets),
            "assets": assets,
        }

        state = hidden.workflow_state
        if state is not None and inputs.get("output"):
            state.set(str(inputs["output"]), manifest)
        if state is not None:
            state.set("asset_manifest", manifest)

        ui = None
        if refs:
            ui = {"gen_ui": to_gen_ui_tree(refs, title=f"Game asset: {name}")}

        logger.info("asset_export", node_id=hidden.unique_id, count=len(assets))
        return NodeOutput(
            values=(manifest, assets),
            ui=ui,
            metadata={"asset_count": len(assets)},
        )

    @staticmethod
    def _manifest_entry(name: str, ref: MediaRef) -> dict[str, Any]:
        ext = (ref.filename.rsplit(".", 1)[-1] if "." in ref.filename else "")
        return {
            "name": name,
            "kind": ref.kind,
            "file_id": ref.file_id,
            "mime": ref.mime,
            "filename": ref.filename,
            "url": ref.src,
            "engine": {
                "import_as": ref.kind,
                "format": ext or ref.mime.split("/")[-1],
            },
            "meta": ref.meta,
        }
