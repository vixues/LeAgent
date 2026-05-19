"""Schema dataclass — the canonical metadata for a workflow node.

Each node subclass declares a ``Schema`` in ``define_schema()``. The registry
uses it to serve ``/object_info``; the validator uses it to type-check links
and required inputs; the runner uses it to marshal inputs into the node's
``execute`` kwargs.

Contract-parity flags (modelled after the reference ``_io.py``):

- ``is_input_list`` — the node opts in to receiving batched, list-typed
  inputs in a single call (the runner skips per-item fan-out).
- ``accept_all_inputs`` — the node accepts arbitrary extra inputs keyed by
  runtime socket names (e.g. merge nodes). The validator skips "unknown
  input" checks when this is on.
- ``has_intermediate_output`` — the node emits progress outputs via
  ``NodeOutput.progress(...)``. The runner multiplexes them through the
  progress registry.
- ``input_order`` — explicit ordering for the frontend editor, separate
  from schema declaration order.
- ``output_tooltips`` — per-output UI hover text, aligned with
  :attr:`outputs` indices.
- ``output_matchtypes`` — additional types an output slot can satisfy (for
  polymorphic link compatibility).
- ``enable_expand`` — the runner honors :attr:`NodeOutput.expand`. Nodes
  that do not opt in and still return an expanded subgraph raise
  :class:`leagent.workflow.engine.errors.WorkflowEngineError`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .hidden import Hidden
from .types import InputBase, OutputBase


@dataclass
class Schema:
    """Canonical metadata describing one node class."""

    node_id: str
    display_name: str = ""
    category: str = "workflow"
    description: str = ""

    inputs: list[InputBase] = field(default_factory=list)
    outputs: list[OutputBase] = field(default_factory=list)
    hidden: list[Hidden] = field(default_factory=list)

    is_output_node: bool = False
    not_idempotent: bool = False
    enable_expand: bool = False
    is_deprecated: bool = False
    is_experimental: bool = False
    control_flow: bool = False

    is_input_list: bool = False
    accept_all_inputs: bool = False
    has_intermediate_output: bool = False
    input_order: list[str] = field(default_factory=list)
    output_tooltips: list[str] = field(default_factory=list)
    output_matchtypes: list[str] = field(default_factory=list)

    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.display_name:
            self.display_name = self.node_id
        self._input_by_id = {i.id: i for i in self.inputs}
        self._output_by_id = {o.id: o for o in self.outputs if o.id}

    def validate(self) -> list[str]:
        """Return a list of structural errors."""
        errors: list[str] = []
        if not self.node_id:
            errors.append("Schema.node_id is required")
        if not self.category:
            errors.append("Schema.category is required")
        seen_ids: set[str] = set()
        for inp in self.inputs:
            if not inp.id:
                errors.append(f"input without id in {self.node_id}")
                continue
            if inp.id in seen_ids:
                errors.append(f"duplicate input id '{inp.id}' in {self.node_id}")
            seen_ids.add(inp.id)
        if self.input_order:
            known = {inp.id for inp in self.inputs}
            for iid in self.input_order:
                if iid not in known:
                    errors.append(
                        f"input_order references unknown input '{iid}' in {self.node_id}"
                    )
        if self.output_tooltips and len(self.output_tooltips) > len(self.outputs):
            errors.append(
                f"output_tooltips has more entries than outputs in {self.node_id}"
            )
        return errors

    def finalize(self) -> "Schema":
        errors = self.validate()
        if errors:
            raise ValueError(f"Invalid schema for {self.node_id}: {errors}")
        return self

    def get_input(self, input_id: str) -> InputBase | None:
        return self._input_by_id.get(input_id)

    def required_input_ids(self) -> list[str]:
        return [i.id for i in self.inputs if not i.optional]

    def return_types(self) -> tuple[str, ...]:
        return tuple(o.get_io_type() for o in self.outputs)

    def return_names(self) -> tuple[str, ...]:
        return tuple(o.id or f"out{idx}" for idx, o in enumerate(self.outputs))

    def ordered_input_ids(self) -> list[str]:
        """Resolve the final editor-visible input order.

        Honors :attr:`input_order` when set, otherwise falls back to the
        declaration order of :attr:`inputs`.
        """
        if not self.input_order:
            return [inp.id for inp in self.inputs]
        declared = [inp.id for inp in self.inputs]
        remaining = [iid for iid in declared if iid not in self.input_order]
        return list(self.input_order) + remaining

    def get_info_dict(self) -> dict[str, Any]:
        """Serialize to the ``/object_info`` entry shape for the front-end."""
        required: dict[str, Any] = {}
        optional: dict[str, Any] = {}
        hidden_dict: dict[str, str] = {}

        for inp in self.inputs:
            spec = inp.as_dict()
            entry: Any
            if isinstance(spec["type"], list):
                entry = (spec["type"], spec["options"])
            else:
                entry = (spec["type"], spec["options"])
            bucket = optional if inp.optional else required
            bucket[inp.id] = entry

        for h in self.hidden:
            hidden_dict[h.value] = h.value.upper()

        return {
            "name": self.node_id,
            "display_name": self.display_name,
            "category": self.category,
            "description": self.description,
            "output_node": self.is_output_node,
            "deprecated": self.is_deprecated,
            "experimental": self.is_experimental,
            "input": {"required": required, "optional": optional, "hidden": hidden_dict},
            "input_order": self.ordered_input_ids(),
            "output": [o.get_io_type() for o in self.outputs],
            "output_name": list(self.return_names()),
            "output_is_list": [bool(o.is_list) for o in self.outputs],
            "output_tooltips": list(self.output_tooltips),
            "output_matchtypes": list(self.output_matchtypes),
            "control_flow": self.control_flow,
            "enable_expand": self.enable_expand,
            "is_input_list": self.is_input_list,
            "accept_all_inputs": self.accept_all_inputs,
            "has_intermediate_output": self.has_intermediate_output,
            "not_idempotent": self.not_idempotent,
            "metadata": self.metadata,
        }
