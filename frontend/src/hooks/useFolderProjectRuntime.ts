import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { apiClient, getAccessToken } from '@/api/client';
import { getMachineFingerprint } from '@/lib/machineFingerprint';
import { useCodingProjectTemplates } from '@/hooks/useCodingProjects';

export interface FolderProjectRunResponse {
  folder_id: string;
  project_id: string;
  status: string;
  runtime_kind: string;
  port: number;
  host: string;
  preview_url: string;
  preview_token: string;
  expires_at: number;
  health_path: string;
}

export interface FolderProjectStatusResponse {
  folder_id: string;
  project_id: string;
  status: string;
  runtime_kind: string;
  port?: number | null;
  pid?: number | null;
  is_running: boolean;
}

const ROOT = ['folders', 'project-runtime'] as const;

export function useFolderProjectStatus(folderId: string | null, enabled = true) {
  return useQuery({
    queryKey: [...ROOT, 'status', folderId],
    queryFn: () =>
      apiClient.get<FolderProjectStatusResponse>(
        `/folders/${folderId}/project/status`,
      ),
    enabled: Boolean(folderId) && enabled,
    refetchInterval: (q) => (q.state.data?.is_running ? 3000 : false),
  });
}

export function useRunFolderProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (folderId: string) =>
      apiClient.post<FolderProjectRunResponse>(
        `/folders/${folderId}/project/run`,
      ),
    onSuccess: (_data, folderId) => {
      qc.invalidateQueries({ queryKey: [...ROOT, 'status', folderId] });
    },
  });
}

export function useStopFolderProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (folderId: string) =>
      apiClient.post<FolderProjectStatusResponse>(
        `/folders/${folderId}/project/stop`,
      ),
    onSuccess: (_data, folderId) => {
      qc.invalidateQueries({ queryKey: [...ROOT, 'status', folderId] });
    },
  });
}

export function useScaffoldFolderProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      folderId,
      name,
      template,
      description,
    }: {
      folderId: string;
      name: string;
      template: string;
      description?: string;
    }) =>
      apiClient.post(`/folders/${folderId}/project/scaffold`, {
        name,
        template,
        description,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['folders'] });
    },
  });
}

export { useCodingProjectTemplates };

export function useFolderProjectLogs(
  folderId: string | null,
  options: { enabled?: boolean; max?: number } = {},
) {
  const { enabled = true, max = 1500 } = options;
  const [lines, setLines] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!folderId || !enabled) return;
    setLines([]);
    setError(null);
    const controller = new AbortController();
    const base = import.meta.env.VITE_API_BASE_URL || '/api/v1';
    const url = `${base}/folders/${folderId}/project/logs`;
    (async () => {
      try {
        const headers: Record<string, string> = { Accept: 'text/event-stream' };
        const token = getAccessToken();
        if (token) headers.Authorization = `Bearer ${token}`;
        const fp = getMachineFingerprint();
        if (fp.length >= 8) headers['x-leagent-machine-fingerprint'] = fp;
        const resp = await fetch(url, {
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
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split('\n\n');
          buffer = parts.pop() ?? '';
          for (const block of parts) {
            let event = 'message';
            let data = '';
            for (const line of block.split('\n')) {
              if (line.startsWith('event:')) event = line.slice(6).trim();
              else if (line.startsWith('data:')) data += line.slice(5).trim();
            }
            if (event === 'log' && data) {
              try {
                const parsed = JSON.parse(data) as { message?: string; text?: string };
                const line = parsed.message ?? parsed.text ?? data;
                setLines((prev) => {
                  const next = [...prev, line];
                  return next.length > max ? next.slice(next.length - max) : next;
                });
              } catch {
                setLines((prev) => [...prev.slice(-max), data]);
              }
            }
          }
        }
      } catch (e) {
        if ((e as Error).name !== 'AbortError') {
          setError(String(e));
        }
      }
    })();
    return () => controller.abort();
  }, [folderId, enabled, max]);

  return { lines, error };
}
