import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { apiClient } from '@/api/client';
import { useChatStore } from '@/stores/chat';
import { useExecutionSessionStore } from '@/stores/executionSession';
import { syncSessionTodosFromWorkflow } from './workflowTodoSync';

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
      const wfAfterStart = useChatStore.getState().messages[sessionId]?.find((m) => m.id === messageId)
        ?.workflow;
      if (wfAfterStart) {
        syncSessionTodosFromWorkflow(
          sessionId,
          wfAfterStart.spec.steps,
          wfAfterStart.stepRuns,
        );
      }
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
        const promptId = res.prompt_id ?? undefined;
        if (promptId) {
          useExecutionSessionStore.getState().upsertFromStarted(sessionId, {
            runId: res.run_id ?? promptId,
            scope: 'workflow',
            promptId,
            parentRunId: parentRunId,
          });
        }
        if (!res.success) {
          updateStep(sessionId, messageId, stepId, {
            status: 'error',
            error: res.error || t('chat.workflow.runFailed'),
            ...stepPatch,
          });
        } else {
          updateStep(sessionId, messageId, stepId, { status: 'success', ...stepPatch });
        }
      } catch (e) {
        updateStep(sessionId, messageId, stepId, {
          status: 'error',
          error: e instanceof Error ? e.message : t('chat.workflow.runFailed'),
        });
      } finally {
        const wf = useChatStore.getState().messages[sessionId]?.find((m) => m.id === messageId)?.workflow;
        if (wf) {
          syncSessionTodosFromWorkflow(sessionId, wf.spec.steps, wf.stepRuns);
        }
      }
    },
    [sessionId, updateStep, t],
  );

  return { runStep };
}
