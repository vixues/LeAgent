import type { FlowEdge, FlowNode } from '@/stores/flow';
import { buildLayoutedFlow, layoutNodes, type EngineNode } from './workflowLayout';

/**
 * Convert the ``Flow.data`` JSON payload stored by the backend into
 * ReactFlow-ready ``nodes`` and ``edges``.
 *
 * Two storage shapes are supported (both canonical-document based):
 *
 * 1. **Pre-laid-out ``ui`` block**: the canonical workflow document
 *    carries a sibling ``ui`` block with ``nodes`` (positions +
 *    display data) and ``edges`` already pre-computed. Used verbatim.
 * 2. **Bare canonical document**: ``nodes`` is a dict keyed by node
 *    id (each spec has ``class_type`` / ``control`` / ``meta``). The
 *    graph is laid out client-side with dagre.
 */
export function parseStoredFlowData(
  data: string | Record<string, unknown> | null | undefined,
): {
  nodes: FlowNode[];
  edges: FlowEdge[];
} {
  let obj: Record<string, unknown>;
  if (typeof data === 'object' && data !== null && !Array.isArray(data)) {
    obj = data as Record<string, unknown>;
  } else if (typeof data === 'string' && data.trim()) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(data);
    } catch {
      return { nodes: [], edges: [] };
    }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { nodes: [], edges: [] };
    }
    obj = parsed as Record<string, unknown>;
  } else {
    return { nodes: [], edges: [] };
  }

  // 1. Pre-laid-out ``ui`` block — fast path.
  const ui = obj.ui;
  if (ui && typeof ui === 'object') {
    const uiObj = ui as { nodes?: unknown; edges?: unknown };
    if (Array.isArray(uiObj.nodes) && uiObj.nodes.length > 0) {
      return {
        nodes: uiObj.nodes as FlowNode[],
        edges: Array.isArray(uiObj.edges) ? (uiObj.edges as FlowEdge[]) : [],
      };
    }
  }

  // 2. Bare canonical document — `nodes` is a dict keyed by node id.
  const nodesRaw = obj.nodes;
  if (nodesRaw && typeof nodesRaw === 'object' && !Array.isArray(nodesRaw)) {
    const engineNodes: EngineNode[] = Object.entries(
      nodesRaw as Record<string, Record<string, unknown>>,
    ).map(([id, spec]) => ({ ...(spec as EngineNode), id }));
    if (engineNodes.length > 0) {
      return buildLayoutedFlow(engineNodes);
    }
  }

  return { nodes: [], edges: [] };
}

/**
 * Same graph topology as {@link parseStoredFlowData}, but re-run dagre in **LR**
 * so the chat mini preview reads left-to-right. Preserves `data` / edge ids;
 * discards editor `ui` / saved x,y so layout matches the narrow strip viewport.
 */
export function parseStoredFlowDataForChatPreview(
  data: string | Record<string, unknown> | null | undefined,
): { nodes: FlowNode[]; edges: FlowEdge[] } {
  const base = parseStoredFlowData(data);
  if (base.nodes.length === 0) return base;

  const stripped: FlowNode[] = base.nodes.map((node) => ({
    ...node,
    measured: undefined,
    position: { x: 0, y: 0 },
  }));

  return layoutNodes(stripped, base.edges, {
    direction: 'LR',
    nodeWidth: 220,
    nodeHeight: 88,
    rankSep: 72,
    nodeSep: 24,
    padding: 36,
  });
}
