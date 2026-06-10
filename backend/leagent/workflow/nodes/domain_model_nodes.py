"""Build ``Model.<task>.<provider>`` workflow nodes from domain-model adapters.

Each registered :class:`~leagent.llm.domain_registry.DomainModelAdapter`
becomes a typed palette node whose inputs mirror the adapter's declared
:class:`~leagent.llm.domain_registry.DomainParam` schema and whose outputs
are the uniform domain-result envelope:

``(text, data_b64, mime, result, success)``

* ``text``     — primary text payload (ASR transcript, URL, caption)
* ``data_b64`` — primary binary payload, base64 (TTS audio, generated image)
* ``mime``     — MIME type of ``data_b64``
* ``result``   — full result envelope (metadata, model, provider)
* ``success``  — invocation success flag for downstream branching
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

import structlog

from leagent.workflow.io import IO, Hidden, HiddenHolder, InputBase, NodeOutput, Schema
from leagent.workflow.nodes.base import WorkflowNode

if TYPE_CHECKING:
    from leagent.llm.domain_registry import (
        DomainModelAdapter,
        DomainModelSpec,
        DomainParam,
    )

logger = structlog.get_logger(__name__)

#: Canonical output slot order for every domain-model node.
MODEL_OUTPUT_NAMES = ("text", "data_b64", "mime", "result", "success")


def _param_to_input(param: DomainParam) -> InputBase:
    """Map an adapter parameter onto a typed workflow input."""
    common: dict[str, Any] = {
        "id": param.id,
        "optional": not param.required,
    }
    if param.default is not None:
        common["default"] = param.default
    if param.tooltip:
        common["tooltip"] = param.tooltip

    io_type = param.io_type.upper()
    if io_type == "INT":
        return IO.Int.Input(
            **common,
            min=int(param.min) if param.min is not None else None,
            max=int(param.max) if param.max is not None else None,
        )
    if io_type == "FLOAT":
        return IO.Float.Input(
            **common,
            min=float(param.min) if param.min is not None else None,
            max=float(param.max) if param.max is not None else None,
        )
    if io_type == "BOOLEAN":
        return IO.Boolean.Input(**common)
    if io_type == "COMBO":
        return IO.Combo.Input(**common, choices=list(param.choices))
    if io_type == "FILE":
        return IO.File.Input(**common)
    if io_type == "OBJECT":
        return IO.Object.Input(**common)
    # STRING and any unknown types fall back to a (multiline?) string input.
    return IO.String.Input(**common, multiline=param.multiline)


def build_domain_model_node(adapter: DomainModelAdapter) -> type[WorkflowNode]:
    """Create a :class:`WorkflowNode` subclass for one adapter."""
    spec: DomainModelSpec = adapter.spec
    node_id = f"Model.{spec.task}.{spec.provider}"
    display = spec.display_name or f"{spec.task} ({spec.provider})"

    schema = Schema(
        node_id=node_id,
        display_name=display,
        category=f"models/{spec.task}",
        description=spec.description or f"Run the {spec.provider} {spec.task} model.",
        inputs=[_param_to_input(p) for p in spec.params],
        outputs=[
            IO.String.Output(id="text"),
            IO.String.Output(id="data_b64"),
            IO.String.Output(id="mime"),
            IO.Object.Output(id="result"),
            IO.Boolean.Output(id="success"),
        ],
        hidden=[Hidden.UNIQUE_ID, Hidden.WORKFLOW_STATE],
        metadata={
            "domain_task": spec.task,
            "domain_provider": spec.provider,
            "domain_model": spec.model,
            "domain_output": spec.output,
        },
        not_idempotent=True,
    )

    class _DomainModelNode(WorkflowNode):
        NODE_ID = node_id
        _adapter = adapter
        _schema = schema

        @classmethod
        def define_schema(cls) -> Schema:
            return cls._schema

        async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
            params = {k: v for k, v in inputs.items() if v is not None}
            # Resolve {{var}} templates against the workflow state.
            state = hidden.workflow_state
            if state is not None:
                params = {
                    k: state.resolve_template(v) if isinstance(v, str) else v
                    for k, v in params.items()
                }
            # Live progress: adapters that opt in receive a `_progress(step,
            # total)` callback that streams onto the canvas (diffusion steps).
            if spec.supports_progress and hidden.progress is not None:
                progress_registry = hidden.progress
                node_unique_id = hidden.unique_id

                def _progress(step: int, total: int) -> None:
                    progress_registry.update(
                        value=float(step),
                        max=float(total or 1),
                        node_id=node_unique_id,
                    )

                params["_progress"] = _progress
            try:
                result = await type(self)._adapter.invoke(**params)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "domain_model_node_error",
                    node=node_id,
                    error=str(exc),
                    exc_info=True,
                )
                return NodeOutput(error=str(exc), metadata={"node_id": hidden.unique_id})

            if not result.success:
                return NodeOutput(
                    error=result.error or f"{node_id} invocation failed",
                    metadata={"node_id": hidden.unique_id, "provider": result.provider},
                )

            envelope = asdict(result)
            return NodeOutput(
                values=(
                    result.text or result.url or "",
                    result.b64_data or "",
                    result.mime,
                    envelope,
                    result.success,
                ),
                metadata={
                    "model": result.model,
                    "provider": result.provider,
                    "task": spec.task,
                },
            )

    _DomainModelNode.__name__ = f"DomainModelNode_{spec.task}_{spec.provider}"
    _DomainModelNode.__qualname__ = _DomainModelNode.__name__
    return _DomainModelNode


__all__ = ["build_domain_model_node", "MODEL_OUTPUT_NAMES"]
