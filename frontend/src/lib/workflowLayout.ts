/**
 * Client-side graph layout for the workflow canvas.
 *
 * Mirrors the backend module {@code leagent.workflow.layout} so the
 * "Re-layout" button and canonical documents without stored positions
 * render with the same deterministic topology the backend produces when
 * a template is first applied.
 *
 * The implementation delegates the actual layered placement to
 * {@link https://github.com/dagrejs/dagre dagre} — it's ~25KB gzipped,
 * has no React peer dep, and its output plays nicely with
 * {@link https://reactflow.dev @xyflow/react}.
 */

import dagre from 'dagre';
import type { FlowEdge, FlowNode, FlowNodeData } from '@/stores/flow';

/** Layout direction mirroring dagre's rankdir. */
export type LayoutDirection = 'LR' | 'TB';

export interface LayoutOptions {
  direction?: LayoutDirection;
  nodeWidth?: number;
  nodeHeight?: number;
  /** Gap between adjacent ranks. Dagre calls this ``ranksep``. */
  rankSep?: number;
  /** Gap between two sibling nodes within a rank. Dagre's ``nodesep``. */
  nodeSep?: number;
  /** Distance between the graph origin and the top/left edge. */
  padding?: number;
}

const DEFAULT_OPTIONS: Required<LayoutOptions> = {
  direction: 'LR',
  nodeWidth: 240,
  nodeHeight: 80,
  rankSep: 120,
  nodeSep: 60,
  padding: 40,
};

interface EngineNodeAction {
  id?: string;
  label?: string;
  next?: string;
}

interface EngineNodeControl {
  next?: string;
  error_handler?: string;
  else_node?: string;
  else?: string;
  on_reject?: string;
  conditions?: Array<{ if?: unknown; if_expr?: unknown; then?: string }>;
  branches?: Array<{
    id?: string;
    nodes?: Array<string | { id?: string }>;
  }>;
}

/**
 * A node spec from the canonical workflow document (``nodes`` dict entry
 * flattened with its id). Control flow lives in ``control``; display
 * metadata in ``meta``.
 */
export interface EngineNode {
  id?: string;
  class_type?: string;
  inputs?: Record<string, unknown> | string[];
  control?: EngineNodeControl;
  meta?: {
    name?: string;
    description?: string;
    actions?: EngineNodeAction[];
  };
}

export interface WorkflowLayoutEdge {
  id: string;
  source: string;
  target: string;
  kind: 'next' | 'error' | 'condition' | 'else' | 'branch' | 'sequence' | 'action' | 'reject';
  label?: string;
}

type ConditionEntry = { if?: unknown; if_expr?: unknown; then?: string };

/** Pretty-print a condition expression for the edge label. */
function conditionLabel(cond: ConditionEntry | undefined): string {
  if (!cond) return '';
  const expr = cond.if ?? cond.if_expr;
  if (typeof expr === 'string') {
    let text = expr.trim();
    if (text.startsWith('${') && text.endsWith('}')) {
      text = text.slice(2, -1);
    }
    return text.slice(0, 40);
  }
  if (expr && typeof expr === 'object') {
    const e = expr as { left?: unknown; operator?: unknown; right?: unknown };
    return `${String(e.left ?? '')} ${String(e.operator ?? 'eq')} ${String(e.right ?? '')}`.slice(0, 40);
  }
  return '';
}

function resolveControl(node: EngineNode): EngineNodeControl {
  return node.control && typeof node.control === 'object' ? node.control : {};
}

function resolveActions(node: EngineNode): EngineNodeAction[] {
  return Array.isArray(node.meta?.actions) ? node.meta.actions : [];
}

/**
 * Walk every node and yield a :ref:`WorkflowLayoutEdge` for each
 * declared exit. Mirrors :func:`extract_edges` on the backend so both
 * sides agree on the graph shape.
 */
export function extractWorkflowEdges(engineNodes: EngineNode[]): WorkflowLayoutEdge[] {
  const ids = new Set<string>();
  for (const n of engineNodes) {
    if (typeof n.id === 'string' && n.id) ids.add(n.id);
  }

  const edges: WorkflowLayoutEdge[] = [];
  const seen = new Set<string>();

  const push = (source: string, target: string, kind: WorkflowLayoutEdge['kind'], label?: string) => {
    if (!source || !target || !ids.has(source) || !ids.has(target)) return;
    const key = `${source}->${target}::${kind}`;
    if (seen.has(key)) return;
    seen.add(key);
    const token = (label || kind).replace(/\s+/g, '_');
    edges.push({ id: `e-${source}-${target}-${token}`, source, target, kind, label });
  };

  for (const node of engineNodes) {
    const src = typeof node.id === 'string' ? node.id : '';
    if (!src) continue;
    const control = resolveControl(node);

    if (typeof control.next === 'string' && control.next) {
      push(src, control.next, 'next');
    }
    if (typeof control.error_handler === 'string' && control.error_handler) {
      push(src, control.error_handler, 'error', 'on_error');
    }

    if (Array.isArray(control.conditions)) {
      for (const cond of control.conditions) {
        if (cond && typeof cond === 'object' && typeof cond.then === 'string') {
          push(src, cond.then, 'condition', conditionLabel(cond));
        }
      }
    }
    const elseTarget = typeof control.else_node === 'string' ? control.else_node : control.else;
    if (typeof elseTarget === 'string' && elseTarget) {
      push(src, elseTarget, 'else', 'else');
    }

    if (Array.isArray(control.branches)) {
      for (const branch of control.branches) {
        if (!branch) continue;
        const branchIds: string[] = [];
        for (const ref of branch.nodes ?? []) {
          if (typeof ref === 'string') branchIds.push(ref);
          else if (ref && typeof ref.id === 'string') branchIds.push(ref.id);
        }
        if (branchIds.length === 0) continue;
        push(src, branchIds[0]!, 'branch', branch.id);
        for (let i = 0; i < branchIds.length - 1; i += 1) {
          push(branchIds[i]!, branchIds[i + 1]!, 'sequence');
        }
      }
    }

    for (const action of resolveActions(node)) {
      if (action && typeof action.next === 'string') {
        const label = typeof action.label === 'string' ? action.label : action.id;
        push(src, action.next, 'action', label);
      }
    }

    if (typeof control.on_reject === 'string' && control.on_reject) {
      push(src, control.on_reject, 'reject', 'rejected');
    }
  }

  return edges;
}

export interface LayoutResult {
  nodes: FlowNode[];
  edges: FlowEdge[];
}

/**
 * Run dagre over ``nodes`` and return a new array with updated
 * positions. Edges are returned unchanged so the caller can feed them
 * straight back into ReactFlow state.
 */
export function layoutNodes(
  nodes: FlowNode[],
  edges: FlowEdge[],
  options: LayoutOptions = {},
): LayoutResult {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  if (nodes.length === 0) return { nodes: [], edges };

  const g = new dagre.graphlib.Graph();
  g.setGraph({
    rankdir: opts.direction,
    ranksep: opts.rankSep,
    nodesep: opts.nodeSep,
    marginx: opts.padding,
    marginy: opts.padding,
  });
  g.setDefaultEdgeLabel(() => ({}));

  for (const node of nodes) {
    g.setNode(node.id, { width: opts.nodeWidth, height: opts.nodeHeight });
  }
  const nodeIds = new Set(nodes.map((n) => n.id));
  for (const edge of edges) {
    if (nodeIds.has(edge.source) && nodeIds.has(edge.target)) {
      g.setEdge(edge.source, edge.target);
    }
  }

  dagre.layout(g);

  const positioned: FlowNode[] = nodes.map((node) => {
    const pos = g.node(node.id);
    if (!pos || typeof pos.x !== 'number' || typeof pos.y !== 'number') {
      return node;
    }
    // Dagre returns the node *center* — ReactFlow expects the top-left.
    return {
      ...node,
      position: {
        x: pos.x - opts.nodeWidth / 2,
        y: pos.y - opts.nodeHeight / 2,
      },
    };
  });

  return { nodes: positioned, edges };
}

/** Category mapping mirrors the backend ``_TYPE_TO_CATEGORY`` table. */
const TYPE_TO_CATEGORY: Record<string, string> = {
  start: 'trigger',
  end: 'trigger',
  tool_call: 'web',
  llm_call: 'llm',
  condition: 'condition',
  parallel: 'loop',
  human_review: 'notification',
  error_handler: 'transform',
  transform: 'transform',
  subworkflow: 'transform',
  wait: 'delay',
  delay: 'delay',
  webhook: 'webhook',
};

const CLASS_TO_TYPE: Record<string, string> = {
  StartNode: 'start',
  EndNode: 'end',
  ToolCallNode: 'tool_call',
  LLMCallNode: 'llm_call',
  ConditionNode: 'condition',
  ParallelNode: 'parallel',
  HumanReviewNode: 'human_review',
  ErrorHandlerNode: 'error_handler',
  TransformNode: 'transform',
  SubworkflowNode: 'subworkflow',
  WaitNode: 'wait',
};

function nodeType(node: EngineNode): string {
  if (typeof node.class_type === 'string') {
    const mapped = CLASS_TO_TYPE[node.class_type];
    if (mapped) return mapped;
  }
  return 'tool_call';
}

function nodeLabel(id: string, node: EngineNode): string {
  const name = node.meta?.name;
  if (typeof name === 'string' && name.trim()) return name;
  return id;
}

function nodeParameters(node: EngineNode): Record<string, unknown> {
  if (node.inputs && typeof node.inputs === 'object' && !Array.isArray(node.inputs)) {
    const inputs = node.inputs as Record<string, unknown>;
    const params = inputs.params;
    if (params && typeof params === 'object' && !Array.isArray(params)) {
      return params as Record<string, unknown>;
    }
    return inputs;
  }
  return {};
}

/**
 * Convert a raw engine-shaped node list into ReactFlow nodes with a
 * dagre-computed layout and a complete edge set. This is the shared
 * fallback used by {@link parseStoredFlowData} and by the canvas
 * "Re-layout" action.
 */
export function buildLayoutedFlow(
  engineNodes: EngineNode[],
  options: LayoutOptions = {},
): LayoutResult {
  const baseNodes: FlowNode[] = engineNodes.map((node, i) => {
    const id = typeof node.id === 'string' && node.id ? node.id : `node-${i}`;
    const type = nodeType(node);
    const inputs = node.inputs;
    const tool =
      inputs && typeof inputs === 'object' && !Array.isArray(inputs)
        ? (inputs as Record<string, unknown>).tool
        : undefined;
    const data: FlowNodeData = {
      label: nodeLabel(id, node),
      icon: type,
      category: TYPE_TO_CATEGORY[type] ?? 'transform',
      description:
        typeof tool === 'string'
          ? tool
          : typeof node.meta?.description === 'string'
            ? node.meta.description
            : undefined,
      parameters: nodeParameters(node),
      inputs: ['input'],
      outputs: ['output'],
    };
    return {
      id,
      type: 'generic',
      position: { x: 0, y: 0 },
      data,
    };
  });

  const extracted = extractWorkflowEdges(engineNodes);
  const flowEdges: FlowEdge[] = extracted.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    type: 'default',
    label: e.label,
    data: { kind: e.kind },
  }));

  return layoutNodes(baseNodes, flowEdges, options);
}
