import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { MessageCircleQuestion, Send } from 'lucide-react';

import { Button } from '@/components/ui';
import { useExecutionResume } from '@/hooks/useExecutionResume';

import { useExecutionOverlay } from '../store/executionOverlay';

/**
 * Shown when a run pauses on a blocking node (agent `awaiting_user_input` or
 * human review). Displays the agent's question and posts the answer to the
 * prompt resume endpoint; the resumed run streams back over the same
 * execution WebSocket.
 */
export function ResumePanel() {
  const { t } = useTranslation();
  const resumeExecution = useExecutionResume(t);
  const promptId = useExecutionOverlay((s) => s.promptId);
  const blocked = useExecutionOverlay((s) => s.blocked);
  const setBlockedForPrompt = useExecutionOverlay((s) => s.setBlocked);
  const [answer, setAnswer] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!blocked || !promptId) return null;

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await resumeExecution({
        scope: 'workflow',
        promptId,
        checkpointId: blocked.checkpointId,
        answer,
      });
      setBlockedForPrompt(promptId, null);
      setAnswer('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Resume failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="absolute bottom-4 left-1/2 z-40 w-[480px] max-w-[90%] -translate-x-1/2 rounded-lg border border-amber-300 bg-surface p-3 shadow-xl dark:border-amber-700">
      <div className="mb-2 flex items-center gap-2 text-sm font-medium text-foreground">
        <MessageCircleQuestion className="h-4 w-4 text-amber-500" />
        {t('resume.title', 'The workflow is waiting for your input')}
      </div>
      {blocked.question && (
        <p className="mb-2 max-h-32 overflow-auto whitespace-pre-wrap rounded bg-muted/40 px-2 py-1.5 text-xs text-muted-foreground">
          {blocked.question}
        </p>
      )}
      <div className="flex items-end gap-2">
        <textarea
          className="min-h-[40px] flex-1 resize-y rounded border border-border bg-background px-2 py-1.5 text-xs outline-none"
          placeholder={t('resume.answerPlaceholder', 'Type your answer...')}
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              void submit();
            }
          }}
        />
        <Button
          size="sm"
          leftIcon={<Send className="h-3.5 w-3.5" />}
          onClick={() => void submit()}
          disabled={submitting || !answer.trim()}
        >
          {t('resume.send', 'Resume')}
        </Button>
      </div>
      {error && <p className="mt-1 text-xs text-red-500">{error}</p>}
    </div>
  );
}
