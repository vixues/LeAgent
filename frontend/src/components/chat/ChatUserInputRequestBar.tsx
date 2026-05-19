import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { MessageCircleQuestion, Send, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { isChatStreamBusyForSession, useChatStore } from '@/stores/chat';
import type { UserInputQuestion } from '@/types/chat';

interface ChatUserInputRequestBarProps {
  onSubmitAnswers: (answers: Record<string, string | string[]>) => void | Promise<void>;
  className?: string;
}

function validateAnswers(
  questions: UserInputQuestion[],
  raw: Record<string, string | string[]>,
  customByQid: Record<string, string>,
): boolean {
  for (const q of questions) {
    const customTrim = (customByQid[q.id] ?? '').trim();
    if (q.choices?.length) {
      const canCustomize = q.allow_custom !== false;
      if (q.multi_select) {
        const chips = Array.isArray(raw[q.id])
          ? (raw[q.id] as string[])
          : raw[q.id] !== undefined && raw[q.id] !== ''
            ? [String(raw[q.id])]
            : [];
        if (chips.length > 0) continue;
        if (canCustomize && customTrim) continue;
        return false;
      }
      const picked = raw[q.id];
      const pickedOk = typeof picked === 'string' && picked.length > 0;
      if (pickedOk) continue;
      if (canCustomize && customTrim) continue;
      return false;
    }

    const v = raw[q.id];
    if (v === undefined || v === '') return false;
    if (Array.isArray(v)) {
      if (v.length === 0) return false;
      continue;
    }
    if (String(v).trim().length === 0) return false;
  }
  return true;
}

function buildMergedAnswers(
  questions: UserInputQuestion[],
  raw: Record<string, string | string[]>,
  customByQid: Record<string, string>,
): Record<string, string | string[]> {
  const out: Record<string, string | string[]> = { ...raw };
  for (const q of questions) {
    if (!q.choices?.length) continue;
    if (q.allow_custom === false) continue;
    const ct = (customByQid[q.id] ?? '').trim();
    if (q.multi_select) {
      const base = Array.isArray(out[q.id])
        ? [...(out[q.id] as string[])]
        : out[q.id] !== undefined && out[q.id] !== ''
          ? [String(out[q.id])]
          : [];
      const merged = [...base];
      if (ct && !merged.includes(ct)) merged.push(ct);
      out[q.id] = merged;
    } else if (ct) {
      out[q.id] = ct;
    }
  }
  return out;
}

export function ChatUserInputRequestBar({
  onSubmitAnswers,
  className,
}: ChatUserInputRequestBarProps) {
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

  const [answers, setAnswers] = useState<Record<string, string | string[]>>({});
  const [customByQid, setCustomByQid] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  const active = useMemo(
    () =>
      pending && currentSessionId && pending.sessionId === currentSessionId ? pending : null,
    [pending, currentSessionId],
  );

  const resetLocal = useCallback(() => {
    setAnswers({});
    setCustomByQid({});
  }, []);

  const onToggleMulti = useCallback((qid: string, choice: string, checked: boolean) => {
    setAnswers((prev) => {
      const cur = prev[qid];
      const list = Array.isArray(cur) ? [...cur] : cur ? [String(cur)] : [];
      if (checked) {
        if (!list.includes(choice)) list.push(choice);
      } else {
        const i = list.indexOf(choice);
        if (i >= 0) list.splice(i, 1);
      }
      return { ...prev, [qid]: list };
    });
  }, []);

  const onPickSingle = useCallback((qid: string, choice: string) => {
    setCustomByQid((prev) => ({ ...prev, [qid]: '' }));
    setAnswers((prev) => ({ ...prev, [qid]: choice }));
  }, []);

  const onChoiceRowCustomChange = useCallback((qid: string, multi: boolean, value: string) => {
    setCustomByQid((prev) => ({ ...prev, [qid]: value }));
    if (!multi) {
      setAnswers((prev) => {
        const next = { ...prev };
        delete next[qid];
        return next;
      });
    }
  }, []);

  const onCustomChange = useCallback((qid: string, value: string) => {
    setAnswers((prev) => ({ ...prev, [qid]: value }));
  }, []);

  const handleDismiss = useCallback(() => {
    resetLocal();
    clearPending();
  }, [clearPending, resetLocal]);

  const handleSubmit = useCallback(async () => {
    if (!active) return;
    if (!validateAnswers(active.questions, answers, customByQid)) return;
    if (streamBusyForSession || submitting) return;
    setSubmitting(true);
    try {
      const payload = buildMergedAnswers(active.questions, answers, customByQid);
      await onSubmitAnswers(payload);
      resetLocal();
    } finally {
      setSubmitting(false);
    }
  }, [active, answers, customByQid, onSubmitAnswers, resetLocal, streamBusyForSession, submitting]);

  if (!active) return null;

  const disabled = streamBusyForSession || submitting;
  const canSubmit = validateAnswers(active.questions, answers, customByQid) && !disabled;

  return (
    <div
      className={cn(
        'border-b border-border-subtle bg-surface-sunken/50 px-3 py-3',
        className,
      )}
      role="region"
      aria-label={t('chat.userInput.regionLabel')}
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          <MessageCircleQuestion className="h-4 w-4 shrink-0 text-primary" aria-hidden />
          {t('chat.userInput.title')}
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

      <div className="flex max-h-[min(40vh,320px)] flex-col gap-3 overflow-y-auto">
        {active.questions.map((q) => (
          <div key={q.id} className="rounded-lg border border-border-subtle bg-surface px-3 py-2.5">
            <p className="text-sm font-medium text-foreground">{q.prompt}</p>

            {q.choices && q.choices.length > 0 ? (
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                {q.choices.map((c) => {
                  const multi = Boolean(q.multi_select);
                  const selected = multi
                    ? Array.isArray(answers[q.id]) && (answers[q.id] as string[]).includes(c)
                    : answers[q.id] === c;
                  return (
                    <button
                      key={c}
                      type="button"
                      disabled={disabled}
                      onClick={() =>
                        multi
                          ? onToggleMulti(q.id, c, !selected)
                          : onPickSingle(q.id, c)
                      }
                      className={cn(
                        'rounded-md border px-2.5 py-1 text-xs transition-colors',
                        selected
                          ? 'border-primary bg-primary-50 text-primary-900 dark:bg-primary-900/30 dark:text-primary-100'
                          : 'border-border-subtle bg-surface-sunken/60 text-muted-foreground hover:border-border',
                        disabled && 'opacity-50',
                      )}
                    >
                      {c}
                    </button>
                  );
                })}
                {q.allow_custom !== false ? (
                  <input
                    type="text"
                    disabled={disabled}
                    value={customByQid[q.id] ?? ''}
                    onChange={(e) =>
                      onChoiceRowCustomChange(q.id, Boolean(q.multi_select), e.target.value)
                    }
                    className={cn(
                      'min-w-[min(100%,140px)] max-w-full flex-1 basis-[140px] rounded-md border border-border-subtle bg-surface px-2 py-1 text-xs text-foreground',
                      'placeholder:text-muted-foreground-tertiary focus:border-primary focus:outline-none',
                      disabled && 'opacity-50',
                    )}
                    placeholder={t('chat.userInput.customPlaceholder')}
                    aria-label={t('chat.userInput.customLabel')}
                  />
                ) : null}
              </div>
            ) : q.allow_custom ? (
              <label className="mt-2 block text-xs text-muted-foreground">
                <span className="mb-1 block">{t('chat.userInput.customLabel')}</span>
                <input
                  type="text"
                  disabled={disabled}
                  value={typeof answers[q.id] === 'string' ? (answers[q.id] as string) : ''}
                  onChange={(e) => onCustomChange(q.id, e.target.value)}
                  className={cn(
                    'w-full rounded-md border border-border-subtle bg-surface px-2 py-1.5 text-sm text-foreground',
                    'placeholder:text-muted-foreground-tertiary focus:border-primary focus:outline-none',
                  )}
                  placeholder={t('chat.userInput.customPlaceholder')}
                />
              </label>
            ) : (
              <input
                type="text"
                disabled={disabled}
                value={typeof answers[q.id] === 'string' ? (answers[q.id] as string) : ''}
                onChange={(e) => onCustomChange(q.id, e.target.value)}
                className={cn(
                  'mt-2 w-full rounded-md border border-border-subtle bg-surface px-2 py-1.5 text-sm',
                )}
                placeholder={t('chat.userInput.answerPlaceholder')}
              />
            )}
          </div>
        ))}
      </div>

      <div className="mt-3 flex justify-end gap-2">
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
          onClick={() => void handleSubmit()}
          disabled={!canSubmit}
          className={cn(
            'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium',
            'bg-primary text-primary-foreground hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40',
          )}
        >
          <Send className="h-3.5 w-3.5" aria-hidden />
          {t('chat.userInput.submit')}
        </button>
      </div>
    </div>
  );
}
