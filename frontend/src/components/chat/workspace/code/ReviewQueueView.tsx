/**
 * Review queue sub-tab: worktree change reviews awaiting a human
 * approve / reject decision (Codex Review Queue parity). Approving a
 * pending review merges the agent's worktree branch back into the base
 * branch; rejecting discards it.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Check,
  ChevronDown,
  ChevronRight,
  GitBranch,
  GitMerge,
  Loader2,
  ShieldCheck,
  X,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/stores/chat';
import { useChatDraftStore } from '@/stores/chatDraft';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/api/client';
import {
  changeReviewsQueryKey,
  useApproveChangeReview,
  useChangeReviewDiff,
  useChangeReviews,
  useRejectChangeReview,
  useSetWorkspaceMode,
  useWorkspaceMode,
  type ChangeReview,
} from '@/hooks/useChangeReviews';

const STATUS_STYLES: Record<ChangeReview['status'], string> = {
  pending: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  approved: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  merged: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  rejected: 'bg-rose-500/15 text-rose-500',
  failed: 'bg-rose-500/15 text-rose-500',
};

function WorktreeModeBar() {
  const { t } = useTranslation();
  const currentSessionId = useChatStore((s) => s.currentSessionId);
  const projectFolderPath = useChatDraftStore((s) => s.projectFolderPath);
  const workspaceMode = useWorkspaceMode(currentSessionId);
  const setMode = useSetWorkspaceMode(currentSessionId);
  const qc = useQueryClient();

  const createReview = useMutation({
    mutationFn: () =>
      apiClient.post(`/chat/sessions/${currentSessionId}/change-reviews`, {}),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: changeReviewsQueryKey(currentSessionId) });
    },
  });

  const mode = workspaceMode.data?.mode ?? 'direct';
  const isWorktree = mode === 'worktree';

  return (
    <div className="flex shrink-0 items-center gap-2 rounded-lg border border-border-subtle/50 bg-surface-sunken/40 px-2.5 py-1.5 text-[11px]">
      <GitBranch className="size-3 shrink-0 text-muted-foreground" aria-hidden />
      <span className="text-muted-foreground">
        {t('chat.workspace.agent.review.workspaceMode', { defaultValue: 'Workspace' })}
      </span>
      <button
        type="button"
        disabled={setMode.isPending || (!isWorktree && !projectFolderPath)}
        onClick={() =>
          setMode.mutate(
            isWorktree
              ? { mode: 'direct' }
              : { mode: 'worktree', projectPath: projectFolderPath ?? '' },
          )
        }
        className={cn(
          'rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase transition-colors disabled:opacity-50',
          isWorktree
            ? 'bg-violet-500/15 text-violet-600 dark:text-violet-400'
            : 'bg-zinc-500/15 text-muted-foreground hover:text-foreground',
        )}
        title={
          !isWorktree && !projectFolderPath
            ? t('chat.workspace.agent.review.needProject', {
                defaultValue: 'Bind a project folder first.',
              })
            : undefined
        }
      >
        {isWorktree
          ? t('chat.workspace.agent.review.modeWorktree', { defaultValue: 'worktree' })
          : t('chat.workspace.agent.review.modeDirect', { defaultValue: 'direct' })}
      </button>
      {isWorktree && workspaceMode.data?.worktrees[0]?.branch && (
        <code className="truncate rounded bg-surface-sunken px-1 py-0.5 text-[10px] text-muted-foreground">
          {workspaceMode.data.worktrees[0].branch}
        </code>
      )}
      {isWorktree && (
        <button
          type="button"
          disabled={createReview.isPending}
          onClick={() => createReview.mutate()}
          className="ml-auto flex items-center gap-1 rounded-md border border-border-subtle px-2 py-0.5 text-[10px] font-medium text-muted-foreground transition-colors hover:bg-surface-sunken hover:text-foreground disabled:opacity-50"
        >
          {createReview.isPending ? (
            <Loader2 className="size-3 animate-spin" aria-hidden />
          ) : (
            <GitMerge className="size-3" aria-hidden />
          )}
          {t('chat.workspace.agent.review.submit', { defaultValue: 'Submit for review' })}
        </button>
      )}
    </div>
  );
}

export function ReviewQueueView() {
  const { t } = useTranslation();
  const currentSessionId = useChatStore((s) => s.currentSessionId);
  const reviews = useChangeReviews(currentSessionId);
  const approve = useApproveChangeReview(currentSessionId);
  const reject = useRejectChangeReview(currentSessionId);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const diff = useChangeReviewDiff(expandedId);

  const items = reviews.data ?? [];

  if (reviews.isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center p-6">
        <Loader2 className="size-4 animate-spin text-muted-foreground" aria-hidden />
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="flex min-h-0 flex-1 flex-col gap-1.5">
        <WorktreeModeBar />
        <div className="flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center">
          <ShieldCheck className="size-5 text-muted-foreground/50" aria-hidden />
          <p className="max-w-[240px] text-xs leading-relaxed text-muted-foreground">
            {t('chat.workspace.agent.review.empty', {
              defaultValue:
                'No change reviews. Worktree runs land here for approve / reject before merging.',
            })}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-1.5">
      <WorktreeModeBar />
      <div className="chat-sessions-scroll -mr-1 min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1">
      {items.map((review) => {
        const expanded = expandedId === review.id;
        const busy = approve.isPending || reject.isPending;
        return (
          <div
            key={review.id}
            className="rounded-lg border border-border-subtle/50 bg-surface-sunken/40"
          >
            <button
              type="button"
              onClick={() => setExpandedId(expanded ? null : review.id)}
              className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-[11px]"
              aria-expanded={expanded}
            >
              {expanded ? (
                <ChevronDown className="size-3 shrink-0 text-muted-foreground" aria-hidden />
              ) : (
                <ChevronRight className="size-3 shrink-0 text-muted-foreground" aria-hidden />
              )}
              <GitBranch className="size-3 shrink-0 text-muted-foreground" aria-hidden />
              <span className="min-w-0 flex-1 truncate font-medium text-foreground">
                {review.title}
              </span>
              <span className="shrink-0 tabular-nums text-[10px] text-muted-foreground">
                <span className="text-emerald-500">+{review.additions}</span>{' '}
                <span className="text-rose-500">-{review.deletions}</span>
              </span>
              <span
                className={cn(
                  'shrink-0 rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase',
                  STATUS_STYLES[review.status],
                )}
              >
                {t(`chat.workspace.agent.review.status.${review.status}`, {
                  defaultValue: review.status,
                })}
              </span>
            </button>

            {expanded && (
              <div className="space-y-2 border-t border-border-subtle/40 px-2.5 py-2">
                {review.branch && (
                  <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                    <GitMerge className="size-3" aria-hidden />
                    <code className="rounded bg-surface-sunken px-1 py-0.5">
                      {review.branch}
                    </code>
                    {review.base_branch && (
                      <>
                        <span>→</span>
                        <code className="rounded bg-surface-sunken px-1 py-0.5">
                          {review.base_branch}
                        </code>
                      </>
                    )}
                  </div>
                )}
                {review.summary && (
                  <p className="text-[11px] leading-relaxed text-muted-foreground">
                    {review.summary}
                  </p>
                )}

                <div className="max-h-[240px] overflow-auto rounded border border-border-subtle/40 bg-[#0c0c0e] p-2 font-mono text-[10px] leading-relaxed">
                  {diff.isLoading ? (
                    <Loader2 className="size-3 animate-spin text-zinc-500" aria-hidden />
                  ) : diff.data?.diff ? (
                    diff.data.diff.split('\n').map((line, i) => (
                      <div
                        key={i}
                        className={cn(
                          'whitespace-pre',
                          line.startsWith('+') && !line.startsWith('+++')
                            ? 'text-emerald-400'
                            : line.startsWith('-') && !line.startsWith('---')
                              ? 'text-rose-400'
                              : line.startsWith('@@')
                                ? 'text-cyan-400'
                                : 'text-zinc-400',
                        )}
                      >
                        {line || ' '}
                      </div>
                    ))
                  ) : (
                    <span className="text-zinc-500">
                      {t('chat.workspace.agent.review.noDiff', {
                        defaultValue: 'Diff unavailable.',
                      })}
                    </span>
                  )}
                </div>

                {review.status === 'pending' && (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => approve.mutate(review.id)}
                      className="flex items-center gap-1 rounded-md bg-emerald-600 px-2.5 py-1 text-[11px] font-medium text-white transition-colors hover:bg-emerald-500 disabled:opacity-50"
                    >
                      <Check className="size-3" aria-hidden />
                      {t('chat.workspace.agent.review.approve', {
                        defaultValue: 'Approve & merge',
                      })}
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => reject.mutate({ reviewId: review.id })}
                      className="flex items-center gap-1 rounded-md border border-border-subtle px-2.5 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-surface-sunken hover:text-foreground disabled:opacity-50"
                    >
                      <X className="size-3" aria-hidden />
                      {t('chat.workspace.agent.review.reject', {
                        defaultValue: 'Reject',
                      })}
                    </button>
                  </div>
                )}
                {review.reject_reason && (
                  <p className="text-[10px] text-rose-400">{review.reject_reason}</p>
                )}
              </div>
            )}
          </div>
        );
      })}
      </div>
    </div>
  );
}
