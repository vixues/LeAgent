/**
 * React Query hooks for Folder code-project mode.
 *
 * Each hook is scoped to a folderId and only fires when project mode
 * is enabled, so they can be used unconditionally inside the
 * FolderPage tabset without extra guards. Backend endpoints live
 * under `/folders/{id}/project/...` (see api/v1/folders.py).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/api/client';

export interface ProjectTreeEntry {
  name: string;
  rel_path: string;
  type: 'file' | 'dir';
  size?: number | null;
  mtime?: number | null;
  is_ignored?: boolean;
  has_children?: boolean | null;
}

export interface ProjectFileResponse {
  rel_path: string;
  encoding?: string | null;
  size: number;
  line_count: number;
  is_binary: boolean;
  truncated: boolean;
  content: string;
  start_line: number;
  end_line: number;
}

export interface ProjectGitCommit {
  commit: string;
  short: string;
  author_name: string;
  author_email: string;
  date_iso: string;
  summary: string;
}

export interface ProjectGitStatusEntry {
  path: string;
  status_code: string;
}

export interface ProjectGitDiffResponse {
  commit: string | null;
  path: string | null;
  diff: string;
  scope: 'commit' | 'worktree';
}

export interface ProjectGitShowResponse {
  commit: string;
  path: string;
  content: string;
}

export interface UpdateProjectModeInput {
  enabled: boolean;
  project_path?: string | null;
}

const PROJECT_QUERY_BASE = ['folders', 'project'] as const;

export function useProjectTree(
  folderId: string | null | undefined,
  path: string = '',
  depth: number = 1,
  options: { includeIgnored?: boolean; enabled?: boolean } = {},
) {
  const { includeIgnored = false, enabled = true } = options;
  return useQuery({
    queryKey: [...PROJECT_QUERY_BASE, folderId, 'tree', path, depth, includeIgnored],
    queryFn: () =>
      apiClient.get<ProjectTreeEntry[]>(`/folders/${folderId}/project/tree`, {
        path,
        depth,
        include_ignored: includeIgnored ? 'true' : 'false',
      } as Record<string, string | number | boolean | undefined>),
    enabled: !!folderId && enabled,
    staleTime: 10_000,
  });
}

export function useProjectFile(
  folderId: string | null | undefined,
  path: string | null | undefined,
  options: { offset?: number; limit?: number; enabled?: boolean } = {},
) {
  const { offset = 1, limit, enabled = true } = options;
  return useQuery({
    queryKey: [...PROJECT_QUERY_BASE, folderId, 'file', path, offset, limit],
    queryFn: () =>
      apiClient.get<ProjectFileResponse>(`/folders/${folderId}/project/file`, {
        path: path!,
        offset,
        ...(limit ? { limit } : {}),
      } as Record<string, string | number | boolean | undefined>),
    enabled: !!folderId && !!path && enabled,
    staleTime: 5_000,
  });
}

export function useProjectGitLog(
  folderId: string | null | undefined,
  options: { path?: string | null; limit?: number; offset?: number; enabled?: boolean } = {},
) {
  const { path, limit = 50, offset = 0, enabled = true } = options;
  return useQuery({
    queryKey: [...PROJECT_QUERY_BASE, folderId, 'git', 'log', path ?? null, limit, offset],
    queryFn: () =>
      apiClient.get<ProjectGitCommit[]>(`/folders/${folderId}/project/git/log`, {
        ...(path ? { path } : {}),
        limit,
        offset,
      } as Record<string, string | number | boolean | undefined>),
    enabled: !!folderId && enabled,
  });
}

export function useProjectGitShow(
  folderId: string | null | undefined,
  commit: string | null | undefined,
  path: string | null | undefined,
  enabled: boolean = true,
) {
  return useQuery({
    queryKey: [...PROJECT_QUERY_BASE, folderId, 'git', 'show', commit, path],
    queryFn: () =>
      apiClient.get<ProjectGitShowResponse>(`/folders/${folderId}/project/git/show`, {
        commit: commit!,
        path: path!,
      } as Record<string, string | number | boolean | undefined>),
    enabled: !!folderId && !!commit && !!path && enabled,
  });
}

export function useProjectGitDiff(
  folderId: string | null | undefined,
  options: {
    commit?: string | null;
    path?: string | null;
    againstWorktree?: boolean;
    enabled?: boolean;
  } = {},
) {
  const { commit = null, path = null, againstWorktree = false, enabled = true } = options;
  return useQuery({
    queryKey: [...PROJECT_QUERY_BASE, folderId, 'git', 'diff', commit, path, againstWorktree],
    queryFn: () =>
      apiClient.get<ProjectGitDiffResponse>(`/folders/${folderId}/project/git/diff`, {
        ...(commit ? { commit } : {}),
        ...(path ? { path } : {}),
        against_worktree: againstWorktree ? 'true' : 'false',
      } as Record<string, string | number | boolean | undefined>),
    enabled: !!folderId && enabled && (!!commit || againstWorktree),
  });
}

export function useProjectGitStatus(folderId: string | null | undefined, enabled: boolean = true) {
  return useQuery({
    queryKey: [...PROJECT_QUERY_BASE, folderId, 'git', 'status'],
    queryFn: () =>
      apiClient.get<ProjectGitStatusEntry[]>(`/folders/${folderId}/project/git/status`),
    enabled: !!folderId && enabled,
    refetchInterval: 15_000,
  });
}

export function useUpdateFolderProject(folderId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: UpdateProjectModeInput) =>
      apiClient.patch(`/folders/${folderId}/project`, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['folders'] });
      qc.invalidateQueries({ queryKey: [...PROJECT_QUERY_BASE, folderId] });
    },
  });
}

export function useInitProjectGit(folderId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiClient.post(`/folders/${folderId}/project/git/init`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [...PROJECT_QUERY_BASE, folderId] });
    },
  });
}
