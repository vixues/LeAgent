import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { runChatWorkflowStep } from './chatWorkflowRunActions';

/**
 * Executes persisted chat workflow steps via the verified HTTP endpoint.
 */
export function useWorkflowStepRunner(sessionId: string) {
  const { t } = useTranslation();

  const runStep = useCallback(
    async (messageId: string, stepId: string, workflowDigest: string, userInput?: string) => {
      await runChatWorkflowStep({
        sessionId,
        messageId,
        stepId,
        digest: workflowDigest,
        userInput,
        fallbackError: t('chat.workflow.runFailed'),
      });
    },
    [sessionId, t],
  );

  return { runStep };
}
