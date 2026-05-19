/**
 * React Query hooks + an SSE log stream consumer for the coding-project
 * live-runtime feature.
 *
 * Backend endpoints live under `/api/v1/coding-projects/...` (see
 * `leagent/backend/leagent/api/v1/coding_projects.py`).
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  useMutation,
  useQuery,
  useQueryClient,
  type Query,
} from '@tanstack/react-query';
import { apiClient, getAccessToken } from '@/api/client';
import { getMachineFingerprint } from '@/lib/machineFingerprint';

// ---------------------------------------------------------------------------
// Schemas (mirror the Python Pydantic models)
// ---------------------------------------------------------------------------

export type CodingProjectRuntimeKind = 'frontend' | 'fastapi' | 'python';

export type CodingProjectStatus =
  | 'idle'
  | 'starting'
  | 'running'
  | 'stopping'
  | 'crashed';

export interface CodingProject {
  id: string;
  user_id?: string | null;
  folder_id?: string | null;
  name: string;
  description?: string | null;
  template: string;
  runtime_kind: CodingProjectRuntimeKind;
  root_path: string;
  port?: number | null;
  status: CodingProjectStatus;
  last_started_at?: string | null;
  last_stopped_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface TemplateInfo {
  name: string;
  runtime_kind: string;
  title: string;
  description: string;
  needs_install: boolean;
}

export interface CreateProjectInput {
  name: string;
  template: string;
  description?: string | null;
  folder_id?: string | null;
  into_path?: string | null;
}

export interface RunResponse {
  project_id: string;
  status: CodingProjectStatus;
  runtime_kind: CodingProjectRuntimeKind;
  port: number;
  host: string;
  preview_url: string;
  preview_token: string;
  expires_at: number;
  health_path: string;
}

export interface StatusResponse {
  project_id: string;
  status: CodingProjectStatus;
  runtime_kind: CodingProjectRuntimeKind;
  port?: number | null;
  pid?: number | null;
  last_started_at?: string | null;
  last_stopped_at?: string | null;
  is_running: boolean;
}

export interface CodingProjectLogLine {
  seq: number;
  ts: number;
  stream: 'stdout' | 'stderr';
  text: string;
}

/** React Query root key for coding-projects queries (workspace hooks reuse this). */
export const CODING_PROJECTS_QUERY_ROOT = ['coding-projects'] as const;

const ROOT_KEY = CODING_PROJECTS_QUERY_ROOT;

// ---------------------------------------------------------------------------
// Templates
// ---------------------------------------------------------------------------

export function useCodingProjectTemplates() {
  return useQuery({
    queryKey: [...ROOT_KEY, 'templates'],
    queryFn: () => apiClient.get<TemplateInfo[]>('/coding-projects/templates'),
    staleTime: 5 * 60_000,
  });
}

// ---------------------------------------------------------------------------
// Projects CRUD
// ---------------------------------------------------------------------------

export function useCodingProjects() {
  return useQuery({
    queryKey: [...ROOT_KEY, 'list'],
    queryFn: () => apiClient.get<CodingProject[]>('/coding-projects'),
    staleTime: 10_000,
  });
}

export function useCodingProject(projectId: string | null | undefined) {
  return useQuery({
    queryKey: [...ROOT_KEY, 'detail', projectId],
    queryFn: () =>
      apiClient.get<CodingProject>(`/coding-projects/${projectId}`),
    enabled: !!projectId,
    staleTime: 5_000,
  });
}

export function useCreateCodingProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateProjectInput) =>
      apiClient.post<CodingProject>('/coding-projects', input),
    onSuccess: (created) => {
      queryClient.invalidateQueries({ queryKey: [...ROOT_KEY, 'list'] });
      queryClient.invalidateQueries({
        queryKey: [...ROOT_KEY, 'workspace', created.id],
      });
    },
  });
}

export function useDeleteCodingProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) =>
      apiClient.delete<void>(`/coding-projects/${projectId}`),
    onSuccess: (_data, projectId) => {
      queryClient.invalidateQueries({ queryKey: [...ROOT_KEY, 'list'] });
      queryClient.removeQueries({
        queryKey: [...ROOT_KEY, 'workspace', projectId],
      });
    },
  });
}

// ---------------------------------------------------------------------------
// Run / stop / status
// ---------------------------------------------------------------------------

export function useRunCodingProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) =>
      apiClient.post<RunResponse>(`/coding-projects/${projectId}/run`),
    onSuccess: (_data, projectId) => {
      queryClient.invalidateQueries({
        queryKey: [...ROOT_KEY, 'status', projectId],
      });
      queryClient.invalidateQueries({
        queryKey: [...ROOT_KEY, 'detail', projectId],
      });
      queryClient.invalidateQueries({ queryKey: [...ROOT_KEY, 'list'] });
    },
  });
}

export function useStopCodingProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) =>
      apiClient.post<StatusResponse>(`/coding-projects/${projectId}/stop`),
    onSuccess: (_data, projectId) => {
      queryClient.invalidateQueries({
        queryKey: [...ROOT_KEY, 'status', projectId],
      });
      queryClient.invalidateQueries({
        queryKey: [...ROOT_KEY, 'detail', projectId],
      });
      queryClient.invalidateQueries({ queryKey: [...ROOT_KEY, 'list'] });
    },
  });
}

export interface CodingProjectStatusPollOptions {
  /** Milliseconds between polls while the dev server is up (`running` / `is_running`). Default `5000`. */
  activeIntervalMs?: number;
  /** Milliseconds while `starting` or `stopping`. Default `2500`. */
  transitionalIntervalMs?: number;
}

/**
 * Smart polling: returns `false` when idle/crashed so React Query does not
 * schedule periodic refetches. Used by {@link useCodingProjectStatus}.
 */
export function getCodingProjectStatusPollInterval(
  data: StatusResponse | undefined,
  opts: Required<CodingProjectStatusPollOptions>,
): number | false {
  if (!data) return false;

  const { status, is_running: isRunning } = data;

  if (status === 'crashed') return false;
  if (status === 'idle' && !isRunning) return false;

  if (status === 'starting' || status === 'stopping') {
    return opts.transitionalIntervalMs;
  }

  if (isRunning || status === 'running') {
    return opts.activeIntervalMs;
  }

  return opts.transitionalIntervalMs;
}

export interface UseCodingProjectStatusOptions extends CodingProjectStatusPollOptions {
  enabled?: boolean;
  /**
   * `smart` (default): poll only during starting / stopping / running.
   * `fixed`: previous behaviour — constant interval whenever enabled.
   */
  polling?: 'smart' | 'fixed';
  /** @deprecated Use `activeIntervalMs`; kept as alias for `activeIntervalMs`. */
  refetchIntervalMs?: number;
}

export function useCodingProjectStatus(
  projectId: string | null | undefined,
  options: UseCodingProjectStatusOptions = {},
) {
  const {
    enabled = true,
    polling = 'smart',
    refetchIntervalMs = 5_000,
    activeIntervalMs = refetchIntervalMs,
    transitionalIntervalMs = 2_500,
  } = options;

  const pollOpts: Required<CodingProjectStatusPollOptions> = {
    activeIntervalMs,
    transitionalIntervalMs,
  };

  const refetchInterval =
    polling === 'fixed'
      ? activeIntervalMs
      : (query: Query<StatusResponse, Error>) =>
          getCodingProjectStatusPollInterval(
            query.state.data,
            pollOpts,
          );

  return useQuery({
    queryKey: [...ROOT_KEY, 'status', projectId],
    queryFn: () =>
      apiClient.get<StatusResponse>(`/coding-projects/${projectId}/status`),
    enabled: !!projectId && enabled,
    refetchInterval,
    refetchIntervalInBackground: false,
    staleTime: polling === 'smart' ? 30_000 : 1_000,
  });
}

// ---------------------------------------------------------------------------
// Log SSE stream
// ---------------------------------------------------------------------------

export interface UseCodingProjectLogsResult {
  lines: CodingProjectLogLine[];
  done: boolean;
  error: string | null;
  clear: () => void;
}

/**
 * Connect to the SSE log stream and accumulate lines into a bounded array.
 *
 * `EventSource` doesn't support the `Authorization` header natively, so we
 * fall back to a streaming `fetch` and parse the SSE frames manually. This
 * also lets us cleanly abort on unmount or `enabled` flipping false.
 */
export function useCodingProjectLogs(
  projectId: string | null | undefined,
  options: { enabled?: boolean; max?: number } = {},
): UseCodingProjectLogsResult {
  const { enabled = true, max = 1500 } = options;
  const [lines, setLines] = useState<CodingProjectLogLine[]>([]);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!projectId || !enabled) return;
    setLines([]);
    setDone(false);
    setError(null);
    const controller = new AbortController();
    abortRef.current = controller;

    const token = getAccessToken();
    const url = (import.meta.env.VITE_API_BASE_URL || '/api/v1') +
      `/coding-projects/${projectId}/logs`;

    (async () => {
      try {
        const headers: Record<string, string> = { Accept: 'text/event-stream' };
        if (token) headers.Authorization = `Bearer ${token}`;
        const fp = getMachineFingerprint();
        if (fp.length >= 8) {
          headers['x-leagent-machine-fingerprint'] = fp;
        }
        const resp = await fetch(url, {
          method: 'GET',
          credentials: 'include',
          headers,
          signal: controller.signal,
        });
        if (!resp.ok || !resp.body) {
          setError(`HTTP ${resp.status}`);
          return;
        }
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        const flush = (block: string) => {
          const lines2 = block.split('\n');
          let event = 'message';
          let data = '';
          for (const line of lines2) {
            if (line.startsWith('event:')) event = line.slice(6).trim();
            else if (line.startsWith('data:')) data += line.slice(5).trim();
          }
          if (!data) return;
          if (event === 'log') {
            try {
              const parsed = JSON.parse(data) as CodingProjectLogLine;
              setLines((prev) => {
                const next = [...prev, parsed];
                return next.length > max ? next.slice(next.length - max) : next;
              });
            } catch {
              /* ignore */
            }
          } else if (event === 'done') {
            setDone(true);
          }
        };

        while (!controller.signal.aborted) {
          const { done: streamDone, value } = await reader.read();
          if (streamDone) break;
          buffer += decoder.decode(value, { stream: true });
          const blocks = buffer.split('\n\n');
          buffer = blocks.pop() || '';
          for (const block of blocks) {
            if (block.trim()) flush(block);
          }
        }
        setDone(true);
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') return;
        setError(err instanceof Error ? err.message : String(err));
      }
    })();

    return () => {
      controller.abort();
      abortRef.current = null;
    };
  }, [projectId, enabled, max]);

  const clear = useMemo(
    () => () => {
      setLines([]);
      setError(null);
      setDone(false);
    },
    [],
  );

  return { lines, done, error, clear };
}
