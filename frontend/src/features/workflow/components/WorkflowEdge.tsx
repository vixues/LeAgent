import { memo } from 'react';
import { BaseEdge, getBezierPath, type EdgeProps } from '@xyflow/react';

import { isControlFlowEdgeData } from '../graph/connectionUtils';

/**
 * Edge colored by the wire type of the slot it carries (set on connect from
 * the source slot colour), echoing ComfyUI's type-colored links.
 * Control-flow (sequence) edges render dashed slate.
 */
function WorkflowEdgeImpl({
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  data,
  selected,
}: EdgeProps) {
  const [path] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });
  const isControl = isControlFlowEdgeData(data);
  const color = (data?.color as string) || '#94a3b8';
  return (
    <BaseEdge
      path={path}
      markerEnd={markerEnd}
      style={{
        stroke: color,
        strokeWidth: selected ? 3 : 2,
        opacity: selected ? 1 : 0.85,
        strokeDasharray: isControl ? '6 4' : undefined,
      }}
    />
  );
}

export const WorkflowEdge = memo(WorkflowEdgeImpl);
