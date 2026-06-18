"""Game-art playbook — the prompt layer + decomposition planner that teaches
the agent how to turn a creative brief into a runnable art DAG.

Lives in the prompt layer (``leagent/prompts``) rather than the agent core:
it is pure prompt content + a deterministic planning helper with no agent /
runtime dependencies (the node registry is read lazily, by reference). The
``art_playbook`` context source consumes it.

Pieces, all offline / dependency-free:

* :data:`ART_ONTOLOGY` — the canonical concept → sheet → mesh → rig → VFX →
  export pipeline shape the agent should reason in.
* :func:`build_art_node_catalog` — a *graph-aware* catalog introspected from
  the live node registry (node id + typed input/output sockets) so the agent
  wires real, currently-registered nodes rather than hallucinated ones.
* :func:`render_art_playbook` — assembles ontology + node catalog +
  ``TPL-ART-01`` pattern + the required tool sequence into one system-prompt
  block.
* :func:`plan_art_tasks` — a lightweight, keyword-driven decomposition that
  turns a brief into an ordered ``todo_write``-shaped step list.

The playbook is surfaced to the model via the ``art_playbook`` context source
(:mod:`leagent.context.sources.art_playbook`), gated so it only appears for
art-flavoured requests.
"""

from __future__ import annotations

import re
from typing import Any

__all__ = [
    "ART_ONTOLOGY",
    "ART_TOOL_SEQUENCE",
    "ART_REQUEST_HINTS",
    "build_art_node_catalog",
    "looks_like_art_request",
    "plan_art_tasks",
    "render_art_playbook",
]

ART_ONTOLOGY = (
    "Game-art production ontology (decompose every brief along this spine):\n"
    "1. concept    — text→image key art / mood (Art.ImageGen).\n"
    "2. sheet      — turnaround / multi-angle reference (Art.CameraControl + Art.ImageGen).\n"
    "3. evaluate   — score the asset (Art.QualityCritic → QualityGateNode).\n"
    "4. self-heal  — on a below-bar score, IterativeRefineNode feeds critique\n"
    "               back into the prompt and regenerates (bounded loop).\n"
    "5. upscale    — super-resolve the approved image (Art.Upscale).\n"
    "6. mesh        — image→3D model, engine format (Art.Mesh3D).\n"
    "7. motion/vfx — turntable/idle clip (Art.VideoGen) or flipbook (Art.VFXGen).\n"
    "8. export     — engine-ready bundle with import metadata (AssetExportNode)."
)

ART_TOOL_SEQUENCE = (
    "Required tool sequence for authoring + running an art pipeline:\n"
    "  1. todo_write        — record the decomposed plan as visible steps.\n"
    "  2. chat_workflow_embed_emit — stream the DAG onto the canvas as you build it.\n"
    "  3. workflow_save     — validate + persist the graph (returns flow_id + digest).\n"
    "  4. workflow_run      — execute; below-bar quality returns success=False.\n"
    "  5. workflow_status   — poll until COMPLETED.\n"
    "If workflow_run reports below-bar quality, revise the graph/prompts and\n"
    "re-run within the same turn (the quality gate + refine loop are bounded)."
)

#: Keyword hints that flag a request as a game-art task.
ART_REQUEST_HINTS: tuple[str, ...] = (
    "game art", "game-art", "concept art", "sprite", "texture", "asset",
    "3d model", "mesh", "turntable", "vfx", "flipbook", "particle",
    "character", "prop", "environment art", "pipeline", "render",
    "unity", "unreal", "godot", "image generation", "img2img", "controlnet",
    "美术", "贴图", "建模", "角色", "素材", "特效", "原画", "渲染",
)

#: Nodes (beyond ``Art.*``) that form the art pipeline backbone.
_PIPELINE_BUILTINS = ("QualityGateNode", "IterativeRefineNode", "AssetExportNode")

_TPL_ART_PATTERN = (
    "Flagship pattern (config/workflows/templates/TPL-ART-01.yaml):\n"
    "  Art.ImageGen → Art.QualityCritic → QualityGateNode\n"
    "    ├─(fail)→ IterativeRefineNode → (loops back to Art.ImageGen)\n"
    "    └─(pass)→ Art.Mesh3D / Art.VideoGen → AssetExportNode\n"
    "Reuse this shape; only swap node params (prompt, style, size, format, engine)."
)


def looks_like_art_request(text: str | None) -> bool:
    """Heuristic: does *text* read like a game-art production request?"""
    if not text:
        return False
    low = text.lower()
    return any(hint in low for hint in ART_REQUEST_HINTS)


def build_art_node_catalog(registry: Any | None = None) -> str:
    """Introspect the node registry into a compact, graph-aware node catalog.

    Lists each art / pipeline node's id plus its typed input/output sockets so
    the agent wires real registered nodes. Falls back to a static list when the
    registry is unavailable (keeps the playbook useful before bootstrap).
    """
    snapshot = _registry_snapshot(registry)
    if not snapshot:
        return _static_catalog()

    lines: list[str] = []
    for node_id in sorted(snapshot):
        if not (node_id.startswith("Art.") or node_id in _PIPELINE_BUILTINS):
            continue
        info = snapshot[node_id]
        inputs = _socket_names(info, "input")
        outputs = _socket_names(info, "output")
        desc = _node_description(info)
        sig = f"  {node_id}({', '.join(inputs)}) -> ({', '.join(outputs)})"
        lines.append(f"{sig}\n      {desc}" if desc else sig)

    if not lines:
        return _static_catalog()
    return "Registered art node catalog (wire these by id):\n" + "\n".join(lines)


def render_art_playbook(registry: Any | None = None) -> str:
    """Assemble the full art playbook system-prompt block."""
    return "\n\n".join(
        [
            "# Game-art pipeline playbook",
            ART_ONTOLOGY,
            build_art_node_catalog(registry),
            _TPL_ART_PATTERN,
            ART_TOOL_SEQUENCE,
        ]
    )


def plan_art_tasks(brief: str | None) -> list[dict[str, str]]:
    """Decompose a creative *brief* into an ordered ``todo_write`` step list.

    Keyword-driven and deterministic: the spine is always concept → evaluate →
    self-correct → export, with mesh / video / vfx / upscale stages added when
    the brief asks for them. Returns ``[{id, content, status}]`` ready to hand
    to the ``todo_write`` tool.
    """
    text = (brief or "").strip()
    low = text.lower()
    subject = _subject_phrase(text)

    steps: list[str] = [
        f"Generate concept image for {subject} (Art.ImageGen)",
        "Score the asset and gate on quality (Art.QualityCritic → QualityGateNode)",
        "Wire a bounded self-correction loop (IterativeRefineNode → Art.ImageGen)",
    ]
    if any(k in low for k in ("turnaround", "multi-angle", "sheet", "multi angle", "转面", "三视图")):
        steps.append("Add multi-angle turnaround sheet (Art.CameraControl → Art.ImageGen)")
    if any(k in low for k in ("upscale", "high-res", "hi-res", "4k", "高清", "放大")):
        steps.append("Super-resolve the approved image (Art.Upscale)")
    if any(k in low for k in ("3d", "mesh", "model", "建模", "模型")):
        steps.append("Generate 3D mesh from the concept (Art.Mesh3D)")
    if any(k in low for k in ("video", "turntable", "animation", "idle", "clip", "动画", "视频")):
        steps.append("Produce a motion clip (Art.VideoGen)")
    if any(k in low for k in ("vfx", "flipbook", "particle", "spell", "explosion", "特效")):
        steps.append("Produce a VFX flipbook (Art.VFXGen)")

    engine = _engine_hint(low)
    export = "Package an engine-ready bundle (AssetExportNode"
    export += f", engine={engine})" if engine else ")"
    steps.append(export)
    steps.append("Save (workflow_save) and run (workflow_run); re-run if below bar")

    return [
        {"id": f"art-{i + 1}", "content": step, "status": "pending"}
        for i, step in enumerate(steps)
    ]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _engine_hint(low: str) -> str:
    for engine in ("unity", "unreal", "godot"):
        if engine in low:
            return engine
    return ""


def _subject_phrase(text: str) -> str:
    """Extract a short subject phrase from the brief for step descriptions."""
    if not text:
        return "the asset"
    # Prefer a quoted phrase if present.
    quoted = re.search(r"['\"\u2018\u201c]([^'\"\u2019\u201d]{2,60})['\"\u2019\u201d]", text)
    if quoted:
        return quoted.group(1).strip()
    words = text.split()
    return " ".join(words[:8]) if words else "the asset"


def _registry_snapshot(registry: Any | None) -> dict[str, Any]:
    try:
        if registry is None:
            from leagent.workflow.nodes import get_registry

            registry = get_registry()
        snap = registry.snapshot()
        return snap if isinstance(snap, dict) else {}
    except Exception:  # noqa: BLE001 - registry not booted yet
        return {}


def _socket_names(info: Any, side: str) -> list[str]:
    """Best-effort extraction of input/output socket ids from a snapshot entry."""
    try:
        data = info.get(side) if isinstance(info, dict) else getattr(info, side, None)
        if isinstance(data, dict):
            names: list[str] = []
            for bucket in ("required", "optional"):
                section = data.get(bucket)
                if isinstance(section, dict):
                    names.extend(section.keys())
            if not names:
                names = [k for k in data.keys() if k not in ("required", "optional")]
            return names[:6]
        if isinstance(data, (list, tuple)):
            return [str(x) for x in data][:6]
    except Exception:  # noqa: BLE001
        pass
    return []


def _node_description(info: Any) -> str:
    try:
        desc = info.get("description") if isinstance(info, dict) else getattr(info, "description", "")
        return str(desc or "").split("\n", 1)[0][:100]
    except Exception:  # noqa: BLE001
        return ""


def _static_catalog() -> str:
    return (
        "Art node catalog (wire these by id):\n"
        "  Art.ImageGen(prompt, image?, camera?, control?, width, height, style) -> (image, preview_url, success)\n"
        "  Art.Upscale(image, prompt?, scale) -> (image, preview_url, success)\n"
        "  Art.Mesh3D(prompt, image?, camera?, format) -> (mesh, preview_url, success)\n"
        "  Art.VideoGen(prompt, image?, camera?, duration, fps) -> (video, preview_url, success)\n"
        "  Art.VFXGen(prompt, image?, frames, cols, fps, fx_type) -> (vfx, preview_url, success)\n"
        "  Art.CameraControl(...) -> (camera)\n"
        "  Art.PoseControl(...) -> (control)\n"
        "  Art.QualityCritic(asset, criteria) -> (score, critique, asset)\n"
        "  QualityGateNode(asset, score, threshold) -> (passed, asset)\n"
        "  IterativeRefineNode(...) -> (feedback loop-back)\n"
        "  AssetExportNode(image?, video?, mesh?, engine) -> (manifest, assets, bundle_url)"
    )
