import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertCircle,
  Check,
  ChevronDown,
  ChevronRight,
  Circle,
  Loader2,
  MinusCircle,
  Pin,
  PinOff,
  X,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { TaskProgressStatus, TaskProgressStep } from '@/types/chat';
import { nextTodoStatusOnClick, todoStatusI18nKey } from './todoStatusUtils';

export function sortTodoSteps(steps: TaskProgressStep[]): TaskProgressStep[] {
  if (!steps.length) return [];
  return [...steps].sort((a, b) => {
    const ao = a.order ?? 0;
    const bo = b.order ?? 0;
    if (ao !== bo) return ao - bo;
    return a.taskId.localeCompare(b.taskId);
  });
}

function TodoStatusIcon({ status }: { status: TaskProgressStep['status'] }) {
  if (status === 'completed') {
    return <Check className="h-3.5 w-3.5 shrink-0 text-mint-500" aria-hidden />;
  }
  if (status === 'failed') {
    return <AlertCircle className="h-3.5 w-3.5 shrink-0 text-red-500" aria-hidden />;
  }
  if (status === 'cancelled') {
    return <MinusCircle className="h-3.5 w-3.5 shrink-0 text-muted-foreground-tertiary" aria-hidden />;
  }
  if (status === 'in_progress') {
    return (
      <Loader2
        className="h-3.5 w-3.5 shrink-0 text-sky-500 animate-spin motion-reduce:animate-none"
        aria-hidden
      />
    );
  }
  return <Circle className="h-3.5 w-3.5 shrink-0 text-muted-foreground-tertiary" aria-hidden />;
}

export interface TodoListBlockProps {
  steps: TaskProgressStep[];
  isStreaming?: boolean;
  variant?: 'inline' | 'pinned';
  interactive?: boolean;
  /** When set, status clicks persist via chat store. */
  sessionId?: string;
  onStatusChange?: (taskId: string, status: TaskProgressStatus) => void | Promise<void>;
  showPin?: boolean;
  showUnpin?: boolean;
  showClose?: boolean;
  onPin?: () => void;
  onUnpin?: () => void;
  onClose?: () => void;
  className?: string;
}

export function TodoListBlock({
  steps,
  isStreaming = false,
  variant = 'inline',
  interactive = false,
  sessionId,
  onStatusChange,
  showPin = false,
  showUnpin = false,
  showClose = false,
  onPin,
  onUnpin,
  onClose,
  className,
}: TodoListBlockProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(true);
  const [busyTaskId, setBusyTaskId] = useState<string | null>(null);

  const sortedSteps = useMemo(() => sortTodoSteps(steps), [steps]);
  const completedCount = sortedSteps.filter((item) => item.status === 'completed').length;
  const canInteract = interactive && Boolean(sessionId || onStatusChange);

  const handleStatusClick = useCallback(
    async (step: TaskProgressStep) => {
      if (!canInteract || busyTaskId) return;
      const nextStatus = nextTodoStatusOnClick(step.status);
      if (nextStatus === step.status) return;

      setBusyTaskId(step.taskId);
      try {
        await onStatusChange?.(step.taskId, nextStatus);
      } finally {
        setBusyTaskId(null);
      }
    },
    [busyTaskId, canInteract, onStatusChange],
  );

  if (sortedSteps.length === 0) {
    return null;
  }

  const titleKey = variant === 'pinned' ? 'chat.sessionTodos.pinnedTitle' : 'chat.sessionTodos.title';

  return (
    <div
      className={cn(
        'rounded-xl border border-border-subtle/80 bg-surface-sunken/50',
        variant === 'pinned' &&
          'border-border-subtle/60 bg-surface/65 shadow-md ring-1 ring-black/[0.04] backdrop-blur-md backdrop-saturate-150 dark:bg-surface/55 dark:ring-white/[0.06]',
        className,
      )}
    >
      <div className="flex items-center gap-1 px-2 py-1.5">
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
          <span className="truncate text-xs font-medium text-foreground/90">
            {t(titleKey, { defaultValue: variant === 'pinned' ? 'Pinned tasks' : 'Tasks' })}
          </span>
          <span className="ml-auto shrink-0 text-xs tabular-nums text-muted-foreground-tertiary">
            {t('chat.sessionTodos.completed', {
              defaultValue: '{{done}}/{{total}} completed',
              done: completedCount,
              total: sortedSteps.length,
            })}
          </span>
        </button>
        {showPin ? (
          <button
            type="button"
            onClick={onPin}
            className="rounded-md p-1.5 text-muted-foreground-tertiary hover:bg-muted/40 hover:text-foreground"
            title={t('chat.sessionTodos.pin', { defaultValue: 'Pin to top' })}
            aria-label={t('chat.sessionTodos.pin', { defaultValue: 'Pin to top' })}
          >
            <Pin className="h-3.5 w-3.5" />
          </button>
        ) : null}
        {showUnpin ? (
          <button
            type="button"
            onClick={onUnpin}
            className="rounded-md p-1.5 text-muted-foreground-tertiary hover:bg-muted/40 hover:text-foreground"
            title={t('chat.sessionTodos.unpin', { defaultValue: 'Unpin' })}
            aria-label={t('chat.sessionTodos.unpin', { defaultValue: 'Unpin' })}
          >
            <PinOff className="h-3.5 w-3.5" />
          </button>
        ) : null}
        {showClose ? (
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground-tertiary hover:bg-muted/40 hover:text-foreground"
            title={t('chat.sessionTodos.close', { defaultValue: 'Close' })}
            aria-label={t('chat.sessionTodos.close', { defaultValue: 'Close' })}
          >
            <X className="h-3.5 w-3.5" />
          </button>
        ) : null}
      </div>

      {expanded ? (
        <div className="space-y-1 border-t border-border-subtle px-2 py-2">
          {sortedSteps.map((step) => {
            const statusLabel = t(todoStatusI18nKey(step.status), {
              defaultValue: step.status.replace('_', ' '),
            });
            const nextStatus = nextTodoStatusOnClick(step.status);
            const nextLabel = t(todoStatusI18nKey(nextStatus), {
              defaultValue: nextStatus.replace('_', ' '),
            });
            const rowBusy = busyTaskId === step.taskId;

            return (
              <div
                key={step.taskId}
                className={cn(
                  'group flex min-w-0 items-start gap-2 rounded-lg px-1 py-1 text-sm',
                  canInteract && 'hover:bg-muted/30',
                  step.status === 'in_progress' && 'bg-sky-500/5',
                )}
              >
                {canInteract ? (
                  <button
                    type="button"
                    disabled={rowBusy}
                    onClick={() => void handleStatusClick(step)}
                    className={cn(
                      'mt-0.5 rounded-md p-0.5 transition-colors',
                      'hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40',
                      rowBusy && 'opacity-50',
                    )}
                    title={t('chat.sessionTodos.cycleStatus', {
                      defaultValue: 'Mark as {{status}}',
                      status: nextLabel,
                    })}
                    aria-label={t('chat.sessionTodos.cycleStatus', {
                      defaultValue: 'Mark as {{status}}',
                      status: nextLabel,
                    })}
                  >
                    <TodoStatusIcon status={step.status} />
                  </button>
                ) : (
                  <span className="mt-0.5">
                    <TodoStatusIcon status={step.status} />
                  </span>
                )}
                <button
                  type="button"
                  disabled={!canInteract || rowBusy}
                  onClick={() => void handleStatusClick(step)}
                  className={cn(
                    'min-w-0 flex-1 text-left',
                    canInteract && 'cursor-pointer',
                    !canInteract && 'cursor-default',
                    (step.status === 'completed' || step.status === 'cancelled') &&
                      'text-muted-foreground line-through',
                    step.status !== 'completed' &&
                      step.status !== 'cancelled' &&
                      'text-foreground/95',
                  )}
                >
                  {step.label}
                </button>
                <span
                  className={cn(
                    'shrink-0 text-[11px] tabular-nums',
                    step.status === 'in_progress'
                      ? 'font-medium text-sky-600 dark:text-sky-400'
                      : 'text-muted-foreground-tertiary',
                    canInteract && 'opacity-70 group-hover:opacity-100',
                  )}
                >
                  {step.progress !== undefined ? `${Math.round(step.progress)}%` : statusLabel}
                </span>
              </div>
            );
          })}
          {isStreaming ? (
            <div className="px-1 pt-1 text-xs text-muted-foreground-tertiary">
              {t('chat.sessionTodos.inProgress', { defaultValue: 'Updating in real time' })}
            </div>
          ) : null}
        </div>
      ) : (
        <div className="border-t border-border-subtle px-3 py-2 text-xs text-muted-foreground-tertiary">
          {t('chat.sessionTodos.collapsed', {
            defaultValue: '{{count}} tasks',
            count: sortedSteps.length,
          })}
        </div>
      )}
    </div>
  );
}
