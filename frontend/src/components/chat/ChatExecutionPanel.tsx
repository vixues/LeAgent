import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useShallow } from 'zustand/react/shallow';
import {
  AlertCircle,
  Check,
  ChevronDown,
  ChevronRight,
  Loader2,
  MessageCircleQuestion,
  PinOff,
  Send,
  Wrench,
  X,
} from 'lucide-react';
import { apiClient } from '@/api/client';
import { useExecutionStream } from '@/features/workflow/api/useExecutionStream';
import { useExecutionOverlay } from '@/features/workflow/store/executionOverlay';
import { useExecutionResume } from '@/hooks/useExecutionResume';
import { cn } from '@/lib/utils';
import { isChatStreamBusyForSession, useChatStore } from '@/stores/chat';
import { useExecutionSessionStore } from '@/stores/executionSession';
import type { TaskProgressStep } from '@/types/chat';
import { TodoListBlock } from './TodoListBlock';

interface ChatExecutionPanelProps {
  sessionId: string | null | undefined;
  className?: string;
}

const EMPTY_TODOS: TaskProgressStep[] = [];

function WorkflowLiveStatus({ promptId }: { promptId: string }) {
  const { t } = useTranslation();
  useExecutionStream(promptId);
  const overlay = useExecutionOverlay((s) => s.overlays[promptId]);
  const nodes = overlay?.nodes ?? {};
  const runningNodes = Object.entries(nodes).filter(([, n]) => n.status === 'running');
  const blocked = overlay?.blocked;

  if (blocked) {
    return (
      <p className="text-xs text-amber-700 dark:text-amber-300">
        {t('chat.execution.panel.workflowBlocked')}
      </p>
    );
  }

  if (runningNodes.length === 0) {
    return (
      <p className="text-xs text-muted-foreground-tertiary">
        {overlay?.running
          ? t('chat.execution.panel.workflowRunning')
          : t('chat.execution.panel.workflowIdle')}
      </p>
    );
  }

  return (
    <ul className="space-y-1">
      {runningNodes.slice(0, 4).map(([nodeId]) => (
        <li key={nodeId} className="flex items-center gap-1.5 text-xs text-primary-700 dark:text-primary-300">
          <Loader2 className="h-3 w-3 shrink-0 animate-spin" aria-hidden />
          <span className="truncate font-mono">{nodeId}</span>
        </li>
      ))}
    </ul>
  );
}

/** Unified execution panel: todos, capability log, workflow status, resume controls. */
export function ChatExecutionPanel({ sessionId, className }: ChatExecutionPanelProps) {
  const { t } = useTranslation();
  const resumeExecution = useExecutionResume(t);
  const [resumeAnswer, setResumeAnswer] = useState('');
  const [resumeSubmitting, setResumeSubmitting] = useState(false);
  const [resumeError, setResumeError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(true);

  const todos = useChatStore(
    useShallow((state) => {
      if (!sessionId) return EMPTY_TODOS;
      return state.sessions.find((s) => s.id === sessionId)?.todos ?? EMPTY_TODOS;
    }),
  );

  const ui = useChatStore((state) => (sessionId ? state.sessionTodoUi[sessionId] : undefined));

  const isStreaming = useChatStore((state) =>
    sessionId ? isChatStreamBusyForSession(sessionId, state) : false,
  );

  const execution = useExecutionSessionStore((s) =>
    sessionId ? s.bySession[sessionId] : undefined,
  );

  const setSessionTodoPinned = useChatStore((s) => s.setSessionTodoPinned);
  const dismissSessionTodoPanel = useChatStore((s) => s.dismissSessionTodoPanel);
  const patchSessionTodoStatus = useChatStore((s) => s.patchSessionTodoStatus);

  const handleStatusChange = useCallback(
    (taskId: string, status: TaskProgressStep['status']) => {
      if (!sessionId) return Promise.resolve();
      return patchSessionTodoStatus(sessionId, taskId, status);
    },
    [patchSessionTodoStatus, sessionId],
  );

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    void apiClient
      .get<
        Array<{
          run_id: string;
          scope: string;
          parent_run_id?: string | null;
          prompt_id?: string | null;
          status?: string;
          pause_token?: Record<string, unknown> | null;
        }>
      >(`/chat/sessions/${sessionId}/executions`)
      .then((rows) => {
        if (!cancelled && rows.length > 0) {
          useExecutionSessionStore.getState().hydrateExecutions(sessionId, rows);
        }
      })
      .catch(() => {
        /* optional hydration */
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const capabilityLog = execution?.capabilityLog ?? [];
  const promptId = execution?.promptId ?? null;
  const overlayBlocked = useExecutionOverlay((s) =>
    promptId ? s.overlays[promptId]?.blocked : null,
  );

  const hasTodos = todos.length > 0;

  const pendingUserInput = useChatStore((s) => s.pendingUserInput);
  const lastCheckpointId = useChatStore((s) => s.lastCheckpointId);

  const showResumeChat = Boolean(
    pendingUserInput &&
      pendingUserInput.sessionId === sessionId &&
      pendingUserInput.checkpointId,
  );

  const showResumeWorkflow = Boolean(promptId && overlayBlocked);

  const showForTodos = hasTodos && ui?.pinned === true && !ui?.dismissed;

  const hasExecutionPanelContent =
    isStreaming ||
    execution?.status === 'blocked' ||
    capabilityLog.length > 0 ||
    Boolean(promptId) ||
    showResumeChat ||
    showResumeWorkflow;

  const showForExecution =
    hasExecutionPanelContent &&
    (!ui?.dismissed ||
      execution?.status === 'blocked' ||
      showResumeChat ||
      showResumeWorkflow);

  const handleResume = useCallback(async () => {
    if (!sessionId) return;
    setResumeSubmitting(true);
    setResumeError(null);
    try {
      if (showResumeWorkflow && promptId && overlayBlocked) {
        await resumeExecution({
          scope: 'workflow',
          promptId,
          checkpointId: overlayBlocked.checkpointId,
          answer: resumeAnswer,
        });
        useExecutionOverlay.getState().setBlocked(promptId, null);
      } else if (showResumeChat) {
        await resumeExecution({
          scope: 'chat_turn',
          sessionId,
          checkpointId: pendingUserInput?.checkpointId ?? lastCheckpointId ?? undefined,
          prompt: resumeAnswer,
        });
      }
      setResumeAnswer('');
    } catch (err) {
      setResumeError(
        err instanceof Error ? err.message : t('chat.execution.panel.resumeFailed'),
      );
    } finally {
      setResumeSubmitting(false);
    }
  }, [
    sessionId,
    showResumeWorkflow,
    promptId,
    overlayBlocked,
    resumeAnswer,
    resumeExecution,
    showResumeChat,
    pendingUserInput?.checkpointId,
    lastCheckpointId,
    t,
  ]);

  const panelTitle = useMemo(() => {
    if (execution?.status === 'blocked' || showResumeWorkflow) {
      return t('chat.execution.panel.titleBlocked');
    }
    if (isStreaming || execution?.status === 'running') {
      return t('chat.execution.panel.titleRunning');
    }
    return t('chat.execution.panel.title');
  }, [execution?.status, showResumeWorkflow, isStreaming, t]);

  if (!sessionId || (!showForTodos && !showForExecution)) {
    return null;
  }

  return (
    <div className={cn('chat-todo-panel-row', className)}>
      <div className="chat-composer-inner min-w-0">
        <div
          className={cn(
            'rounded-xl border border-border-subtle/80 bg-surface/65 shadow-md ring-1 ring-black/[0.04] backdrop-blur-md backdrop-saturate-150',
            'dark:bg-surface/55 dark:ring-white/[0.06]',
          )}
        >
          <div className="flex items-center gap-1 border-b border-border-subtle/80 px-2 py-1.5">
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="flex min-w-0 flex-1 items-center gap-2 rounded-md px-1 py-1 text-left hover:bg-muted/40"
              aria-expanded={expanded}
            >
              {expanded ? (
                <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground-tertiary" />
              ) : (
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground-tertiary" />
              )}
              <span className="truncate text-xs font-medium text-foreground/90">{panelTitle}</span>
              {isStreaming ? (
                <Loader2 className="ml-auto h-3.5 w-3.5 shrink-0 animate-spin text-sky-500" />
              ) : null}
            </button>
            {hasTodos ? (
              <button
                type="button"
                onClick={() => setSessionTodoPinned(sessionId, false)}
                className="rounded-md p-1.5 text-muted-foreground-tertiary hover:bg-muted/40 hover:text-foreground"
                title={t('chat.sessionTodos.unpin')}
                aria-label={t('chat.sessionTodos.unpin')}
              >
                <PinOff className="h-3.5 w-3.5" />
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => dismissSessionTodoPanel(sessionId)}
              className="rounded-md p-1.5 text-muted-foreground-tertiary hover:bg-muted/40 hover:text-foreground"
              title={t('chat.sessionTodos.close')}
              aria-label={t('chat.sessionTodos.close')}
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>

          {expanded ? (
            <div className="space-y-3 px-2 py-2">
              {hasTodos ? (
                <TodoListBlock
                  steps={todos}
                  isStreaming={isStreaming}
                  variant="pinned"
                  interactive
                  sessionId={sessionId}
                  onStatusChange={handleStatusChange}
                  className="border-0 bg-transparent shadow-none ring-0"
                />
              ) : null}

              {capabilityLog.length > 0 ? (
                <section>
                  <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground-tertiary">
                    {t('chat.execution.panel.capabilities')}
                  </h3>
                  <ul className="max-h-40 space-y-1 overflow-y-auto">
                    {capabilityLog.slice(-12).map((entry) => (
                      <li
                        key={entry.id}
                        className="flex items-center gap-2 rounded-md px-1 py-0.5 text-xs"
                      >
                        {entry.status === 'running' ? (
                          <Loader2 className="h-3 w-3 shrink-0 animate-spin text-sky-500" />
                        ) : entry.status === 'success' ? (
                          <Check className="h-3 w-3 shrink-0 text-mint-500" />
                        ) : entry.status === 'awaiting_user' ? (
                          <MessageCircleQuestion className="h-3 w-3 shrink-0 text-amber-500" />
                        ) : (
                          <AlertCircle className="h-3 w-3 shrink-0 text-red-500" />
                        )}
                        <Wrench className="h-3 w-3 shrink-0 text-muted-foreground-tertiary" />
                        <span className="min-w-0 flex-1 truncate font-mono">{entry.name}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}

              {promptId ? (
                <section>
                  <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground-tertiary">
                    {t('chat.execution.panel.workflow')}
                  </h3>
                  <WorkflowLiveStatus promptId={promptId} />
                </section>
              ) : null}

              {(showResumeChat || showResumeWorkflow) && (
                <section className="rounded-lg border border-amber-200/80 bg-amber-50/50 p-2 dark:border-amber-800/50 dark:bg-amber-950/20">
                  <p className="mb-2 text-xs font-medium text-amber-800 dark:text-amber-200">
                    {overlayBlocked?.question ??
                      t('chat.execution.panel.resumePrompt')}
                  </p>
                  <div className="flex items-end gap-2">
                    <textarea
                      className="min-h-[36px] flex-1 resize-y rounded border border-border bg-background px-2 py-1 text-xs outline-none"
                      placeholder={t('chat.execution.panel.resumePlaceholder')}
                      value={resumeAnswer}
                      onChange={(e) => setResumeAnswer(e.target.value)}
                    />
                    <button
                      type="button"
                      disabled={resumeSubmitting || !resumeAnswer.trim()}
                      onClick={() => void handleResume()}
                      className="inline-flex items-center gap-1 rounded-lg bg-primary-600 px-2.5 py-1.5 text-xs font-medium text-white disabled:opacity-50"
                    >
                      <Send className="h-3 w-3" />
                      {t('chat.execution.panel.resume')}
                    </button>
                  </div>
                  {resumeError ? (
                    <p className="mt-1 text-xs text-red-600 dark:text-red-400">{resumeError}</p>
                  ) : null}
                </section>
              )}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
