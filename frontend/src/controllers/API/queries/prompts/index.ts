import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient, type UseQueryOptions } from '@tanstack/react-query';
import { apiClient, type ApiError } from '@/api/client';
import { openAuthedWebSocket } from '@/lib/authedTransport';
import { URL_KEYS } from '../../helpers/constants';
import type {
  WorkflowExecutionDetail,
  WorkflowExecutionSummary,
} from '../executions';

/**
 * Prompt-queue types and hooks for the workflow engine.
 *
 * The backend exposes two equivalent submission surfaces:
 *   - POST /workflow/prompts?flow_id=...
 *   - POST /workflow/flows/{flow_id}/run   (convenience wrapper)
 *
 * Both return a ``prompt_id`` that frontends can then subscribe to over
 * the WebSocket streams under ``/workflow/ws/executions``.
 */

export interface PromptSubmission {
  flow_id: string;
  input_data?: Record<string, unknown>;
  priority?: number;
  trigger_type?: string;
  session_id?: string | null;
  extra_data?: Record<string, unknown>;
}

export interface PromptSubmissionResponse {
  execution_id: string;
  prompt_id: string;
  flow_id: string;
  status: string;
  queue_position?: number | null;
  message?: string;
}

export type ExecutionEventType =
  | 'execution_started'
  | 'execution_completed'
  | 'execution_failed'
  | 'execution_cancelled'
  | 'execution_paused'
  | 'execution_resumed'
  | 'node_started'
  | 'node_completed'
  | 'node_failed'
  | 'node_progress'
  | 'queue_position';

export interface ExecutionEvent {
  type: ExecutionEventType | string;
  prompt_id: string;
  node_id?: string | null;
  data?: Record<string, unknown>;
  timestamp?: string;
}

// ---------------------------------------------------------------------------
// REST hooks
// ---------------------------------------------------------------------------

export const useSubmitPrompt = () => {
  const queryClient = useQueryClient();
  return useMutation<PromptSubmissionResponse, ApiError, PromptSubmission>({
    mutationFn: async ({ flow_id, ...body }) => {
      return apiClient.post<PromptSubmissionResponse>(
        URL_KEYS.WORKFLOW_PROMPTS,
        body,
        { params: { flow_id } },
      );
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['flows', data.flow_id, 'executions'] });
    },
  });
};

export const useGetPrompt = (
  promptId: string,
  options?: Omit<UseQueryOptions<WorkflowExecutionDetail, ApiError>, 'queryKey' | 'queryFn'>,
) => {
  return useQuery<WorkflowExecutionDetail, ApiError>({
    queryKey: ['prompts', promptId],
    queryFn: async () =>
      apiClient.get<WorkflowExecutionDetail>(URL_KEYS.WORKFLOW_PROMPT_BY_ID(promptId)),
    enabled: !!promptId,
    ...options,
  });
};

export const useCancelPrompt = () =>
  useMutation<{ prompt_id: string; status: string }, ApiError, string>({
    mutationFn: async (promptId) =>
      apiClient.post<{ prompt_id: string; status: string }>(
        URL_KEYS.WORKFLOW_PROMPT_CANCEL(promptId),
      ),
  });

export const usePausePrompt = () =>
  useMutation<{ prompt_id: string; status: string }, ApiError, string>({
    mutationFn: async (promptId) =>
      apiClient.post<{ prompt_id: string; status: string }>(
        URL_KEYS.WORKFLOW_PROMPT_PAUSE(promptId),
      ),
  });

export const useResumePrompt = () =>
  useMutation<
    { prompt_id: string; status: string },
    ApiError,
    { promptId: string; resumeData?: Record<string, unknown> }
  >({
    mutationFn: async ({ promptId, resumeData }) =>
      apiClient.post<{ prompt_id: string; status: string }>(
        URL_KEYS.WORKFLOW_PROMPT_RESUME(promptId),
        resumeData,
      ),
  });

// ---------------------------------------------------------------------------
// WebSocket hooks
// ---------------------------------------------------------------------------

function buildWsUrl(path: string): string {
  // The REST base is usually ``/api/v1``. The WS endpoints hang off the same
  // prefix so we can reuse it directly; in dev with proxies this is still
  // resolved via the current host.
  const base = import.meta.env.VITE_WS_BASE_URL as string | undefined;
  if (base) return `${base.replace(/\/$/, '')}${path}`;

  const loc = window.location;
  const proto = loc.protocol === 'https:' ? 'wss:' : 'ws:';
  const apiBase = (import.meta.env.VITE_API_BASE_URL as string | undefined) || '/api/v1';
  return `${proto}//${loc.host}${apiBase.replace(/\/$/, '')}${path}`;
}

export interface ExecutionStreamState {
  events: ExecutionEvent[];
  lastEvent: ExecutionEvent | null;
  isOpen: boolean;
  error: Event | null;
}

/**
 * Subscribe to the per-prompt execution stream.
 *
 * Opens a WebSocket at ``/workflow/ws/executions/{promptId}`` and keeps the
 * latest event + a bounded history in component state. Closes on unmount.
 */
export const useExecutionStream = (
  promptId: string | null | undefined,
  options?: { historyLimit?: number; onEvent?: (event: ExecutionEvent) => void },
): ExecutionStreamState => {
  const historyLimit = options?.historyLimit ?? 200;
  const onEventRef = useRef(options?.onEvent);
  onEventRef.current = options?.onEvent;

  const [state, setState] = useState<ExecutionStreamState>({
    events: [],
    lastEvent: null,
    isOpen: false,
    error: null,
  });

  useEffect(() => {
    if (!promptId) return;
    const url = buildWsUrl(`/workflow/ws/executions/${promptId}`);
    const ws = openAuthedWebSocket(url);

    ws.onopen = () => setState((s) => ({ ...s, isOpen: true, error: null }));
    ws.onerror = (e) => setState((s) => ({ ...s, error: e }));
    ws.onclose = () => setState((s) => ({ ...s, isOpen: false }));
    ws.onmessage = (msg) => {
      try {
        const event = JSON.parse(msg.data) as ExecutionEvent;
        onEventRef.current?.(event);
        setState((s) => ({
          ...s,
          events: [...s.events.slice(-historyLimit + 1), event],
          lastEvent: event,
        }));
      } catch {
        // ignore malformed frames
      }
    };

    return () => {
      ws.close();
    };
  }, [promptId, historyLimit]);

  return state;
};

export interface ExecutionsMonitorState {
  events: ExecutionEvent[];
  byPrompt: Record<string, WorkflowExecutionSummary>;
  isOpen: boolean;
}

/**
 * Subscribe to the fan-in monitor stream that relays events for every
 * prompt currently executing. Useful for dashboards.
 */
export const useExecutionsMonitor = (
  enabled = true,
  options?: { historyLimit?: number },
): ExecutionsMonitorState => {
  const historyLimit = options?.historyLimit ?? 500;
  const [state, setState] = useState<ExecutionsMonitorState>({
    events: [],
    byPrompt: {},
    isOpen: false,
  });

  useEffect(() => {
    if (!enabled) return;
    const url = buildWsUrl('/workflow/ws/executions');
    const ws = openAuthedWebSocket(url);

    ws.onopen = () => setState((s) => ({ ...s, isOpen: true }));
    ws.onclose = () => setState((s) => ({ ...s, isOpen: false }));
    ws.onmessage = (msg) => {
      try {
        const event = JSON.parse(msg.data) as ExecutionEvent;
        setState((s) => {
          const events = [...s.events.slice(-historyLimit + 1), event];
          const byPrompt = { ...s.byPrompt };
          const summary = event.data?.summary as WorkflowExecutionSummary | undefined;
          if (summary && event.prompt_id) {
            byPrompt[event.prompt_id] = summary;
          }
          return { events, byPrompt, isOpen: s.isOpen };
        });
      } catch {
        // ignore
      }
    };

    return () => {
      ws.close();
    };
  }, [enabled, historyLimit]);

  return state;
};
