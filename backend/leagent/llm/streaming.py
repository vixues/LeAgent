"""Tool-call stream assembler.

The LLM provider layer emits :class:`~leagent.llm.base.StreamChunk` units;
the agent loop normalises those into ``ModelStreamEvent`` at a single
boundary (``agent/deps.py::_make_llm_call_model``), and the SDK kernel
collapses ``SDKMessage`` → :class:`~leagent.sdk.events.AgentEvent` at one
more boundary (``sdk/kernel/loop.py``). Those are the two — and only two —
streaming shape boundaries.

This module owns the small, focused piece of that normalisation that is
genuinely reusable: :class:`ToolCallStreamAssembler` coalesces OpenAI-shaped
tool-call deltas into complete tool-call dicts. ``ToolCallDelta`` /
``ToolCallComplete`` are its return types.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# ── Tool-call event types ───────────────────────────────────────────────


@dataclass
class ToolCallDelta:
    """Partial tool-call update (for UI progress)."""

    index: int
    tool_call_id: str | None = None
    name: str | None = None
    arguments_fragment: str = ""


@dataclass
class ToolCallComplete:
    """A fully assembled tool-call."""

    tool_call_id: str
    name: str
    arguments: str


# ── Tool-call stream assembler ──────────────────────────────────────────

_EMIT_INTERVAL_MS = 48
_EMIT_MIN_BYTES = 512


@dataclass
class _ToolSlot:
    """Accumulator for one in-flight tool-call."""

    tool_call_id: str = ""
    name: str = ""
    arguments: str = ""
    last_emit_len: int = 0
    last_emit_time: float = 0.0


class ToolCallStreamAssembler:
    """Coalesce OpenAI-shaped ``tool_calls_delta`` into complete calls.

    Providers emit incremental deltas indexed by slot position.  This
    class accumulates them and yields :class:`ToolCallDelta` (throttled
    for UI) and :class:`ToolCallComplete` events.

    Replaces the inline coalescing logic that was in
    ``agent/deps.py::_make_llm_call_model``.
    """

    def __init__(self) -> None:
        self._slots: dict[int, _ToolSlot] = {}

    @property
    def pending_count(self) -> int:
        return len(self._slots)

    def has_pending(self) -> bool:
        return bool(self._slots)

    def feed_deltas(
        self, deltas: list[dict[str, Any]],
    ) -> list[ToolCallDelta]:
        """Ingest a batch of OpenAI-shaped deltas and return UI deltas."""
        ui_deltas: list[ToolCallDelta] = []
        for delta in deltas:
            idx = delta.get("index", 0)
            slot = self._slots.setdefault(idx, _ToolSlot())

            tc_id = delta.get("id") or ""
            if tc_id:
                slot.tool_call_id = tc_id

            func = delta.get("function") or {}
            name = func.get("name") or ""
            if name:
                slot.name = name

            args_frag = func.get("arguments")
            if args_frag:
                # OpenAI streams string fragments; some gateways emit a whole
                # dict. Normalise to the string accumulator either way.
                if not isinstance(args_frag, str):
                    args_frag = json.dumps(args_frag, ensure_ascii=False)
                slot.arguments += args_frag

            if self._should_emit_ui(slot):
                ui_deltas.append(ToolCallDelta(
                    index=idx,
                    tool_call_id=slot.tool_call_id or None,
                    name=slot.name or None,
                    arguments_fragment=slot.arguments[slot.last_emit_len:],
                ))
                slot.last_emit_len = len(slot.arguments)
                slot.last_emit_time = time.monotonic()

        return ui_deltas

    def slots_as_dicts(self) -> dict[int, dict[str, Any]]:
        """Return a non-draining snapshot of in-flight slots.

        Shape matches the ``{"id", "name", "arguments"}`` dict the agent loop
        consumed from its former inline ``pending_tool_calls`` accumulator, so
        callers can keep their own throttling / finalization while delegating
        the raw delta coalescing to this assembler.
        """
        return {
            idx: {"id": slot.tool_call_id, "name": slot.name, "arguments": slot.arguments}
            for idx, slot in sorted(self._slots.items())
        }

    def finalize(self) -> list[ToolCallComplete]:
        """Drain all accumulated slots into complete tool-call objects."""
        results: list[ToolCallComplete] = []
        for _idx, slot in sorted(self._slots.items()):
            results.append(ToolCallComplete(
                tool_call_id=slot.tool_call_id,
                name=slot.name,
                arguments=slot.arguments,
            ))
        self._slots.clear()
        return results

    def finalize_as_dicts(self) -> list[dict[str, Any]]:
        """Drain all accumulated slots as plain dicts (legacy compat)."""
        results: list[dict[str, Any]] = []
        for _idx, slot in sorted(self._slots.items()):
            args = slot.arguments
            parsed: Any
            try:
                parsed = json.loads(args) if args else {}
            except (json.JSONDecodeError, ValueError):
                parsed = args
            results.append({
                "id": slot.tool_call_id,
                "name": slot.name,
                "arguments": parsed,
                "_raw_arguments": args,
            })
        self._slots.clear()
        return results

    @staticmethod
    def _should_emit_ui(slot: _ToolSlot) -> bool:
        args_len = len(slot.arguments)
        if args_len - slot.last_emit_len < _EMIT_MIN_BYTES:
            return False
        elapsed_ms = (time.monotonic() - slot.last_emit_time) * 1000
        return elapsed_ms >= _EMIT_INTERVAL_MS


__all__ = [
    "ToolCallComplete",
    "ToolCallDelta",
    "ToolCallStreamAssembler",
]
