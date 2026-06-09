import { useTranslation } from 'react-i18next';
import { useChatStore } from '@/stores/chat';
import { useCheckpointResume } from '@/hooks/useCheckpointResume';
import type { TerminalReason } from '@/types/chat';

function reasonLabel(reason: TerminalReason, t: (k: string, opts?: { defaultValue?: string }) => string): string | null {
  switch (reason) {
    case 'max_turns':
      return t('chat.errors.maxTurns', { defaultValue: 'The agent reached its turn limit.' });
    case 'token_budget_exceeded':
      return t('chat.errors.tokenBudgetExceeded', { defaultValue: 'Token budget exceeded.' });
    case 'prompt_too_long':
      return t('chat.errors.promptTooLong', { defaultValue: 'Conversation too long for context window.' });
    case 'model_error':
      return t('chat.errors.modelError', { defaultValue: 'The model returned an error.' });
    default:
      return null;
  }
}

/**
 * Informational banner shown after the agent stream ends with a
 * non-`completed` terminal reason. When a `checkpoint_id` is available
 * it shows a "Continue" button to resume the paused run.
 */
export function ChatTerminalReasonBanner() {
  const { t } = useTranslation();
  const lastReason = useChatStore((s) => s.lastTerminalReason) as TerminalReason | null;
  const checkpointId = useChatStore((s) => s.lastCheckpointId);
  const isStreaming = useChatStore((s) => s.isStreaming);
  const sessionId = useChatStore((s) => s.currentSessionId);
  const resumeFromCheckpoint = useCheckpointResume(t);

  if (!lastReason || lastReason === 'completed' || lastReason === 'awaiting_user_input' || isStreaming) {
    return null;
  }

  const label = reasonLabel(lastReason, t);
  if (!label) return null;

  const canResume = !!checkpointId && !!sessionId;

  return (
    <div className="flex items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-800 dark:border-amber-700/40 dark:bg-amber-900/20 dark:text-amber-200 mb-2">
      <span className="flex-1">{label}</span>
      {canResume && (
        <button
          type="button"
          onClick={() => void resumeFromCheckpoint(sessionId)}
          className="shrink-0 rounded-md bg-amber-600 px-3 py-1 text-xs font-medium text-white hover:bg-amber-700 transition-colors dark:bg-amber-500 dark:hover:bg-amber-600"
        >
          {t('common.continue', { defaultValue: 'Continue' })}
        </button>
      )}
      <button
        type="button"
        onClick={() => useChatStore.setState({ lastTerminalReason: null })}
        className="shrink-0 text-amber-500 hover:text-amber-700 dark:text-amber-400 dark:hover:text-amber-200"
        aria-label="Dismiss"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <path d="M4 4l8 8M12 4l-8 8" />
        </svg>
      </button>
    </div>
  );
}
