/**
 * Change-review queue hooks (Codex Review Queue parity).
 *
 * Backend endpoints (leagent/api/v1/chat/reviews.py):
 *  - GET  /chat/sessions/{sessionId}/change-reviews
 *  - GET  /chat/change-reviews/{reviewId}/diff
 *  - POST /chat/change-reviews/{reviewId}/approve
 *  - POST /chat/change-reviews/{reviewId}/reject
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/api/client';

export type ChangeReviewStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'merged'
  | 'failed';

interface ChangeReviewsResponse {
  reviews: ChangeReview[];
}

export interface ChangeReview {
  id: string;
  session_id: string;
  run_id?: string | null;
  workspace_mode: string;
  worktree_path?: string | null;
  branch?: string | null;
  base_branch?: string | null;
  title: string;
  summary?: string | null;
  files_changed: number;
  additions: number;
  deletions: number;
  status: ChangeReviewStatus;
  created_at: string;
  decided_at?: string | null;
  decided_by?: string | null;
  reject_reason?: string | null;
}

const ROOT_KEY = ['change-reviews'] as const;

export interface WorktreeInfo {
  session_id: string;
  project_root: string;
  worktree_path: string;
  branch: string;
  base_branch: string;
  created_at: number;
}

export interface WorkspaceModeState {
  session_id: string;
  mode: 'direct' | 'worktree';
  worktrees: WorktreeInfo[];
}

export function workspaceModeQueryKey(sessionId: string | null | undefined) {
  return ['workspace-mode', sessionId ?? 'none'] as const;
}

export function useWorkspaceMode(sessionId: string | null | undefined) {
  return useQuery({
    queryKey: workspaceModeQueryKey(sessionId),
    queryFn: () =>
      apiClient.get<WorkspaceModeState>(`/chat/sessions/${sessionId}/workspace-mode`),
    enabled: Boolean(sessionId),
  });
}

export function useSetWorkspaceMode(sessionId: string | null | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      mode,
      projectPath,
    }: {
      mode: 'direct' | 'worktree';
      projectPath?: string;
    }) =>
      apiClient.post<WorkspaceModeState>(`/chat/sessions/${sessionId}/workspace-mode`, {
        mode,
        project_path: projectPath ?? '',
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: workspaceModeQueryKey(sessionId) });
    },
  });
}

export function changeReviewsQueryKey(sessionId: string | null | undefined) {
  return [...ROOT_KEY, sessionId ?? 'none'] as const;
}

export function useChangeReviews(sessionId: string | null | undefined) {
  return useQuery({
    queryKey: changeReviewsQueryKey(sessionId),
    queryFn: () =>
      apiClient.get<ChangeReviewsResponse>(
        `/chat/sessions/${sessionId}/change-reviews`,
      ),
    enabled: Boolean(sessionId),
    refetchInterval: 15_000,
    select: (data: ChangeReviewsResponse) => data.reviews ?? [],
  });
}

export function useChangeReviewDiff(reviewId: string | null) {
  return useQuery({
    queryKey: [...ROOT_KEY, 'diff', reviewId ?? 'none'],
    queryFn: () =>
      apiClient.get<{ diff: string; files: string[] }>(
        `/chat/change-reviews/${reviewId}/diff`,
      ),
    enabled: Boolean(reviewId),
    staleTime: 10_000,
  });
}

export function useApproveChangeReview(sessionId: string | null | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (reviewId: string) =>
      apiClient.post<ChangeReview>(`/chat/change-reviews/${reviewId}/approve`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: changeReviewsQueryKey(sessionId) });
    },
  });
}

export function useRejectChangeReview(sessionId: string | null | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ reviewId, reason }: { reviewId: string; reason?: string }) =>
      apiClient.post<ChangeReview>(`/chat/change-reviews/${reviewId}/reject`, {
        reason: reason ?? '',
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: changeReviewsQueryKey(sessionId) });
    },
  });
}
