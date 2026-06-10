import { apiClient } from '@/api/client';
import { parseStoredFlowData } from '@/lib/parseFlowDataFromApi';

export interface FlowData {
  id: string;
  name: string;
  description?: string;
  nodes: unknown[];
  edges: unknown[];
  tags?: string;
}

/**
 * Fetch a single flow by id. Kept separate from `WorkflowsPage/index.tsx` so it can be
 * called from non-React code (route lazy loader) without dragging the whole
 * WorkflowsPage chunk into the main bundle.
 */
export async function fetchFlow(flowId: string): Promise<FlowData> {
  const raw = await apiClient.get<{
    id: string;
    name: string;
    description?: string | null;
    data?: string | null;
    tags?: string | null;
  }>(`/workflow/flows/${flowId}`);
  const { nodes, edges } = parseStoredFlowData(raw.data ?? undefined);
  return {
    id: String(raw.id),
    name: raw.name,
    description: raw.description ?? undefined,
    nodes,
    edges,
    tags: raw.tags ?? undefined,
  };
}
