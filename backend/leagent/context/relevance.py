"""Relevance gating primitive for on-demand prompt sources.

A :class:`RelevanceGate` is the single, testable lever that decides whether a
heavy, domain-specific prompt block (canvas/GenUI rules, document-font guidance,
the art playbook, the leagent.js runtime reference, ...) should be injected into
the system prompt for a given turn. It keeps the always-on prompt lean by
default and only pays for a block when the turn is actually about that domain.

Three signals feed the decision, in priority order:

1. **Explicit harness opt-in** — a truthy ``template_vars[key]`` for any of the
   gate's ``opt_in_keys``. This is the deterministic lever the runtime harness
   (workflow steps, ``HtmlFrame`` mini-apps via ``chat.ask``, batch jobs) uses
   to force-enable a domain regardless of the wording of the user query.
2. **Workflow hint** — a keyword match against an explicit ``workflow_hint``.
3. **Query heuristic** — a keyword match against the user query.

The same primitive backs every gated source so the boundaries stay uniform and
there is exactly one place to reason about (and test) gating behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["RelevanceGate"]


@dataclass(frozen=True)
class RelevanceGate:
    """Decide whether a domain-specific prompt block is relevant this turn.

    Attributes:
        name: Stable identifier for logging / debugging.
        hints: Lower-case substrings that flag a query (or workflow hint) as
            belonging to this domain. Keep these specific — broad tokens
            false-positive on unrelated turns.
        opt_in_keys: ``template_vars`` keys that, when truthy, force the gate
            open regardless of the query wording (the harness lever).
    """

    name: str
    hints: tuple[str, ...] = ()
    opt_in_keys: tuple[str, ...] = ()

    def opted_in(
        self,
        *,
        template_vars: dict[str, Any] | None = None,
        workflow_hint: str | None = None,
    ) -> bool:
        """Return whether the harness explicitly enabled this domain."""
        if template_vars:
            for key in self.opt_in_keys:
                if template_vars.get(key):
                    return True
        return bool(workflow_hint and self._matches_text(workflow_hint))

    def matches(
        self,
        query: str | None,
        *,
        workflow_hint: str | None = None,
        template_vars: dict[str, Any] | None = None,
    ) -> bool:
        """Return whether the block should be injected for this turn."""
        if self.opted_in(template_vars=template_vars, workflow_hint=workflow_hint):
            return True
        return self._matches_text(query)

    def _matches_text(self, text: str | None) -> bool:
        if not text or not self.hints:
            return False
        low = text.lower()
        return any(hint in low for hint in self.hints)
