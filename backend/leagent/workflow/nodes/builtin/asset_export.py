"""``AssetExportNode`` — package generated assets into an engine-ready bundle.

Terminal art-pipeline node. It gathers the typed media assets wired into
it (image / video / mesh / VFX), assembles a **real downloadable ``.zip``
bundle** laid out for the chosen engine (Unity / Unreal / Godot / generic)
with per-asset import-metadata sidecars and 3D format-conversion hints,
registers that archive as a single managed artifact via the file layer,
and emits a GenUI gallery + download card. The manifest (with the bundle
reference) is written to state for downstream/agent consumption.
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

from .export_profiles import EXPORT_ENGINES, build_export_bundle

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
                "Package generated image / video / 3D / VFX assets into an "
                "engine-ready, downloadable bundle (Unity / Unreal / Godot) "
                "with import metadata, and render them as a gallery."
            ),
            inputs=[
                IO.Image.Input(id="image", optional=True, tooltip="Image asset to export."),
                IO.Video.Input(id="video", optional=True, tooltip="Video asset to export."),
                IO.Mesh3D.Input(id="mesh", optional=True, tooltip="3D mesh asset to export."),
                IO.Combo.Input(
                    id="engine", optional=True, default="generic",
                    choices=list(EXPORT_ENGINES),
                    tooltip="Target game engine import profile.",
                ),
                IO.Boolean.Input(
                    id="embed_assets", optional=True, default=True,
                    tooltip="Embed raw asset bytes in the bundle (vs. by-reference).",
                ),
                IO.String.Input(id="asset_name", optional=True, default="asset",
                                tooltip="Base name for the exported asset bundle."),
                IO.String.Input(id="output", optional=True,
                                tooltip="Optional state variable to store the manifest."),
            ],
            outputs=[
                IO.Object.Output(id="manifest"),
                IO.Array.Output(id="assets"),
                IO.String.Output(id="bundle_url"),
            ],
            hidden=[Hidden.UNIQUE_ID, Hidden.WORKFLOW_STATE, Hidden.SESSION_ID, Hidden.USER_ID],
            is_output_node=True,
            not_idempotent=True,
        )

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        name = str(inputs.get("asset_name") or "asset")
        engine = str(inputs.get("engine") or "generic")
        embed = inputs.get("embed_assets")
        embed = True if embed is None else bool(embed)

        refs: list[MediaRef] = []
        for slot in ("image", "video", "mesh"):
            ref = MediaRef.from_dict(inputs.get(slot))
            if ref is not None and ref.src:
                refs.append(ref)

        assets = [self._manifest_entry(name, ref) for ref in refs]

        asset_bytes: dict[str, bytes] = {}
        if embed:
            asset_bytes = await self._collect_bytes(refs, hidden)

        zip_bytes, descriptor = build_export_bundle(
            name=name, entries=assets, engine=engine, asset_bytes=asset_bytes,
        )
        bundle = await self._register_bundle(zip_bytes, name, engine, hidden)

        manifest = {
            "name": name,
            "engine": engine,
            "asset_count": len(assets),
            "assets": assets,
            "bundle": bundle,
            "conversions": descriptor.get("conversions", []),
            "members": descriptor.get("members", []),
            "embedded_count": descriptor.get("embedded_count", 0),
        }

        state = hidden.workflow_state
        if state is not None and inputs.get("output"):
            state.set(str(inputs["output"]), manifest)
        if state is not None:
            state.set("asset_manifest", manifest)

        ui = None
        if refs:
            ui = {"gen_ui": to_gen_ui_tree(refs, title=f"Game asset: {name}")}

        bundle_url = (bundle or {}).get("url") or ""
        logger.info(
            "asset_export", node_id=hidden.unique_id, count=len(assets),
            engine=engine, embedded=descriptor.get("embedded_count", 0),
            bundle=bool(bundle),
        )
        return NodeOutput(
            values=(manifest, assets, bundle_url),
            ui=ui,
            metadata={
                "asset_count": len(assets),
                "engine": engine,
                "bundle_file_id": (bundle or {}).get("file_id"),
                "embedded_count": descriptor.get("embedded_count", 0),
            },
        )

    @staticmethod
    async def _collect_bytes(
        refs: list[MediaRef], hidden: HiddenHolder
    ) -> dict[str, bytes]:
        """Best-effort fetch of managed asset bytes by file id for embedding."""
        out: dict[str, bytes] = {}
        file_service = None
        try:
            from leagent.services.service_manager import get_service_manager

            sm = get_service_manager()
            file_service = getattr(sm, "file_service", None) if sm else None
        except Exception:  # noqa: BLE001 - no service context (CLI / tests)
            file_service = None
        if file_service is None:
            return out
        for ref in refs:
            if not ref.file_id:
                continue
            try:
                fref = await file_service.get(ref.file_id)
                if fref is None:
                    continue
                data, _mime = await file_service.download(fref)
                out[ref.file_id] = data
            except Exception:  # noqa: BLE001 - fall back to by-reference
                logger.debug("asset_export_fetch_failed", file_id=ref.file_id)
        return out

    @staticmethod
    async def _register_bundle(
        zip_bytes: bytes, name: str, engine: str, hidden: HiddenHolder
    ) -> dict[str, Any] | None:
        """Persist the bundle as a managed artifact; return its download info."""
        from leagent.file.tool_output import register_tool_artifact

        filename = f"{name}_{engine}_bundle.zip"
        attachment = await register_tool_artifact(
            zip_bytes,
            filename=filename,
            content_type="application/zip",
            session_id=getattr(hidden, "session_id", None),
            user_id=getattr(hidden, "user_id", None),
        )
        if not attachment:
            return None
        file_id = str(attachment.get("id") or "")
        url = (
            attachment.get("download_url")
            or attachment.get("preview_url")
            or (f"/api/v1/files/{file_id}/download" if file_id else "")
        )
        return {
            "file_id": file_id,
            "filename": filename,
            "url": url,
            "size": attachment.get("size"),
            "mime": "application/zip",
        }

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
