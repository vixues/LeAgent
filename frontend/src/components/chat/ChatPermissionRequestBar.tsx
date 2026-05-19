import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FileKey, Shield, SlidersHorizontal, Wrench, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { isChatStreamBusyForSession, useChatStore } from '@/stores/chat';
import type { UserInputPermissionKind, UserInputQuestion } from '@/types/chat';

interface ChatPermissionRequestBarProps {
  onSubmitAnswers: (answers: Record<string, string | string[]>) => void | Promise<void>;
  className?: string;
}

function PermissionKindIcon({
  kind,
  className,
}: {
  kind: UserInputPermissionKind | undefined;
  className?: string;
}) {
  const k = kind ?? 'generic';
  const cls = cn('h-4 w-4 shrink-0', className);
  switch (k) {
    case 'file_access':
      return <FileKey className={cls} aria-hidden />;
    case 'tool_run':
      return <Wrench className={cls} aria-hidden />;
    case 'mode_change':
      return <SlidersHorizontal className={cls} aria-hidden />;
    default:
      return <Shield className={cls} aria-hidden />;
  }
}

export function ChatPermissionRequestBar({
  onSubmitAnswers,
  className,
}: ChatPermissionRequestBarProps) {
  const { t } = useTranslation();
  const pending = useChatStore((s) => s.pendingUserInput);
  const currentSessionId = useChatStore((s) => s.currentSessionId);
  const clearPending = useChatStore((s) => s.clearPendingUserInput);
  const streamBusyForSession = useChatStore((s) =>
    isChatStreamBusyForSession(s.currentSessionId, {
      activeStreamSessionId: s.activeStreamSessionId,
      isLoading: s.isLoading,
      isStreaming: s.isStreaming,
    }),
  );

  const [customNote, setCustomNote] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const activeQuestion = useMemo((): UserInputQuestion | null => {
    if (!pending || !currentSessionId || pending.sessionId !== currentSessionId) return null;
    if (pending.questions.length !== 1) return null;
    const q = pending.questions[0];
    if (!q) return null;
    if (q.ui_variant !== 'permission') return null;
    return q;
  }, [pending, currentSessionId]);

  const kindLabel = useCallback(
    (q: UserInputQuestion) => {
      const pk = q.permission_kind ?? 'generic';
      const map: Record<UserInputPermissionKind, string> = {
        file_access: t('chat.userInput.permission.kindFileAccess'),
        tool_run: t('chat.userInput.permission.kindToolRun'),
        mode_change: t('chat.userInput.permission.kindModeChange'),
        generic: t('chat.userInput.permission.kindGeneric'),
      };
      return map[pk];
    },
    [t],
  );

  const resetLocal = useCallback(() => {
    setCustomNote('');
  }, []);

  const handleDismiss = useCallback(() => {
    resetLocal();
    clearPending();
  }, [clearPending, resetLocal]);

  const submit = useCallback(
    async (value: string) => {
      if (!activeQuestion) return;
      if (streamBusyForSession || submitting) return;
      setSubmitting(true);
      try {
        await onSubmitAnswers({ [activeQuestion.id]: value });
        resetLocal();
      } finally {
        setSubmitting(false);
      }
    },
    [activeQuestion, onSubmitAnswers, resetLocal, streamBusyForSession, submitting],
  );

  const handleAllow = useCallback(() => {
    if (!activeQuestion) return;
    const q = activeQuestion;
    if (q.allow_custom && customNote.trim()) {
      void submit(customNote.trim());
      return;
    }
    void submit('allow');
  }, [activeQuestion, customNote, submit]);

  const handleDeny = useCallback(() => {
    void submit('deny');
  }, [submit]);

  if (!activeQuestion) return null;

  const q = activeQuestion;
  const disabled = streamBusyForSession || submitting;
  const allowLabel = q.primary_choice ?? t('chat.userInput.permission.allow');
  const denyLabel = q.secondary_choice ?? t('chat.userInput.permission.deny');

  return (
    <div
      className={cn(
        'border-b border-border-subtle bg-surface-sunken/50 px-3 py-3',
        className,
      )}
      role="region"
      aria-live="polite"
      aria-label={t('chat.userInput.permission.regionLabel')}
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="flex min-w-0 flex-1 gap-2.5">
          <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border-subtle bg-surface text-primary">
            <PermissionKindIcon kind={q.permission_kind} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
              <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                {kindLabel(q)}
              </span>
            </div>
            <p className="mt-0.5 text-sm font-medium leading-snug text-foreground">{q.prompt}</p>
            {q.detail ? (
              <p className="mt-1 break-all font-mono text-xs text-muted-foreground">{q.detail}</p>
            ) : null}
          </div>
        </div>
        <button
          type="button"
          onClick={handleDismiss}
          disabled={disabled}
          className="rounded-md p-1 text-muted-foreground hover:bg-surface-sunken hover:text-foreground disabled:opacity-40"
          aria-label={t('chat.userInput.dismiss')}
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {q.allow_custom ? (
        <label className="mb-3 block">
          <span className="sr-only">{t('chat.userInput.permission.customHint')}</span>
          <input
            type="text"
            disabled={disabled}
            value={customNote}
            onChange={(e) => setCustomNote(e.target.value)}
            className={cn(
              'w-full rounded-md border border-border-subtle bg-surface px-2.5 py-1.5 text-sm text-foreground',
              'placeholder:text-muted-foreground-tertiary focus:border-primary focus:outline-none',
              disabled && 'opacity-50',
            )}
            placeholder={t('chat.userInput.permission.customHint')}
          />
        </label>
      ) : null}

      <div className="flex flex-wrap items-center justify-end gap-2">
        <button
          type="button"
          onClick={handleDismiss}
          disabled={disabled}
          className="rounded-md px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-surface-sunken"
        >
          {t('chat.userInput.cancel')}
        </button>
        <button
          type="button"
          onClick={handleDeny}
          disabled={disabled}
          className="rounded-md border border-border-subtle bg-surface px-3 py-1.5 text-xs font-medium text-foreground hover:bg-surface-sunken"
        >
          {denyLabel}
        </button>
        <button
          type="button"
          onClick={() => void handleAllow()}
          disabled={disabled}
          className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:opacity-90"
        >
          {allowLabel}
        </button>
      </div>
    </div>
  );
}
