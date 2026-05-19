import { useMemo } from 'react';
import { useGetFlows } from '@/controllers/API/queries/flows';
import {
  useRunFlow as useRunFlowMutation,
  type RunFlowResponse,
} from '@/controllers/API/queries/executions';

interface Flow {
  id: string;
  name: string;
  description?: string;
  status: 'draft' | 'active' | 'paused' | 'error';
  nodeCount: number;
  inputSchema?: Record<string, {
    type: string;
    title?: string;
    description?: string;
    placeholder?: string;
    required?: boolean;
    multiline?: boolean;
  }>;
  createdAt: string;
  updatedAt: string;
}

interface RunFlowResult {
  success: boolean;
  execution_id: string;
  prompt_id: string;
  flow_id: string;
  status: string;
  queue_position?: number | null;
  message?: string;
  result?: unknown;
  error?: string;
  duration?: string;
  logs?: Array<{
    timestamp: string;
    level: 'info' | 'warn' | 'error';
    message: string;
  }>;
}

export function useFlows() {
  const query = useGetFlows({ pageSize: 50 });
  const data = useMemo(() => {
    return (query.data?.data ?? []).map((f): Flow => {
      const parsedData = (() => {
        try {
          return f.data ? JSON.parse(f.data) : null;
        } catch {
          return null;
        }
      })() as Record<string, unknown> | null;
      const nodes = parsedData?.nodes;
      const inputs = parsedData?.inputs;
      const nodeCount = Array.isArray(nodes)
        ? nodes.length
        : nodes && typeof nodes === 'object'
          ? Object.keys(nodes as Record<string, unknown>).length
          : 0;
      const inputSchema = Array.isArray(inputs)
        ? Object.fromEntries(
            inputs
              .filter((it): it is Record<string, unknown> => !!it && typeof it === 'object')
              .map((it) => [
                String(it.name ?? it.key ?? 'input'),
                {
                  type: String(it.type ?? 'string'),
                  title: typeof it.title === 'string' ? it.title : undefined,
                  description: typeof it.description === 'string' ? it.description : undefined,
                  required: Boolean(it.required),
                },
              ]),
          )
        : undefined;
      return {
        id: f.id,
        name: f.name,
        description: f.description ?? undefined,
        status: f.status === 'published' ? 'active' : (f.status as Flow['status']),
        nodeCount,
        inputSchema,
        createdAt: f.created_at ?? new Date().toISOString(),
        updatedAt: f.updated_at ?? new Date().toISOString(),
      };
    });
  }, [query.data?.data]);

  return { ...query, data };
}

export function useRunFlow() {
  const mutation = useRunFlowMutation();
  return {
    ...mutation,
    mutateAsync: async ({ flowId, inputs }: { flowId: string; inputs: Record<string, unknown> }) => {
      const res: RunFlowResponse = await mutation.mutateAsync({
        flowId,
        inputData: inputs,
        priority: 5,
        triggerType: 'manual',
      });
      return {
        ...res,
        success: res.status === 'queued' || res.status === 'running' || res.status === 'completed',
        result: {
          execution_id: res.execution_id,
          prompt_id: res.prompt_id,
          queue_position: res.queue_position,
        },
      } as RunFlowResult;
    },
  };
}
