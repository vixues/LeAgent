import type { Connection, Node } from '@xyflow/react';

import type { NodeDefinition } from './objectInfo';
import { typesCompatible } from './socketTypes';
import type { WorkflowNodeData } from './serialization';

/** Slate colour for control-flow (sequence) edges. */
export const CONTROL_EDGE_COLOR = '#94a3b8';

export function controlFlowEdgeData(): Record<string, unknown> {
  return { kind: 'control', controlKind: 'next', color: CONTROL_EDGE_COLOR };
}

export function isControlFlowEdgeData(data: unknown): boolean {
  return (
    data != null &&
    typeof data === 'object' &&
    (data as { kind?: string }).kind === 'control'
  );
}

/** Resolve wire types for a connection between two workflow nodes. */
export function connectionWireTypes(
  conn: Connection,
  definitions: Record<string, NodeDefinition>,
  getNode: (id: string) => Node | undefined,
): { outType: string; inType: string; sourceDef?: NodeDefinition; targetDef?: NodeDefinition } {
  const sourceNode = getNode(conn.source ?? '');
  const targetNode = getNode(conn.target ?? '') as Node<WorkflowNodeData> | undefined;
  const sourceDef = definitions[(sourceNode?.data as WorkflowNodeData | undefined)?.nodeType ?? ''];
  const targetDef = definitions[targetNode?.data.nodeType ?? ''];
  const outType =
    sourceDef?.outputs.find((o) => o.id === conn.sourceHandle)?.type ??
    sourceDef?.outputs[0]?.type ??
    '*';
  const inType =
    targetDef?.inputs.find((i) => i.id === conn.targetHandle)?.type ??
    targetDef?.inputs[0]?.type ??
    '*';
  return { outType, inType, sourceDef, targetDef };
}

/** True when StartNode feeds workflow inputs into a downstream prompt slot. */
export function isStartInputFeedConnection(
  conn: Connection,
  definitions: Record<string, NodeDefinition>,
  getNode: (id: string) => Node | undefined,
): boolean {
  const sourceNode = getNode(conn.source ?? '');
  const targetNode = getNode(conn.target ?? '') as Node<WorkflowNodeData> | undefined;
  const sourceType = (sourceNode?.data as WorkflowNodeData | undefined)?.nodeType;
  if (sourceType !== 'StartNode') return false;
  const targetDef = definitions[targetNode?.data.nodeType ?? ''];
  if (!targetDef) return false;
  const handle = conn.targetHandle;
  if (handle === 'prompt') return true;
  if (!handle && targetDef.inputs.some((i) => i.id === 'prompt')) return true;
  return false;
}

/** Whether a canvas link is allowed (data-compatible or control-flow from a control node). */
export function isWorkflowConnectionValid(
  conn: Connection,
  definitions: Record<string, NodeDefinition>,
  getNode: (id: string) => Node | undefined,
): boolean {
  if (!conn.source || !conn.target || conn.source === conn.target) return false;
  if (isStartInputFeedConnection(conn, definitions, getNode)) return true;
  const { outType, inType, sourceDef } = connectionWireTypes(conn, definitions, getNode);
  if (inType === 'ARRAY') return true;
  if (typesCompatible(outType, inType)) return true;
  return Boolean(sourceDef?.controlFlow);
}

/** True when the link should be stored as ``control.next`` (not a data socket ref). */
export function isControlFlowConnection(
  conn: Connection,
  definitions: Record<string, NodeDefinition>,
  getNode: (id: string) => Node | undefined,
): boolean {
  if (isStartInputFeedConnection(conn, definitions, getNode)) return false;
  const { outType, inType, sourceDef } = connectionWireTypes(conn, definitions, getNode);
  if (typesCompatible(outType, inType)) return false;
  return Boolean(sourceDef?.controlFlow);
}
