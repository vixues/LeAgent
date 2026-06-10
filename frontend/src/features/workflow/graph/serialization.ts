/**
 * Serialize the React Flow editor graph to the backend's canonical workflow
 * document and back.
 *
 * The backend `submit_prompt` path runs `load(json.loads(flow.data))`, which
 * requires the canonical shape: `nodes` is a `dict[node_id, {class_type,
 * inputs, meta, control}]` and data dependencies are expressed as input link
 * refs `[upstream_node_id, slot_index]` (see
 * `leagent/workflow/io/loader.py` and `engine/graph.py`). We therefore emit
 * that exact shape so editor-authored flows are directly runnable, and attach
 * a sibling `ui` block (editor nodes/edges/viewport) so the editor can reload
 * the exact visual layout.
 */

import type { Edge, Node, Viewport } from '@xyflow/react';

import type { NodeDefinition } from './objectInfo';

export interface WorkflowNodeData extends Record<string, unknown> {
  /** Backend node id used as `class_type` on serialize. */
  nodeType: string;
  label: string;
  category: string;
  description?: string;
  /** Inline widget values keyed by input slot id. */
  values?: Record<string, unknown>;
  /** ComfyUI-style execution mode: muted (skip) or bypassed (pass-through). */
  mode?: 'mute' | 'bypass';
}

export type EditorNode = Node<WorkflowNodeData>;
export type EditorEdge = Edge;

export interface CanonicalDocument {
  id: string;
  name: string;
  description: string;
  inputs: unknown[];
  outputs: unknown[];
  metadata: Record<string, unknown>;
  nodes: Record<string, CanonicalNode>;
  control: { start?: string; edges: CanonicalEdge[] };
  ui: {
    nodes: EditorNode[];
    edges: EditorEdge[];
    viewport?: Viewport;
  };
}

interface CanonicalNode {
  class_type: string;
  inputs: Record<string, unknown>;
  meta: { position: { x: number; y: number }; title?: string; mode?: string };
}

interface CanonicalEdge {
  source: string;
  target: string;
  source_slot: number;
  target_slot: number;
}

function outputSlotIndex(def: NodeDefinition | undefined, handle: string | null | undefined): number {
  if (!def || def.outputs.length === 0) return 0;
  if (!handle) return 0;
  const idx = def.outputs.findIndex((o) => o.id === handle);
  return idx >= 0 ? idx : 0;
}

function inputSlotIndex(def: NodeDefinition | undefined, handle: string | null | undefined): number {
  if (!def || def.inputs.length === 0) return 0;
  if (!handle) return 0;
  const idx = def.inputs.findIndex((i) => i.id === handle);
  return idx >= 0 ? idx : 0;
}

export interface ToCanonicalParams {
  id: string;
  name: string;
  description?: string;
  nodes: EditorNode[];
  edges: EditorEdge[];
  viewport?: Viewport;
  definitions: Record<string, NodeDefinition>;
  metadata?: Record<string, unknown>;
  /** Declared workflow inputs (authored in the I/O config panel). */
  inputs?: unknown[];
  /** Declared workflow outputs (authored in the I/O config panel). */
  outputs?: unknown[];
}

/** UI-only node types that never serialize into the executable graph. */
const UI_ONLY_TYPES = new Set(['reroute', 'group']);

function isUiOnly(node: EditorNode): boolean {
  return UI_ONLY_TYPES.has(node.type ?? '');
}

/**
 * Resolve an edge endpoint upstream through any reroute chain, returning the
 * real producing node + handle (ComfyUI flattens reroutes the same way).
 */
function resolveUpstream(
  sourceId: string,
  sourceHandle: string | null | undefined,
  nodesById: Map<string, EditorNode>,
  edges: EditorEdge[],
): { source: string; sourceHandle: string | null | undefined } | null {
  let id = sourceId;
  let handle = sourceHandle;
  const seen = new Set<string>();
  while (nodesById.get(id)?.type === 'reroute') {
    if (seen.has(id)) return null; // cycle guard
    seen.add(id);
    const incoming = edges.find((e) => e.target === id);
    if (!incoming) return null; // dangling reroute
    id = incoming.source;
    handle = incoming.sourceHandle;
  }
  return { source: id, sourceHandle: handle };
}

/** Build the canonical workflow document (executable + `ui`) from the editor. */
export function toCanonicalDocument(params: ToCanonicalParams): CanonicalDocument {
  const { nodes, edges, definitions } = params;
  const nodesById = new Map(nodes.map((n) => [n.id, n]));

  // Flatten edges: drop those ending at UI-only nodes, rewire those whose
  // source chain passes through reroutes to the true upstream producer.
  const flatEdges: EditorEdge[] = [];
  for (const edge of edges) {
    const targetNode = nodesById.get(edge.target);
    if (!targetNode || isUiOnly(targetNode)) continue;
    const resolved = resolveUpstream(edge.source, edge.sourceHandle, nodesById, edges);
    if (!resolved) continue;
    const sourceNode = nodesById.get(resolved.source);
    if (!sourceNode || isUiOnly(sourceNode)) continue;
    flatEdges.push({ ...edge, source: resolved.source, sourceHandle: resolved.sourceHandle });
  }

  const workflowNodes = nodes.filter((n) => !isUiOnly(n));

  const nodeSpecs: Record<string, CanonicalNode> = {};
  for (const node of workflowNodes) {
    const data = node.data;
    const classType = data.nodeType || (node.type ?? '');
    const def = definitions[classType];
    const inputs: Record<string, unknown> = {};

    // 1. Literal widget values for inputs that are not driven by a link.
    const values = data.values ?? {};
    for (const [key, value] of Object.entries(values)) {
      if (value !== undefined && value !== null && value !== '') {
        inputs[key] = value;
      }
    }

    // 2. Link refs from incoming (flattened) edges override literal widget values.
    for (const edge of flatEdges) {
      if (edge.target !== node.id) continue;
      const targetHandle = edge.targetHandle ?? def?.inputs[0]?.id ?? 'input';
      const sourceDef = definitions[nodeFor(nodes, edge.source)?.data.nodeType ?? ''];
      const slot = outputSlotIndex(sourceDef, edge.sourceHandle);
      inputs[targetHandle] = [edge.source, slot];
    }

    nodeSpecs[node.id] = {
      class_type: classType,
      inputs,
      meta: {
        position: { x: Math.round(node.position.x), y: Math.round(node.position.y) },
        title: data.label,
        ...(data.mode ? { mode: data.mode } : {}),
      },
    };
  }

  const canonicalEdges: CanonicalEdge[] = flatEdges.map((edge) => {
    const sourceDef = definitions[nodeFor(nodes, edge.source)?.data.nodeType ?? ''];
    const targetDef = definitions[nodeFor(nodes, edge.target)?.data.nodeType ?? ''];
    return {
      source: edge.source,
      target: edge.target,
      source_slot: outputSlotIndex(sourceDef, edge.sourceHandle),
      target_slot: inputSlotIndex(targetDef, edge.targetHandle),
    };
  });

  // Prefer an explicit Start node; else the first node with no incoming edges.
  const targets = new Set(flatEdges.map((e) => e.target));
  const startNode =
    workflowNodes.find((n) => n.data.nodeType === 'StartNode') ??
    workflowNodes.find((n) => !targets.has(n.id));

  return {
    id: params.id,
    name: params.name,
    description: params.description ?? '',
    inputs: params.inputs ?? [],
    outputs: params.outputs ?? [],
    metadata: { ...(params.metadata ?? {}), editor: 'react-flow-graph' },
    nodes: nodeSpecs,
    control: { start: startNode?.id, edges: canonicalEdges },
    ui: { nodes, edges, viewport: params.viewport },
  };
}

function nodeFor(nodes: EditorNode[], id: string): EditorNode | undefined {
  return nodes.find((n) => n.id === id);
}

/**
 * Reconstruct editor nodes/edges from a stored document. Prefers the `ui`
 * block (exact layout); otherwise rebuilds a minimal editor view from the
 * canonical `nodes` dict so legacy/template documents still open.
 */
export interface StoredDocumentResult {
  nodes: EditorNode[];
  edges: EditorEdge[];
  viewport?: Viewport;
  description?: string;
  metadata?: Record<string, unknown>;
  /** Declared workflow I/O carried through round-trips. */
  inputs: unknown[];
  outputs: unknown[];
}

export function fromStoredDocument(
  raw: unknown,
  definitions: Record<string, NodeDefinition>,
): StoredDocumentResult {
  const obj = (typeof raw === 'string' ? safeParse(raw) : raw) as
    | Record<string, unknown>
    | null;
  if (!obj || typeof obj !== 'object') return { nodes: [], edges: [], inputs: [], outputs: [] };

  const shared = {
    description: typeof obj.description === 'string' ? obj.description : undefined,
    metadata:
      obj.metadata && typeof obj.metadata === 'object'
        ? (obj.metadata as Record<string, unknown>)
        : undefined,
    inputs: Array.isArray(obj.inputs) ? obj.inputs : [],
    outputs: Array.isArray(obj.outputs) ? obj.outputs : [],
  };

  const ui = obj.ui as CanonicalDocument['ui'] | undefined;
  if (ui && Array.isArray(ui.nodes) && ui.nodes.length > 0) {
    return {
      ...shared,
      nodes: ui.nodes as EditorNode[],
      edges: Array.isArray(ui.edges) ? (ui.edges as EditorEdge[]) : [],
      viewport: ui.viewport,
    };
  }

  // Rebuild from the canonical nodes dict.
  const rawNodes = obj.nodes;
  if (rawNodes && typeof rawNodes === 'object' && !Array.isArray(rawNodes)) {
    return {
      ...shared,
      ...rebuildFromCanonical(rawNodes as Record<string, CanonicalNode>, definitions),
    };
  }
  return { nodes: [], edges: [], ...shared };
}

function rebuildFromCanonical(
  nodesDict: Record<string, CanonicalNode>,
  definitions: Record<string, NodeDefinition>,
): { nodes: EditorNode[]; edges: EditorEdge[] } {
  const nodes: EditorNode[] = [];
  const edges: EditorEdge[] = [];
  let i = 0;
  for (const [id, spec] of Object.entries(nodesDict)) {
    const classType = spec.class_type;
    const def = definitions[classType];
    const values: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(spec.inputs ?? {})) {
      const isLink = Array.isArray(value) && value.length === 2 && typeof value[0] === 'string';
      if (isLink) {
        const [sourceId, slot] = value as [string, number];
        const sourceDef = definitions[nodesDict[sourceId]?.class_type ?? ''];
        edges.push({
          id: `edge-${sourceId}-${id}-${key}`,
          source: sourceId,
          target: id,
          sourceHandle: sourceDef?.outputs[slot]?.id,
          targetHandle: key,
          type: 'workflow',
        });
      } else {
        values[key] = value;
      }
    }
    const pos = spec.meta?.position ?? { x: (i % 4) * 280, y: Math.floor(i / 4) * 200 };
    const mode = spec.meta?.mode;
    nodes.push({
      id,
      type: 'workflow',
      position: pos,
      data: {
        nodeType: classType,
        label: spec.meta?.title || def?.displayName || classType,
        category: def?.category ?? 'workflow',
        description: def?.description,
        values,
        ...(mode === 'mute' || mode === 'bypass' ? { mode } : {}),
      },
    });
    i += 1;
  }
  return { nodes, edges };
}

function safeParse(text: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(text);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
}
