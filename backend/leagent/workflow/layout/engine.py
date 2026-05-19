"""Deterministic layered graph layout.

The goal of this module is narrow: given an ordered list of node IDs
and a set of directed edges, assign each node an ``(x, y)`` coordinate
such that the frontend canvas renders a clean left-to-right (or
top-to-bottom) topology with no overlap.

We intentionally avoid a third-party Python port of dagre. Workflow
documents are tiny — the 18 built-in templates peak at ~25 nodes — so a
hand-rolled three-phase algorithm is both simpler and easier to unit
test:

1. **Rank assignment.** Treat the graph as a DAG by ignoring back-edges
   (introduced by ``wait`` nodes that resume their parent branch) and
   run a BFS from the start node so every node gets its longest-path
   depth. Isolated nodes fall back to BFS rank ``0``.
2. **Layer ordering.** Within each rank, order nodes by the *barycenter*
   of their predecessors' positions. This is the classic one-pass sweep
   from the Sugiyama framework; good enough for ≤100 nodes.
3. **Coordinate emission.** Convert ``(rank, index)`` into absolute
   pixel positions using the caller-supplied ``node_size`` + ``gap``.

The output is a plain ``dict[node_id, (x, y)]`` so the caller can build
whatever UI payload it wants.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Iterable


Direction = str  # "LR" or "TB"


@dataclass(frozen=True)
class LayoutOptions:
    """Tunable layout parameters."""

    direction: Direction = "LR"
    node_width: float = 240.0
    node_height: float = 80.0
    rank_gap: float = 120.0
    node_gap: float = 60.0
    origin_x: float = 80.0
    origin_y: float = 80.0


def _build_adjacency(
    node_ids: list[str],
    edges: Iterable[tuple[str, str]],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    succ: dict[str, list[str]] = {nid: [] for nid in node_ids}
    pred: dict[str, list[str]] = {nid: [] for nid in node_ids}
    for src, tgt in edges:
        if src not in succ or tgt not in succ:
            continue
        if tgt not in succ[src]:
            succ[src].append(tgt)
        if src not in pred[tgt]:
            pred[tgt].append(src)
    return succ, pred


def _assign_ranks(
    node_ids: list[str],
    succ: dict[str, list[str]],
    start: str | None,
) -> dict[str, int]:
    """Longest-path rank assignment on the DAG formed by forward edges.

    Back-edges (u -> v where v is already reachable from start before u)
    are skipped so cyclic control structures like ``wait -> process``
    don't flatten the layout into one giant column.
    """
    rank: dict[str, int] = {nid: 0 for nid in node_ids}
    if not node_ids:
        return rank

    # BFS from declared start to determine forward reachability order.
    visited_order: dict[str, int] = {}
    queue: deque[str] = deque()
    roots = [start] if start and start in succ else []
    if not roots:
        # Fall back to nodes with no predecessors.
        pred_count: dict[str, int] = defaultdict(int)
        for src, targets in succ.items():
            for tgt in targets:
                pred_count[tgt] += 1
        roots = [nid for nid in node_ids if pred_count[nid] == 0]
    for r in roots:
        if r not in visited_order:
            visited_order[r] = len(visited_order)
            queue.append(r)
    while queue:
        nid = queue.popleft()
        for tgt in succ[nid]:
            if tgt not in visited_order:
                visited_order[tgt] = len(visited_order)
                queue.append(tgt)

    # Any node the BFS never reached still needs a rank — park them at 0
    # so they render as detached roots.
    for nid in node_ids:
        visited_order.setdefault(nid, len(visited_order))

    # Forward longest-path relaxation in BFS order. An edge is treated
    # as a back-edge iff the target was visited *before* the source.
    ordered = sorted(node_ids, key=lambda n: visited_order[n])
    for nid in ordered:
        for tgt in succ[nid]:
            if visited_order[tgt] <= visited_order[nid]:
                # Back-edge — ignore for ranking.
                continue
            if rank[tgt] < rank[nid] + 1:
                rank[tgt] = rank[nid] + 1
    return rank


def _order_within_ranks(
    ranks: dict[str, int],
    node_ids: list[str],
    pred: dict[str, list[str]],
) -> dict[int, list[str]]:
    """Barycenter ordering to minimise edge crossings.

    Starts with declaration order (stable input ordering is preserved
    for rank 0) then performs two sweeps using the indices produced in
    the previous sweep — this is enough to remove obvious crossings
    without pulling in a full Sugiyama implementation.
    """
    buckets: dict[int, list[str]] = defaultdict(list)
    for nid in node_ids:
        buckets[ranks[nid]].append(nid)

    max_rank = max(buckets.keys()) if buckets else 0

    def _sweep() -> None:
        for r in range(1, max_rank + 1):
            if r not in buckets:
                continue
            prev_positions = {
                nid: idx for idx, nid in enumerate(buckets.get(r - 1, []))
            }
            # Capture the pre-sort index so the tie-breaker is stable even
            # while Python's sort is re-evaluating the key function.
            current_order = {nid: idx for idx, nid in enumerate(buckets[r])}

            def _key(nid: str, _order=current_order, _prev=prev_positions) -> tuple[float, int]:
                ps = [_prev[p] for p in pred[nid] if p in _prev]
                if not ps:
                    return (float("inf"), _order[nid])
                return (sum(ps) / len(ps), _order[nid])

            buckets[r].sort(key=_key)

    _sweep()
    _sweep()
    return buckets


def _emit_coords(
    buckets: dict[int, list[str]],
    opts: LayoutOptions,
) -> dict[str, tuple[float, float]]:
    coords: dict[str, tuple[float, float]] = {}
    if opts.direction == "TB":
        for rank, members in buckets.items():
            total = len(members)
            total_width = total * opts.node_width + max(0, total - 1) * opts.node_gap
            start_x = opts.origin_x - total_width / 2 + opts.node_width / 2
            y = opts.origin_y + rank * (opts.node_height + opts.rank_gap)
            for idx, nid in enumerate(members):
                x = start_x + idx * (opts.node_width + opts.node_gap)
                coords[nid] = (x, y)
        return coords

    # Default: LR.
    for rank, members in buckets.items():
        total = len(members)
        total_height = total * opts.node_height + max(0, total - 1) * opts.node_gap
        start_y = opts.origin_y - total_height / 2 + opts.node_height / 2
        x = opts.origin_x + rank * (opts.node_width + opts.rank_gap)
        for idx, nid in enumerate(members):
            y = start_y + idx * (opts.node_height + opts.node_gap)
            coords[nid] = (x, y)
    return coords


def compute_layout(
    node_ids: list[str],
    edges: Iterable[tuple[str, str]],
    *,
    start: str | None = None,
    options: LayoutOptions | None = None,
) -> dict[str, tuple[float, float]]:
    """Return a deterministic ``(x, y)`` for every node in ``node_ids``.

    Parameters
    ----------
    node_ids:
        Declaration-ordered node IDs. Ordering is used as the tie-breaker
        within a rank before barycenter ordering runs.
    edges:
        Iterable of ``(source, target)`` tuples. Edges that reference
        unknown nodes are silently skipped.
    start:
        Declared entry node (``control.start``). If omitted the first
        node without predecessors is used.
    options:
        :class:`LayoutOptions` overrides. Defaults to LR layout tuned
        for the built-in ReactFlow node size (240x80).
    """
    opts = options or LayoutOptions()
    unique_ids: list[str] = []
    seen: set[str] = set()
    for nid in node_ids:
        if nid in seen:
            continue
        seen.add(nid)
        unique_ids.append(nid)
    if not unique_ids:
        return {}

    edge_list = [(str(s), str(t)) for s, t in edges]
    succ, pred = _build_adjacency(unique_ids, edge_list)
    ranks = _assign_ranks(unique_ids, succ, start)
    buckets = _order_within_ranks(ranks, unique_ids, pred)
    return _emit_coords(buckets, opts)
