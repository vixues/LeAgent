"""``Art.QualityCritic`` — perceptual / LLM-vision asset scorer.

The evaluation brain of the self-correction loop. It inspects an upstream
:class:`~leagent.workflow.io.media.MediaRef` and produces a quality ``score``
in ``[0, 1]`` plus a free-text ``critique``. The score is meant to be wired
into a :class:`QualityGateNode`'s ``score`` input (which otherwise falls back
to its deterministic iteration heuristic).

Scoring strategy (first usable wins):

1. **Vision LLM critique** — when a multimodal LLM service is reachable, the
   asset is sent to the model with the acceptance criteria and the model
   returns a JSON ``{"score": float, "critique": str}``.
2. **Deterministic heuristic** — when offline (no LLM, forced-offline, or a
   placeholder asset), the score improves with the refine iteration
   (``base + step * iteration``) so credential-free demos still exercise the
   full generate -> evaluate -> regenerate loop reproducibly.

The critique is written to ``state['refine_feedback']`` so the next
regeneration pass is conditioned on concrete, perceptual feedback.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import structlog

from leagent.workflow.io import IO, Hidden, HiddenHolder, NodeOutput, Schema
from leagent.workflow.io.media import MediaRef, to_gen_ui_tree
from leagent.workflow.nodes.base import WorkflowNode

logger = structlog.get_logger(__name__)


class QualityCriticNode(WorkflowNode):
    NODE_ID = "Art.QualityCritic"
    DISPLAY_TITLE = "Quality Critic"

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="Art.QualityCritic",
            display_name="Quality Critic",
            category="art/evaluate",
            description=(
                "Score an asset for quality using a vision LLM (when available) "
                "or a deterministic offline heuristic. Wire `score` into a "
                "QualityGateNode and `critique` into the refine feedback loop."
            ),
            inputs=[
                IO.Any.Input(id="asset", optional=True,
                             tooltip="The asset (image/video/mesh MediaRef) to evaluate."),
                IO.String.Input(id="criteria", optional=True, multiline=True,
                                tooltip="Acceptance criteria the asset is judged against."),
                IO.String.Input(id="model", optional=True,
                                tooltip="Optional vision model id (provider default when blank)."),
                IO.String.Input(id="iteration_var", optional=True, default="refine_iteration",
                                tooltip="State variable holding the refine iteration count."),
                IO.Float.Input(id="base_score", optional=True, default=0.45, min=0.0, max=1.0,
                               tooltip="Offline heuristic base score at iteration 0."),
                IO.Float.Input(id="score_step", optional=True, default=0.3, min=0.0, max=1.0,
                               tooltip="Offline heuristic score gain per refine iteration."),
            ],
            outputs=[
                IO.Float.Output(id="score"),
                IO.String.Output(id="critique"),
                IO.Any.Output(id="asset"),
            ],
            hidden=[Hidden.UNIQUE_ID, Hidden.WORKFLOW_STATE, Hidden.TOOL_CONTEXT],
            not_idempotent=True,
        )

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        state = hidden.workflow_state
        asset = inputs.get("asset")
        ref = MediaRef.from_dict(asset) if isinstance(asset, dict) else (
            asset if isinstance(asset, MediaRef) else None
        )
        criteria = str(inputs.get("criteria") or "").strip()

        score, critique, source = await self._score(hidden, ref, criteria, inputs, state)

        if state is not None:
            state.set("quality_score", round(score, 4))
            if critique:
                state.set("refine_feedback", critique)

        # Production feedback: attribute the quality score to the provider that
        # generated this asset so the CapabilityRouter can self-optimize. Skip
        # the offline floor (deterministic) and unknown providers.
        self._record_provider_quality(ref, score)

        logger.info(
            "art_quality_critic", node_id=hidden.unique_id, score=round(score, 4),
            source=source, has_critique=bool(critique),
        )
        meta: dict[str, Any] = {"score": round(score, 4), "source": source}
        if ref is not None and ref.src:
            meta.update({
                "kind": ref.kind,
                "file_id": ref.file_id,
                "src": ref.src,
                "preview_url": ref.src,
                "filename": ref.filename,
                "width": ref.width,
                "height": ref.height,
            })
        return NodeOutput(
            values=(round(score, 4), critique, asset),
            ui={"gen_ui": to_gen_ui_tree([ref], title=type(self).DISPLAY_TITLE)} if ref and ref.src else None,
            metadata=meta,
        )

    @staticmethod
    def _record_provider_quality(ref: MediaRef | None, score: float) -> None:
        if ref is None:
            return
        provider = str(ref.meta.get("provider") or "").strip()
        if not provider or provider == "offline":
            return
        try:
            from leagent.llm.capabilities import get_provider_stats, kind_to_task

            task = kind_to_task(ref.kind)
            if task is not None:
                get_provider_stats().record_quality(task.value, provider, score)
        except Exception:  # noqa: BLE001 - telemetry must not break the run
            pass

    # -- scoring backends --------------------------------------------------

    async def _score(
        self,
        hidden: HiddenHolder,
        ref: MediaRef | None,
        criteria: str,
        inputs: dict[str, Any],
        state: Any,
    ) -> tuple[float, str, str]:
        """Return ``(score, critique, source)``."""
        ctx = hidden.tool_context
        llm = getattr(ctx, "llm_service", None) if ctx else None
        offline_env = os.environ.get("LEAGENT_ART_OFFLINE", "").strip().lower() in (
            "1", "true", "yes",
        )
        offline_meta = bool(state is not None and state.metadata.get("art_offline"))
        offline_asset = bool(ref and str(ref.meta.get("provider") or "") == "offline")
        placeholder = bool(ref and ref.meta.get("placeholder"))
        src = ref.src if ref else None

        if (
            llm is None
            or offline_env
            or offline_meta
            or offline_asset
            or placeholder
            or not src
            or not _vision_url_reachable(src)
        ):
            return self._heuristic(inputs, state), "", "heuristic"

        try:
            return await self._vision_score(llm, src, criteria, inputs)
        except Exception as exc:  # noqa: BLE001 - never fail the run on a critic error
            logger.warning("art_quality_critic_vision_failed", error=str(exc))
            return self._heuristic(inputs, state), "", "heuristic_fallback"

    async def _vision_score(
        self, llm: Any, src: str, criteria: str, inputs: dict[str, Any],
    ) -> tuple[float, str, str]:
        from leagent.llm import ChatMessage

        instruction = (
            "You are a senior game-art QA reviewer. Evaluate the attached asset "
            "against the acceptance criteria and respond with STRICT JSON only: "
            '{"score": <float 0..1>, "critique": "<one concise sentence of '
            'actionable feedback>"}. '
            f"Acceptance criteria: {criteria or 'production-ready, on-style, clean silhouette, no artifacts.'}"
        )
        content = [
            {"type": "text", "text": instruction},
            {"type": "image_url", "image_url": {"url": src}},
        ]
        response = await llm.complete(
            messages=[ChatMessage.user(content)],
            model=inputs.get("model") or None,
            temperature=0.0,
            max_tokens=512,
        )
        text = (response.content or "").strip()
        score, critique = _parse_score_json(text)
        return score, critique, "vision"

    def _heuristic(self, inputs: dict[str, Any], state: Any) -> float:
        iteration = 0
        if state is not None:
            var = str(inputs.get("iteration_var") or "refine_iteration")
            try:
                iteration = int(state.get(var, 0) or 0)
            except (ValueError, TypeError):
                iteration = 0
        base = float(inputs.get("base_score") if inputs.get("base_score") is not None else 0.45)
        step = float(inputs.get("score_step") if inputs.get("score_step") is not None else 0.3)
        return max(0.0, min(base + step * iteration, 1.0))


def _parse_score_json(text: str) -> tuple[float, str]:
    """Extract ``(score, critique)`` from a (possibly fenced) JSON blob."""
    blob = text
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        blob = fence.group(1)
    else:
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        if brace:
            blob = brace.group(0)
    try:
        data = json.loads(blob)
    except (json.JSONDecodeError, TypeError):
        # Last resort: a bare number anywhere in the text.
        num = re.search(r"(\d*\.?\d+)", text)
        score = float(num.group(1)) if num else 0.5
        return max(0.0, min(score, 1.0)), text[:300]
    score = data.get("score", 0.5)
    try:
        score = float(score)
    except (TypeError, ValueError):
        score = 0.5
    critique = str(data.get("critique") or "").strip()
    return max(0.0, min(score, 1.0)), critique


def _vision_url_reachable(url: str) -> bool:
    """Only public http(s) or data URLs are usable by remote vision models."""
    if url.startswith("data:"):
        return True
    lower = url.lower()
    if not (lower.startswith("http://") or lower.startswith("https://")):
        return False
    return "localhost" not in lower and "127.0.0.1" not in lower


__all__ = ["QualityCriticNode"]
