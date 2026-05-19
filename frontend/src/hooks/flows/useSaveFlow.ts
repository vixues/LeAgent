import { useCallback, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/api/client';
import { useFlowStore } from '../../stores/flow';

interface SaveFlowParams {
  id?: string | null;
  name: string;
  nodes: unknown[];
  edges: unknown[];
}

interface SaveFlowResponse {
  id: string;
  name: string;
  updatedAt: string;
}

const KNOWN_NODE_TYPES = new Set([
  'start',
  'end',
  'tool_call',
  'llm_call',
  'condition',
  'parallel',
  'human_review',
  'error_handler',
  'transform',
  'subworkflow',
  'wait',
  'script',
  'script_agent',
  'code_agent', // legacy flows
]);

function normalizeNodeForSave(node: unknown): unknown {
  if (!node || typeof node !== 'object') return node;
  const value = node as Record<string, unknown>;
  const data = (value.data && typeof value.data === 'object'
    ? value.data
    : {}) as Record<string, unknown>;

  const rawType = typeof value.type === 'string' ? value.type : '';
  const dataIcon = typeof data.icon === 'string' ? data.icon : '';
  const dataType = typeof data.type === 'string' ? data.type : '';
  const inferredType = rawType === 'generic'
    ? (KNOWN_NODE_TYPES.has(dataType) ? dataType : KNOWN_NODE_TYPES.has(dataIcon) ? dataIcon : 'tool_call')
    : rawType;

  if (!inferredType) return node;
  return {
    ...value,
    type: inferredType,
  };
}

function normalizeNodesForSave(nodes: unknown[]): unknown[] {
  return nodes.map((node) => normalizeNodeForSave(node));
}

async function saveFlowToAPI(params: SaveFlowParams): Promise<SaveFlowResponse> {
  const body = {
    name: params.name,
    data: {
      nodes: normalizeNodesForSave(params.nodes),
      edges: params.edges,
    },
  };

  if (params.id) {
    return apiClient.put<SaveFlowResponse>(`/workflow/flows/${params.id}`, body);
  }
  return apiClient.post<SaveFlowResponse>('/workflow/flows', body);
}

interface UseSaveFlowOptions {
  onSuccess?: (data: SaveFlowResponse) => void;
  onError?: (error: Error) => void;
}

export function useSaveFlow(options: UseSaveFlowOptions = {}) {
  const queryClient = useQueryClient();
  const { getFlowData, setFlowId, markClean } = useFlowStore();
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);

  const mutation = useMutation({
    mutationFn: saveFlowToAPI,
    onSuccess: (data) => {
      setFlowId(data.id);
      markClean();
      setLastSavedAt(new Date(data.updatedAt));
      
      queryClient.invalidateQueries({ queryKey: ['flows'] });
      queryClient.invalidateQueries({ queryKey: ['flow', data.id] });
      
      options.onSuccess?.(data);
    },
    onError: (error: Error) => {
      options.onError?.(error);
    },
  });

  const saveFlow = useCallback(async () => {
    const flowData = getFlowData();
    return mutation.mutateAsync({
      id: flowData.id,
      name: flowData.name,
      nodes: flowData.nodes,
      edges: flowData.edges,
    });
  }, [getFlowData, mutation]);

  const saveFlowAs = useCallback(async (name: string) => {
    const flowData = getFlowData();
    return mutation.mutateAsync({
      id: null,
      name,
      nodes: flowData.nodes,
      edges: flowData.edges,
    });
  }, [getFlowData, mutation]);

  return {
    saveFlow,
    saveFlowAs,
    isSaving: mutation.isPending,
    saveError: mutation.error,
    lastSavedAt,
    isSuccess: mutation.isSuccess,
  };
}

export function useAutoSave(intervalMs: number = 30000) {
  const { isDirty } = useFlowStore();
  const { saveFlow, isSaving } = useSaveFlow();

  const autoSave = useCallback(async () => {
    if (isDirty && !isSaving) {
      try {
        await saveFlow();
      } catch {
        console.error('Auto-save failed');
      }
    }
  }, [isDirty, isSaving, saveFlow]);

  return { autoSave, intervalMs };
}

export default useSaveFlow;
