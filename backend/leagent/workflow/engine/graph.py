"""Execution graph primitives.

``DynamicPrompt`` — holds the original (persisted) prompt and an ephemeral
layer for nodes spliced in at runtime via ``NodeOutput.expand``.
``TopologicalSort`` — dependency-closure helper that discovers upstream
nodes lazily (we may not know the full graph until ``expand`` resolves).
``ExecutionList`` — the scheduler. Exposes the primitives used by
``runner.py``: ``add_node``, ``add_strong_link``, ``add_external_block``,
``complete_node_execution``, ``stage_node_execution``.

Control-flow branching is handled by ``select_branch(node_id, chosen)`` —
all other successor branches declared under ``control`` are pruned so they
do not contribute dependencies.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Iterable

from .errors import BlockedError, DependencyCycleError


LinkRef = tuple[str, int]  # (upstream_node_id, slot)


@dataclass
class ExpandFrame:
    """A subgraph spliced in at runtime by a node's ``expand`` output."""

    parent_id: str
    call_idx: int
    nodes: dict[str, dict[str, Any]]


class DynamicPrompt:
    """Prompt view that layers ephemeral (expanded) nodes on the original."""

    def __init__(self, original: dict[str, dict[str, Any]]) -> None:
        self._original: dict[str, dict[str, Any]] = dict(original)
        self._ephemeral: dict[str, dict[str, Any]] = {}
        self._parent: dict[str, str] = {}

    @property
    def all_ids(self) -> set[str]:
        return set(self._original.keys()) | set(self._ephemeral.keys())

    def get(self, node_id: str) -> dict[str, Any] | None:
        return self._ephemeral.get(node_id) or self._original.get(node_id)

    def is_ephemeral(self, node_id: str) -> bool:
        return node_id in self._ephemeral

    def parent_of(self, node_id: str) -> str | None:
        return self._parent.get(node_id)

    def add_expanded(self, frame: ExpandFrame) -> list[str]:
        """Add a subgraph (namespacing ids as ``{parent}:{idx}:{id}``).
        Returns the namespaced ids.
        """
        added: list[str] = []
        prefix = f"{frame.parent_id}:{frame.call_idx}:"
        for raw_id, node in frame.nodes.items():
            qid = f"{prefix}{raw_id}"
            self._ephemeral[qid] = node
            self._parent[qid] = frame.parent_id
            added.append(qid)
        return added

    def remove(self, node_id: str) -> None:
        self._ephemeral.pop(node_id, None)
        self._parent.pop(node_id, None)


class TopologicalSort:
    """Compute dependency closures on a dynamic prompt.

    Dependencies come from input links ``["<upstream_id>", <slot>]`` and
    from *active* control-flow edges (``next``, chosen condition branch,
    ``error_handler`` only after a failure, etc.). Unresolved branches
    are pruned via ``ExecutionList.select_branch`` before the scheduler
    inspects them.
    """

    def __init__(self, prompt: DynamicPrompt) -> None:
        self.prompt = prompt
        self._active_succ: dict[str, set[str]] = {}
        self._pruned: dict[str, set[str]] = {}

    def set_active_successors(self, node_id: str, successors: Iterable[str]) -> None:
        self._active_succ[node_id] = set(successors)

    def prune(self, node_id: str, pruned: Iterable[str]) -> None:
        self._pruned.setdefault(node_id, set()).update(pruned)

    def upstream_of(self, node_id: str) -> list[LinkRef]:
        """Return the input links of ``node_id`` (pruned are skipped)."""
        node = self.prompt.get(node_id)
        if node is None:
            return []
        links: list[LinkRef] = []
        for _, value in (node.get("inputs") or {}).items():
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
                links.append((value[0], int(value[1])))
                continue
            if (
                isinstance(value, list)
                and value
                and all(
                    isinstance(item, list)
                    and len(item) == 2
                    and isinstance(item[0], str)
                    for item in value
                )
            ):
                for up_id, slot in value:
                    links.append((up_id, int(slot)))
        return links

    def successors_of(self, node_id: str) -> set[str]:
        """Successors currently considered active."""
        if node_id in self._active_succ:
            return self._active_succ[node_id]
        node = self.prompt.get(node_id)
        if not node:
            return set()
        control = node.get("control", {}) or {}
        succ: set[str] = set()
        if control.get("next"):
            succ.add(control["next"])
        for cond in control.get("conditions", []) or []:
            t = cond.get("then_node") or cond.get("then")
            if t:
                succ.add(t)
        for key in ("else_node", "else", "on_reject"):
            if control.get(key):
                succ.add(control[key])
        for branch in control.get("branches", []) or []:
            for n in branch.get("nodes", []) or []:
                succ.add(n)
        pruned = self._pruned.get(node_id, set())
        return {s for s in succ if s not in pruned}


@dataclass
class ExecutionState:
    ready: set[str] = field(default_factory=set)
    completed: set[str] = field(default_factory=set)
    in_progress: set[str] = field(default_factory=set)
    skipped: set[str] = field(default_factory=set)
    blocked: dict[str, set[str]] = field(default_factory=dict)  # node_id -> tags
    strong_links: dict[str, set[str]] = field(default_factory=dict)  # downstream -> upstream ids
    cache_links: dict[str, set[str]] = field(default_factory=dict)
    #: (src, dst) edges deactivated by branch selection. A pruned edge does
    #: not promote ``dst`` when ``src`` completes — this prevents a data
    #: link that crosses a control branch from prematurely activating a
    #: gated downstream node (e.g. QualityGate's pass branch on a fail).
    pruned_edges: set[tuple[str, str]] = field(default_factory=set)


class ExecutionList:
    """Scheduler primitives used by the runner.

    Usage (roughly):

        exec_list = ExecutionList(prompt, topo)
        for seed in output_nodes:
            exec_list.add_node(seed)
        while not exec_list.is_done():
            node_id = await exec_list.stage_node_execution()
            if node_id is None:
                break
            ...
            exec_list.complete_node_execution(node_id)
    """

    def __init__(self, prompt: DynamicPrompt, topo: TopologicalSort) -> None:
        self.prompt = prompt
        self.topo = topo
        self.state = ExecutionState()
        self._unblocked = asyncio.Event()
        self._cancelled = False

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def add_node(self, seed_id: str) -> None:
        """Walk upstream dependencies and register them as ready when possible."""
        stack = [seed_id]
        seen: set[str] = set()
        while stack:
            nid = stack.pop()
            if nid in seen:
                continue
            seen.add(nid)
            if self.prompt.get(nid) is None:
                continue
            # Populate this node's strong (data) links *before* the readiness
            # check — otherwise a seed node with input links is wrongly marked
            # ready (its own deps haven't been discovered yet).
            for up_id, _slot in self.topo.upstream_of(nid):
                if self.prompt.get(up_id) is not None:
                    self.state.strong_links.setdefault(nid, set()).add(up_id)
                    if up_id not in seen:
                        stack.append(up_id)
            if nid not in self.state.completed and nid not in self.state.in_progress:
                if not self._remaining_deps(nid):
                    self.state.ready.add(nid)

    def add_strong_link(self, upstream: str, slot: int, downstream: str) -> None:
        self.state.strong_links.setdefault(downstream, set()).add(upstream)
        if upstream not in self.state.completed:
            self.state.ready.discard(downstream)
        self.add_node(upstream)

    def cache_link(self, upstream: str, downstream: str) -> None:
        self.state.cache_links.setdefault(downstream, set()).add(upstream)

    # ------------------------------------------------------------------
    # Control-flow helpers
    # ------------------------------------------------------------------

    def select_branch(self, node_id: str, chosen: str | None) -> None:
        """Mark ``chosen`` as the only active successor; prune the others."""
        node = self.prompt.get(node_id) or {}
        control = node.get("control", {}) or {}
        all_succ: set[str] = set()
        if control.get("next"):
            all_succ.add(control["next"])
        for cond in control.get("conditions", []) or []:
            t = cond.get("then_node") or cond.get("then")
            if t:
                all_succ.add(t)
        for key in ("else_node", "else", "on_reject"):
            if control.get(key):
                all_succ.add(control[key])

        if chosen is None:
            active: set[str] = set()
        else:
            active = {chosen}
        pruned = all_succ - active
        self.topo.set_active_successors(node_id, active)
        self.topo.prune(node_id, pruned)
        # Recompute this node's pruned data/control edges: the chosen edge is
        # reactivated, the others deactivated. Keeps loops correct (a target
        # pruned on a failing pass is re-enabled when later chosen).
        self.state.pruned_edges = {
            (s, d) for (s, d) in self.state.pruned_edges if s != node_id
        }
        for p in pruned:
            self.state.pruned_edges.add((node_id, p))
        for p in pruned:
            self._skip_subtree(p)

    def reopen_or_add(self, node_id: str, *, allow_reopen: bool = False) -> None:
        """Route to ``node_id``, re-executing it only on a loop back-edge.

        For a normal forward edge (``allow_reopen=False``) this behaves like
        :meth:`add_node`; an already-completed target is left untouched.
        For a back-edge from a loop-safe node (``allow_reopen=True``) the
        target — and the completed nodes downstream of it that must re-run —
        are reset first so the bounded refine loop executes again.
        """
        if allow_reopen and (
            node_id in self.state.completed or node_id in self.state.skipped
        ):
            self.reopen(node_id)
        else:
            self.add_node(node_id)

    def reopen(self, node_id: str) -> None:
        """Reset a completed/skipped node and its completed descendants.

        Used by loop-safe back-edges (e.g. ``IterativeRefineNode``) so the
        generate -> evaluate -> regenerate cycle re-runs the loop body. The
        cascade follows both control successors and strong-link dependents,
        stopping at nodes that have not run yet.
        """
        if self.prompt.get(node_id) is None:
            return
        stack = [node_id]
        seen: set[str] = set()
        while stack:
            nid = stack.pop()
            if nid in seen:
                continue
            seen.add(nid)
            self.state.completed.discard(nid)
            self.state.skipped.discard(nid)
            self.state.ready.discard(nid)
            self.state.in_progress.discard(nid)
            for succ in self.topo.successors_of(nid):
                if succ in self.state.completed or succ in self.state.skipped:
                    stack.append(succ)
            for down, ups in self.state.strong_links.items():
                if nid in ups and (down in self.state.completed or down in self.state.skipped):
                    stack.append(down)
        self.add_node(node_id)

    def _skip_subtree(self, node_id: str) -> None:
        """Mark ``node_id`` + downstream graph as skipped (pruned branch)."""
        stack = [node_id]
        while stack:
            nid = stack.pop()
            if nid in self.state.completed or nid in self.state.skipped:
                continue
            if any(nid in ups for ups in self.state.strong_links.values()):
                continue
            self.state.skipped.add(nid)
            self.state.ready.discard(nid)
            for succ in self.topo.successors_of(nid):
                stack.append(succ)

    # ------------------------------------------------------------------
    # External blocks (async human_review, etc.)
    # ------------------------------------------------------------------

    def add_external_block(self, node_id: str, tag: str = "default") -> None:
        """Mark ``node_id`` as blocked on an external event ``tag``."""
        self.state.blocked.setdefault(node_id, set()).add(tag)
        self.state.in_progress.discard(node_id)
        self.state.ready.discard(node_id)

    def release_external_block(self, node_id: str, tag: str = "default") -> None:
        tags = self.state.blocked.get(node_id)
        if not tags:
            return
        tags.discard(tag)
        if not tags:
            self.state.blocked.pop(node_id, None)
            if not self._remaining_deps(node_id):
                self.state.ready.add(node_id)
        self._unblocked.set()

    # ------------------------------------------------------------------
    # Staging
    # ------------------------------------------------------------------

    async def stage_node_execution(self) -> str | None:
        """Return the next ready node_id or ``None`` when nothing remains.

        If no ready nodes exist but we have blocked ones, awaits ``_unblocked``
        until a release call wakes us; if there are neither, returns ``None``.
        """
        batch = await self.stage_ready_batch(limit=1)
        return batch[0] if batch else None

    async def stage_ready_batch(self, limit: int | None = None) -> list[str]:
        """Return a batch of currently-ready node ids, moving them to in_progress.

        This is the parallel-scheduling primitive: every node whose strong-link
        dependencies are satisfied is returned together so the executor can run
        them concurrently. Returned ids are sorted for deterministic ordering.

        When no ready nodes exist but blocked ones remain, awaits ``_unblocked``
        until a release call wakes us; if there are neither, returns ``[]``.
        """
        while True:
            if self._cancelled:
                return []
            if self.state.ready:
                ready = sorted(self.state.ready)
                if limit is not None and limit > 0:
                    ready = ready[:limit]
                for nid in ready:
                    self.state.ready.discard(nid)
                    self.state.in_progress.add(nid)
                return ready
            if self.state.blocked:
                self._unblocked.clear()
                try:
                    await asyncio.wait_for(self._unblocked.wait(), timeout=None)
                except asyncio.CancelledError:
                    return []
                continue
            return []

    def complete_node_execution(self, node_id: str) -> None:
        """Mark ``node_id`` completed and promote its newly-ready downstream nodes."""
        self.state.in_progress.discard(node_id)
        self.state.completed.add(node_id)
        # Promote downstream nodes whose strong-link deps are now satisfied.
        # Skip promotion across a pruned edge so a data link crossing a
        # control branch cannot prematurely activate a gated node.
        for down, ups in list(self.state.strong_links.items()):
            if node_id in ups and down not in self.state.completed and down not in self.state.skipped:
                if (node_id, down) in self.state.pruned_edges:
                    continue
                if not self._remaining_deps(down):
                    self.state.ready.add(down)
        self._unblocked.set()

    def fail_node_execution(self, node_id: str) -> None:
        """Mark a node as failed. Leave downstream in a waiting state
        (the runner may reroute via the node's error_handler)."""
        self.state.in_progress.discard(node_id)
        self.state.skipped.add(node_id)
        self._unblocked.set()

    def cancel(self) -> None:
        self._cancelled = True
        self._unblocked.set()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def is_done(self) -> bool:
        if self._cancelled:
            return True
        if self.state.ready or self.state.in_progress or self.state.blocked:
            return False
        return True

    def _remaining_deps(self, node_id: str) -> set[str]:
        """Strong-link deps not yet completed."""
        deps = self.state.strong_links.get(node_id, set())
        return {d for d in deps if d not in self.state.completed and d not in self.state.skipped}

    def detect_cycles(self) -> list[list[str]]:
        """WF-only cycle detection over the currently-staged strong links."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {}
        cycles: list[list[str]] = []

        def dfs(n: str, path: list[str]) -> None:
            color[n] = GRAY
            path.append(n)
            for up in self.state.strong_links.get(n, set()):
                if color.get(up) == GRAY:
                    cycles.append(path[path.index(up):] + [up])
                elif color.get(up, WHITE) == WHITE:
                    dfs(up, path)
            path.pop()
            color[n] = BLACK

        for n in list(self.state.strong_links.keys()):
            if color.get(n, WHITE) == WHITE:
                dfs(n, [])
        return cycles
