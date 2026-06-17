import { useCallback } from 'react';
import { useStore } from '@xyflow/react';

import type { EditorEdge, EditorNode } from '../../graph/serialization';

export function useInboundEdges(nodeId: string, targetHandle?: string): EditorEdge[] {
  return useStore(
    useCallback(
      (s) =>
        s.edges.filter(
          (e) =>
            e.target === nodeId &&
            (targetHandle == null || e.targetHandle === targetHandle || !e.targetHandle),
        ) as EditorEdge[],
      [nodeId, targetHandle],
    ),
  );
}

export function useSourceNode(sourceId: string | undefined): EditorNode | undefined {
  return useStore(
    useCallback(
      (s) => {
        if (!sourceId) return undefined;
        const fromLookup = (s as { nodeLookup?: Map<string, unknown> }).nodeLookup?.get(sourceId);
        if (fromLookup) return fromLookup as EditorNode;
        return s.nodes.find((n) => n.id === sourceId) as EditorNode | undefined;
      },
      [sourceId],
    ),
  );
}
