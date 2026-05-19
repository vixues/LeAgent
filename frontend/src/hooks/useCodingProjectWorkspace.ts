/**
 * Read-only workspace API for coding projects (file tree, text preview, git).
 */
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/api/client';
import { CODING_PROJECTS_QUERY_ROOT } from '@/hooks/useCodingProjects';

export interface WorkspaceTreeNode {
  name: string;
  path: string;
  type: 'file' | 'dir';
  size?: number;
  children?: WorkspaceTreeNode[];
}

export interface WorkspaceTreeResponse {
  root: WorkspaceTreeNode;
  truncated: boolean;
}

export interface WorkspaceFileResponse {
  path: string;
  content: string;
  truncated: boolean;
  size: number;
}

export interface WorkspaceGitLine {
  status: string;
  xy: string;
  path: string;
}

export interface WorkspaceGitResponse {
  is_git: boolean;
  git_available: boolean;
  branch?: string | null;
  head?: string | null;
  head_full?: string | null;
  lines?: WorkspaceGitLine[];
  error?: string | null;
}

export function useCodingProjectTree(projectId: string | null | undefined) {
  return useQuery({
    queryKey: [...CODING_PROJECTS_QUERY_ROOT, 'workspace', projectId, 'tree'],
    queryFn: () =>
      apiClient.get<WorkspaceTreeResponse>(
        `/coding-projects/${projectId}/workspace/tree`,
      ),
    enabled: !!projectId,
    staleTime: 5_000,
  });
}

export function useCodingProjectFile(
  projectId: string | null | undefined,
  path: string | null | undefined,
) {
  return useQuery({
    queryKey: [
      ...CODING_PROJECTS_QUERY_ROOT,
      'workspace',
      projectId,
      'file',
      path,
    ],
    queryFn: () =>
      apiClient.get<WorkspaceFileResponse>(
        `/coding-projects/${projectId}/workspace/file`,
        { path: path! },
      ),
    enabled: Boolean(projectId && path && path.length > 0),
    staleTime: 3_000,
  });
}

export function useCodingProjectGit(projectId: string | null | undefined) {
  return useQuery({
    queryKey: [...CODING_PROJECTS_QUERY_ROOT, 'workspace', projectId, 'git'],
    queryFn: () =>
      apiClient.get<WorkspaceGitResponse>(
        `/coding-projects/${projectId}/workspace/git`,
      ),
    enabled: !!projectId,
    staleTime: 10_000,
  });
}

/** Invalidate all workspace queries for one project (tree, file, git). */
export function useInvalidateCodingProjectWorkspace() {
  const queryClient = useQueryClient();
  return (projectId: string) =>
    queryClient.invalidateQueries({
      queryKey: [...CODING_PROJECTS_QUERY_ROOT, 'workspace', projectId],
    });
}
