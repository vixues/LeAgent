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
import { CONTROL_EDGE_COLOR } from './connectionUtils';
import { CANVAS_ASSET_NODE_TYPE, canvasAssetSourceHandle, type CanvasAssetNodeData, isCanvasAssetNode } from '../components/canvasAsset';
import {
  canvasAssetToCanonical,
  canonicalToCanvasAsset,
  canvasAssetKindFromCanonical,
} from '../components/canvasAssetSerialize';

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

export type WorkflowEditorNode = Node<WorkflowNodeData>;
/** Workflow nodes plus canvas-dropped asset sources (LoadImage / ScriptNode / LoadMesh3D). */
export type EditorNode = WorkflowEditorNode | Node<CanvasAssetNodeData>;
export type EditorEdge = Edge;

/** Backend ``class_type`` for a workflow editor node; empty for canvas assets. */
export function workflowClassType(node: EditorNode | undefined | null): string {
  if (!node || isCanvasAssetNode(node)) return '';
  return node.data.nodeType ?? '';
}

export function isWorkflowEditorNode(node: EditorNode): node is WorkflowEditorNode {
  return !isCanvasAssetNode(node);
}

export interface CanonicalDocument {
  id: string;
  name: string;
  description: string;
  inputs: unknown[];
  outputs: unknown[];
  metadata: Record<string, unknown>;
  nodes: Record<string, CanonicalNode>;
  control: { start?: string; end?: string; edges: CanonicalEdge[] };
  ui: {
    nodes: EditorNode[];
    edges: EditorEdge[];
    viewport?: Viewport;
  };
}

interface CanonicalNodeControl {
  next?: string;
  error_handler?: string;
  conditions?: Array<{ then?: string; then_node?: string }>;
  else_node?: string;
  else?: string;
  on_reject?: string;
  retry_node?: string;
  exhausted_node?: string;
  branches?: Array<{ id?: string; nodes?: string[] }>;
}

interface CanonicalNode {
  class_type: string;
  inputs: Record<string, unknown>;
  meta: { position?: { x: number; y: number }; title?: string; name?: string; mode?: string };
  control?: CanonicalNodeControl;
}

const BOUNDARY_START_ID = 'start';
const BOUNDARY_END_ID = 'end';

function findNodeIdByClass(
  specs: Record<string, CanonicalNode>,
  classType: string,
): string | undefined {
  for (const [id, spec] of Object.entries(specs)) {
    if (spec.class_type === classType) return id;
  }
  return undefined;
}

/**
 * Inject Start/End boundary nodes and auto-chain ``control.next`` so hand-drawn
 * graphs validate and execute without manual control wiring.
 */
export function finalizeExecutableGraph(
  nodeSpecs: Record<string, CanonicalNode>,
  control: { start?: string; end?: string; edges: CanonicalEdge[] },
  workOrder: string[],
): { nodes: Record<string, CanonicalNode>; control: { start: string; end: string; edges: CanonicalEdge[] } } {
  const nodes: Record<string, CanonicalNode> = {};
  for (const [id, spec] of Object.entries(nodeSpecs)) {
    nodes[id] = {
      ...spec,
      inputs: { ...spec.inputs },
      meta: { ...spec.meta },
      ...(spec.control ? { control: { ...spec.control } } : {}),
    };
  }

  const hasControlRouting = (control: CanonicalNodeControl | undefined): boolean => {
    if (!control) return false;
    return Boolean(
      control.next ||
        control.error_handler ||
        control.else_node ||
        control.on_reject ||
        control.retry_node ||
        control.exhausted_node ||
        (control.conditions && control.conditions.length > 0) ||
        (control.branches && control.branches.length > 0),
    );
  };

  let startId = findNodeIdByClass(nodes, 'StartNode') ?? control.start;
  if (!startId || !nodes[startId]) {
    startId = BOUNDARY_START_ID;
    if (!nodes[startId]) {
      nodes[startId] = {
        class_type: 'StartNode',
        inputs: {},
        meta: { name: 'Start' },
      };
    }
  }

  let endId = findNodeIdByClass(nodes, 'EndNode') ?? control.end;
  if (!endId || !nodes[endId]) {
    endId = BOUNDARY_END_ID;
    if (!nodes[endId]) {
      nodes[endId] = {
        class_type: 'EndNode',
        inputs: {},
        meta: { name: 'End' },
      };
    }
  }

  const boundaryIds = new Set([startId, endId]);
  const workIds = workOrder.filter((id) => nodes[id] && !boundaryIds.has(id));
  if (workIds.length === 0) {
    for (const id of Object.keys(nodes)) {
      if (!boundaryIds.has(id)) workIds.push(id);
    }
  }

  const startSpec = nodes[startId]!;
  if (!startSpec.control) startSpec.control = {};
  if (!startSpec.control.next && workIds.length > 0) {
    startSpec.control.next = workIds[0];
  } else if (!startSpec.control.next && workIds.length === 0) {
    startSpec.control.next = endId;
  }

  for (let i = 0; i < workIds.length; i++) {
    const id = workIds[i]!;
    const spec = nodes[id]!;
    if (hasControlRouting(spec.control)) continue;
    if (!spec.control) spec.control = {};
    if (!spec.control.next) {
      spec.control.next = i < workIds.length - 1 ? workIds[i + 1]! : endId;
    }
  }

  return {
    nodes,
    control: {
      start: startId,
      end: endId,
      edges: control.edges,
    },
  };
}

function edgePairKey(source: string, target: string): string {
  return `${source}|${target}`;
}

/** Build editor edges for declared control-flow exits (``control.next``, branches, …). */
function extractControlFlowEdges(
  nodesDict: Record<string, CanonicalNode>,
  definitions: Record<string, NodeDefinition>,
): EditorEdge[] {
  const knownIds = new Set(Object.keys(nodesDict));
  const edges: EditorEdge[] = [];
  const seen = new Set<string>();

  const add = (source: string, target: string, kind: string) => {
    if (!source || !target || !knownIds.has(target)) return;
    const key = edgePairKey(source, target);
    if (seen.has(key)) return;
    seen.add(key);
    const sourceDef = definitions[nodesDict[source]?.class_type ?? ''];
    const targetDef = definitions[nodesDict[target]?.class_type ?? ''];
    edges.push({
      id: `edge-${source}-${target}-${kind}`,
      source,
      target,
      sourceHandle: sourceDef?.outputs[0]?.id,
      targetHandle: targetDef?.inputs[0]?.id,
      type: 'workflow',
      data: { kind: 'control', controlKind: kind, color: CONTROL_EDGE_COLOR },
    });
  };

  for (const [nodeId, spec] of Object.entries(nodesDict)) {
    const control = spec.control ?? {};
    if (typeof control.next === 'string') add(nodeId, control.next, 'next');
    if (typeof control.error_handler === 'string') add(nodeId, control.error_handler, 'error');

    for (const cond of control.conditions ?? []) {
      const target = cond.then_node ?? cond.then;
      if (typeof target === 'string') add(nodeId, target, 'condition');
    }

    const elseTarget = control.else_node ?? control.else;
    if (typeof elseTarget === 'string') add(nodeId, elseTarget, 'else');
    if (typeof control.on_reject === 'string') add(nodeId, control.on_reject, 'reject');
    if (typeof control.retry_node === 'string') add(nodeId, control.retry_node, 'retry');
    if (typeof control.exhausted_node === 'string') add(nodeId, control.exhausted_node, 'exhausted');

    for (const branch of control.branches ?? []) {
      const branchNodes = branch.nodes ?? [];
      if (branchNodes.length > 0 && typeof branchNodes[0] === 'string') {
        add(nodeId, branchNodes[0], 'branch');
        for (let i = 0; i < branchNodes.length - 1; i++) {
          const a = branchNodes[i];
          const b = branchNodes[i + 1];
          if (typeof a === 'string' && typeof b === 'string') add(a, b, 'sequence');
        }
      }
    }
  }

  return edges;
}

const CONTROL_EDGE_SUFFIXES = new Set([
  'next',
  'error',
  'condition',
  'else',
  'reject',
  'branch',
  'sequence',
  'retry',
  'exhausted',
]);

function controlKindFromEdge(edge: EditorEdge): string | null {
  const data = edge.data;
  if (data && typeof data === 'object' && 'controlKind' in data) {
    const ck = (data as { controlKind?: unknown }).controlKind;
    if (typeof ck === 'string' && CONTROL_EDGE_SUFFIXES.has(ck)) return ck;
  }
  const id = edge.id ?? '';
  const suffix = id.includes('-') ? id.slice(id.lastIndexOf('-') + 1) : '';
  return CONTROL_EDGE_SUFFIXES.has(suffix) ? suffix : null;
}

/** Control-flow edges (pass/fail/retry) must not become ``[upstream, slot]`` input links. */
function isControlFlowEdge(edge: EditorEdge): boolean {
  const data = edge.data;
  if (data && typeof data === 'object' && (data as { kind?: string }).kind === 'control') {
    return true;
  }
  return controlKindFromEdge(edge) !== null;
}

/** Dedupe key — control + data edges may share the same node pair (e.g. gate asset → upscale). */
function edgeDedupeKey(edge: EditorEdge): string {
  if (isControlFlowEdge(edge)) {
    return `${edge.source}|${edge.target}|ctl:${controlKindFromEdge(edge) ?? 'control'}`;
  }
  return `${edge.source}|${edge.target}|data:${edge.sourceHandle ?? ''}:${edge.targetHandle ?? ''}`;
}

/** Reconstruct per-node ``control`` from editor control-flow edges on save. */
function buildNodeControlFromEditorEdges(
  nodeId: string,
  edges: EditorEdge[],
): CanonicalNodeControl | undefined {
  const control: CanonicalNodeControl = {};
  let has = false;

  for (const edge of edges) {
    if (edge.source !== nodeId || !edge.target) continue;
    const kind = controlKindFromEdge(edge);
    if (!kind) continue;
    switch (kind) {
      case 'next':
      case 'sequence':
        control.next = edge.target;
        has = true;
        break;
      case 'error':
        control.error_handler = edge.target;
        has = true;
        break;
      case 'condition':
        control.conditions = [...(control.conditions ?? []), { then_node: edge.target }];
        has = true;
        break;
      case 'else':
        control.else_node = edge.target;
        has = true;
        break;
      case 'reject':
        control.on_reject = edge.target;
        has = true;
        break;
      case 'retry':
        control.retry_node = edge.target;
        has = true;
        break;
      case 'exhausted':
        control.exhausted_node = edge.target;
        has = true;
        break;
      default:
        break;
    }
  }

  return has ? control : undefined;
}

/** Convert backend layout ``ui.edges`` (preview-shaped) into typed editor edges. */
function layoutUiEdgesToEditorEdges(
  uiEdges: unknown[],
  nodesDict: Record<string, CanonicalNode>,
  definitions: Record<string, NodeDefinition>,
): EditorEdge[] {
  const edges: EditorEdge[] = [];
  const seen = new Set<string>();

  for (const raw of uiEdges) {
    if (!raw || typeof raw !== 'object') continue;
    const edge = raw as { id?: string; source?: string; target?: string; data?: { kind?: string } };
    if (typeof edge.source !== 'string' || typeof edge.target !== 'string') continue;
    if (!nodesDict[edge.source] || !nodesDict[edge.target]) continue;

    const key = edgePairKey(edge.source, edge.target);
    if (seen.has(key)) continue;
    seen.add(key);

    const sourceDef = definitions[nodesDict[edge.source]?.class_type ?? ''];
    const targetDef = definitions[nodesDict[edge.target]?.class_type ?? ''];
    const kind = typeof edge.data?.kind === 'string' ? edge.data.kind : 'layout';
    edges.push({
      id: edge.id || `edge-${edge.source}-${edge.target}-${kind}`,
      source: edge.source,
      target: edge.target,
      sourceHandle: sourceDef?.outputs[0]?.id,
      targetHandle: targetDef?.inputs[0]?.id,
      type: 'workflow',
      data: { kind, color: CONTROL_EDGE_COLOR },
    });
  }

  return edges;
}

/** Prefer explicit data-link edges; fill gaps with control/layout edges. */
function mergeEditorEdges(primary: EditorEdge[], secondary: EditorEdge[]): EditorEdge[] {
  const keys = new Set(primary.map((e) => edgeDedupeKey(e)));
  const merged = [...primary];
  for (const edge of secondary) {
    const key = edgeDedupeKey(edge);
    if (!keys.has(key)) {
      keys.add(key);
      merged.push(edge);
    }
  }
  return merged;
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
  for (const node of nodes) {
    if (isCanvasAssetNode(node)) {
      const converted = canvasAssetToCanonical(node);
      if (!converted) continue;
      const inputs = { ...converted.inputs };
      for (const edge of flatEdges) {
        if (edge.target !== node.id) continue;
        const targetDef = definitions[workflowClassType(nodeFor(nodes, edge.target))];
        const targetHandle = edge.targetHandle ?? targetDef?.inputs[0]?.id ?? 'input';
        const sourceNode = nodeFor(nodes, edge.source);
        let slot = 0;
        if (sourceNode?.type === CANVAS_ASSET_NODE_TYPE) {
          slot = 0;
        } else {
          const sourceDef = definitions[workflowClassType(sourceNode)];
          slot = outputSlotIndex(sourceDef, edge.sourceHandle);
        }
        inputs[targetHandle] = [edge.source, slot];
      }
      nodeSpecs[node.id] = {
        class_type: converted.class_type,
        inputs,
        meta: converted.meta,
      };
      continue;
    }

    if (isUiOnly(node)) continue;
    if (!isWorkflowEditorNode(node)) continue;

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

    // 2. Link refs from incoming data edges override literal widget values.
    // Control-flow edges (pass/fail/retry) share node pairs with data links and
    // must not be serialised as input refs — that creates dependency cycles.
    for (const edge of flatEdges) {
      if (edge.target !== node.id || isControlFlowEdge(edge)) continue;
      const targetHandle = edge.targetHandle ?? def?.inputs[0]?.id ?? 'input';
      const sourceNode = nodeFor(nodes, edge.source);
      const slot =
        isCanvasAssetNode(sourceNode)
          ? 0
          : outputSlotIndex(
              definitions[workflowClassType(sourceNode)],
              edge.sourceHandle,
            );
      const slotDef = def?.inputs.find((i) => i.id === targetHandle) ?? def?.inputs[0];
      const isArray = slotDef?.type === 'ARRAY';
      if (isArray) {
        const prev = inputs[targetHandle];
        const link: [string, number] = [edge.source, slot];
        if (Array.isArray(prev)) {
          // Already a multi-link array: [[id, slot], ...]
          if (prev.length > 0 && Array.isArray(prev[0])) {
            (prev as unknown[]).push(link);
            inputs[targetHandle] = prev;
          } else if (prev.length === 2 && typeof prev[0] === 'string') {
            inputs[targetHandle] = [prev as [string, number], link];
          } else {
            inputs[targetHandle] = [link];
          }
        } else {
          inputs[targetHandle] = [link];
        }
      } else {
        inputs[targetHandle] = [edge.source, slot];
      }
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
    const control = buildNodeControlFromEditorEdges(node.id, edges);
    if (control) {
      nodeSpecs[node.id]!.control = control;
    }
  }

  // Storyboard: honour explicit shot ordering from editor UI.
  for (const node of nodes) {
    if (!isWorkflowEditorNode(node) || node.type !== 'workflow' || node.data.nodeType !== 'Art.Storyboard') continue;
    const spec = nodeSpecs[node.id];
    if (!spec) continue;
    const order = node.data.values?.shot_order;
    const shots = spec.inputs.shots;
    if (!Array.isArray(order) || !Array.isArray(shots) || shots.length === 0) continue;
    if (!Array.isArray(shots[0])) continue;
    const byId = new Map((shots as [string, number][]).map((link) => [link[0], link]));
    const sorted: [string, number][] = [];
    for (const sid of order as string[]) {
      const link = byId.get(sid);
      if (link) {
        sorted.push(link);
        byId.delete(sid);
      }
    }
    for (const link of byId.values()) sorted.push(link);
    spec.inputs.shots = sorted;
  }

  const dataEdges = flatEdges.filter((edge) => !isControlFlowEdge(edge));
  const canonicalEdges: CanonicalEdge[] = dataEdges.map((edge) => {
    const sourceNode = nodeFor(nodes, edge.source);
    const targetNode = nodeFor(nodes, edge.target);
    const sourceDef = definitions[workflowClassType(sourceNode)];
    const targetDef = definitions[workflowClassType(targetNode)];
    const source_slot =
      isCanvasAssetNode(sourceNode)
        ? 0
        : outputSlotIndex(sourceDef, edge.sourceHandle);
    return {
      source: edge.source,
      target: edge.target,
      source_slot,
      target_slot: inputSlotIndex(targetDef, edge.targetHandle),
    };
  });

  // Prefer an explicit Start node; else the first node with no incoming edges.
  const targets = new Set(flatEdges.map((e) => e.target));
  const startNode =
    workflowNodes.find((n) => isWorkflowEditorNode(n) && n.data.nodeType === 'StartNode') ??
    nodes.find((n) => isCanvasAssetNode(n)) ??
    workflowNodes.find((n) => !targets.has(n.id));

  const workOrder = workflowNodes
    .filter(
      (n) =>
        isWorkflowEditorNode(n) &&
        n.type === 'workflow' &&
        n.data.nodeType !== 'StartNode' &&
        n.data.nodeType !== 'EndNode',
    )
    .sort((a, b) => a.position.x - b.position.x || a.position.y - b.position.y)
    .map((n) => n.id);

  const finalized = finalizeExecutableGraph(
    nodeSpecs,
    { start: startNode?.id, edges: canonicalEdges },
    workOrder,
  );

  return {
    id: params.id,
    name: params.name,
    description: params.description ?? '',
    inputs: params.inputs ?? [],
    outputs: params.outputs ?? [],
    metadata: { ...(params.metadata ?? {}), editor: 'react-flow-graph' },
    nodes: finalized.nodes,
    control: finalized.control,
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
  const uiNodes = ui && Array.isArray(ui.nodes) ? (ui.nodes as unknown[]) : [];

  const rawNodes = obj.nodes;
  const nodesDict =
    rawNodes && typeof rawNodes === 'object' && !Array.isArray(rawNodes)
      ? (rawNodes as Record<string, CanonicalNode>)
      : null;

  // Fast path: a `ui` block authored by THIS editor carries typed editor
  // nodes (`type: 'workflow'` + `data.nodeType`) and can be used verbatim to
  // restore the exact saved layout.
  if (uiNodes.length > 0 && uiBlockIsEditorShaped(uiNodes)) {
    const storedUiEdges = ui && Array.isArray(ui.edges) ? (ui.edges as EditorEdge[]) : [];
    const edges =
      nodesDict !== null
        ? mergeEditorEdges(
            storedUiEdges,
            extractControlFlowEdges(nodesDict, definitions),
          )
        : storedUiEdges;
    return {
      ...shared,
      nodes: uiNodes as EditorNode[],
      edges,
      viewport: ui?.viewport,
    };
  }

  // Otherwise rebuild typed `workflow` nodes from the canonical `nodes` dict.
  // Templates (and any non-editor producer) ship a preview-shaped `ui` block
  // whose nodes use the ChatWorkflowMiniNode shape (`type: 'generic'`); the
  // ComfyUI editor cannot render those, so we ignore the projection but reuse
  // the positions it already computed for a clean first-open layout.
  if (nodesDict !== null) {
    const rebuilt = rebuildFromCanonical(nodesDict, definitions, positionsFromUiNodes(uiNodes));
    const layoutEdges =
      ui && Array.isArray(ui.edges)
        ? layoutUiEdgesToEditorEdges(ui.edges as unknown[], nodesDict, definitions)
        : [];
    const controlEdges = extractControlFlowEdges(nodesDict, definitions);
    return {
      ...shared,
      nodes: rebuilt.nodes,
      edges: mergeEditorEdges(rebuilt.edges, [...layoutEdges, ...controlEdges]),
      viewport: ui?.viewport,
    };
  }
  return { nodes: [], edges: [], ...shared };
}

/**
 * A `ui` block authored by the typed editor stores `data.nodeType` on every
 * node (including reroute/group affordances). Preview-shaped blocks emitted by
 * the backend layout helper carry only `data.label`/`data.icon`, so this lets
 * us tell the two apart and avoid rendering generic nodes as bare defaults.
 */
function uiBlockIsEditorShaped(uiNodes: unknown[]): boolean {
  return uiNodes.every((n) => {
    if (!n || typeof n !== 'object') return false;
    const node = n as { type?: string; data?: { nodeType?: unknown } };
    if (node.type === CANVAS_ASSET_NODE_TYPE) return true;
    return typeof node.data?.nodeType === 'string';
  });
}

/** Collect `id → position` from a stored `ui` block so a canonical rebuild can
 * reuse a pre-computed layout instead of falling back to a grid. */
function positionsFromUiNodes(uiNodes: unknown[]): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>();
  for (const node of uiNodes) {
    if (!node || typeof node !== 'object') continue;
    const { id, position } = node as { id?: unknown; position?: { x?: unknown; y?: unknown } };
    if (typeof id !== 'string') continue;
    if (position && typeof position.x === 'number' && typeof position.y === 'number') {
      positions.set(id, { x: position.x, y: position.y });
    }
  }
  return positions;
}

function rebuildFromCanonical(
  nodesDict: Record<string, CanonicalNode>,
  definitions: Record<string, NodeDefinition>,
  positions?: Map<string, { x: number; y: number }>,
): { nodes: EditorNode[]; edges: EditorEdge[] } {
  const nodes: EditorNode[] = [];
  const edges: EditorEdge[] = [];
  let i = 0;
  for (const [id, spec] of Object.entries(nodesDict)) {
    const assetNode = canonicalToCanvasAsset(id, spec);
    if (assetNode) {
      nodes.push(assetNode);
      i += 1;
      continue;
    }

    const classType = spec.class_type;
    const def = definitions[classType];
    const values: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(spec.inputs ?? {})) {
      const isLink = Array.isArray(value) && value.length === 2 && typeof value[0] === 'string';
      const isLinkArray =
        Array.isArray(value) &&
        value.length > 0 &&
        Array.isArray(value[0]) &&
        (value as unknown[]).every(
          (v) => Array.isArray(v) && v.length === 2 && typeof (v as unknown[])[0] === 'string',
        );
      if (isLink) {
        const [sourceId, slot] = value as [string, number];
        const sourceSpec = nodesDict[sourceId];
        const sourceAssetKind = sourceSpec ? canvasAssetKindFromCanonical(sourceSpec) : null;
        const sourceDef = definitions[sourceSpec?.class_type ?? ''];
        const sourceHandle =
          sourceSpec && canonicalToCanvasAsset(sourceId, sourceSpec)
            ? canvasAssetSourceHandle(sourceAssetKind ?? 'image')
            : sourceDef?.outputs[slot]?.id;
        edges.push({
          id: `edge-${sourceId}-${id}-${key}`,
          source: sourceId,
          target: id,
          sourceHandle,
          targetHandle: key,
          type: 'workflow',
        });
      } else if (isLinkArray) {
        for (const entry of value as [string, number][]) {
          const [sourceId, slot] = entry;
          const sourceSpec = nodesDict[sourceId];
          const sourceAssetKind = sourceSpec ? canvasAssetKindFromCanonical(sourceSpec) : null;
          const sourceDef = definitions[sourceSpec?.class_type ?? ''];
          const sourceHandle =
            sourceSpec && canonicalToCanvasAsset(sourceId, sourceSpec)
              ? canvasAssetSourceHandle(sourceAssetKind ?? 'image')
              : sourceDef?.outputs[slot]?.id;
          edges.push({
            id: `edge-${sourceId}-${id}-${key}-${slot}`,
            source: sourceId,
            target: id,
            sourceHandle,
            targetHandle: key,
            type: 'workflow',
          });
        }
      } else {
        values[key] = value;
      }
    }
    const pos =
      positions?.get(id) ??
      spec.meta?.position ?? { x: (i % 4) * 280, y: Math.floor(i / 4) * 200 };
    const mode = spec.meta?.mode;
    nodes.push({
      id,
      type: 'workflow',
      position: pos,
      data: {
        nodeType: classType,
        label: spec.meta?.title || spec.meta?.name || def?.displayName || classType,
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
