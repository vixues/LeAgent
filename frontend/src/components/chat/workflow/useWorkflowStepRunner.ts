import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { apiClient } from '@/api/client';
import { useChatStore } from '@/stores/chat';

interface RunStepResult {
  success: boolean;
  data?: unknown;
  error?: string | null;
}

/**
 * Executes persisted chat workflow steps via the verified HTTP endpoint.
 */
export function useWorkflowStepRunner(sessionId: string) {
  const { t } = useTranslation();
  const updateStep = useChatStore((s) => s.updateWorkflowStepRun);

  const runStep = useCallback(
    async (messageId: string, stepId: string, workflowDigest: string, userInput?: string) => {
      updateStep(sessionId, messageId, stepId, { status: 'running', error: undefined });
      try {
        const res = await apiClient.post<RunStepResult>(
          `/chat/sessions/${sessionId}/workflow-steps/${encodeURIComponent(stepId)}/run`,
          {
            message_id: messageId,
            workflow_digest: workflowDigest,
            user_input: userInput?.trim() ?? '',
          },
        );
        if (res.success) {
          updateStep(sessionId, messageId, stepId, { status: 'success' });
        } else {
          updateStep(sessionId, messageId, stepId, {
            status: 'error',
            error: res.error || t('chat.workflow.runFailed'),
          });
        }
      } catch (e) {
        updateStep(sessionId, messageId, stepId, {
          status: 'error',
          error: e instanceof Error ? e.message : t('chat.workflow.runFailed'),
        });
      }
    },
    [sessionId, updateStep, t],
  );

  return { runStep };
}
