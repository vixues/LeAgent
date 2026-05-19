"""``NodeOutput`` — result envelope returned by every node's ``execute``.

Port of ComfyUI's ``NodeOutput`` augmented for the leagent control-flow
domain: ``next_node`` is the node_id the scheduler should route to next
(used by Condition, HumanReview, ErrorHandler). A ``None`` ``next_node``
means "follow the node's default successor".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NodeOutput:
    """Envelope for a single node's execution result.

    Fields:

    - ``values``: positional values matching the node's ``RETURN_TYPES``.
      Single-output nodes pass ``(value,)`` or ``value``.
    - ``ui``: optional UI payload published via the ``executed`` WS event.
    - ``expand``: subgraph-expansion description (``DynamicPrompt`` nodes
      to splice in). A non-empty value causes the scheduler to stage the
      expanded nodes before this one completes.
    - ``block_execution``: if truthy, marks the node "blocked" (e.g. human
      review). The scheduler adds an external block and pauses. Cleared via
      a resume call.
    - ``next_node``: control-flow routing override. If set, the scheduler
      prunes the other outgoing branches and routes to this node_id.
    - ``metadata``: arbitrary metadata persisted with the execution record.
    """

    values: Any = None
    ui: dict[str, Any] | None = None
    expand: dict[str, Any] | None = None
    block_execution: str | None = None
    next_node: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_tuple(self) -> tuple[Any, ...]:
        """Normalize ``values`` to a tuple for downstream wiring."""
        if self.values is None:
            return ()
        if isinstance(self.values, tuple):
            return self.values
        return (self.values,)

    @classmethod
    def single(cls, value: Any, **kwargs: Any) -> "NodeOutput":
        return cls(values=(value,), **kwargs)
