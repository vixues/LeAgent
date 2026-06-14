import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { apiClient } from '@/api/client';
import { useChatStore } from '@/stores/chat';
import { useExecutionSessionStore } from '@/stores/executionSession';
import { useExecutionOverlay } from '@/features/workflow/store/executionOverlay';

interface RunStepResult {
  success: boolean;
  data?: unknown;
  error?: string | null;
  prompt_id?: string | null;
  run_id?: string | null;
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
      const parentRunId =
        useExecutionSessionStore.getState().bySession[sessionId]?.runId ?? undefined;
      try {
        const res = await apiClient.post<RunStepResult>(
          `/chat/sessions/${sessionId}/workflow-steps/${encodeURIComponent(stepId)}/run`,
          {
            message_id: messageId,
            workflow_digest: workflowDigest,
            user_input: userInput?.trim() ?? '',
            parent_run_id: parentRunId,
          },
        );
        const stepPatch = {
          prompt_id: res.prompt_id ?? undefined,
          run_id: res.run_id ?? undefined,
        };
        if (res.prompt_id) {
          useExecutionSessionStore.getState().upsertFromStarted(sessionId, {
            runId: res.run_id ?? res.prompt_id,
            scope: 'workflow',
            promptId: res.prompt_id,
            parentRunId: parentRunId,
          });
          useExecutionOverlay.getState().start(res.prompt_id, 'chat');
        }
        if (!res.success) {
          updateStep(sessionId, messageId, stepId, {
            status: 'error',
            error: res.error || t('chat.workflow.runFailed'),
            ...stepPatch,
          });
        } else if (!res.prompt_id) {
          updateStep(sessionId, messageId, stepId, { status: 'success', ...stepPatch });
        } else {
          updateStep(sessionId, messageId, stepId, { status: 'running', ...stepPatch });
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
