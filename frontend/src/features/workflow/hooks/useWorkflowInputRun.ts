import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import {
  runChatWorkflowStep,
  startChatWorkflowEmbedRun,
} from '@/components/chat/workflow/chatWorkflowRunActions';
import { dispatchGenUiAction } from '@/lib/genUiActionBus';
import { useGenUiFormsStore } from '@/stores/genUiForms';

import type { OperationRunTarget } from '../components/WorkflowOperationPanel';
import {
  coerceFormValues,
  missingRequiredInputs,
  type WorkflowInputSpec,
} from '../genui/inputsToGenUiTree';
import { inputDefaults } from '../genui/workflowRunForm';

export interface UseWorkflowInputRunOptions {
  formKey: string;
  inputs: WorkflowInputSpec[];
  flowId: string;
  runTarget?: OperationRunTarget;
  sessionId?: string;
  messageId?: string;
  onRunError?: (message: string) => void;
}

export function useWorkflowInputRun({
  formKey,
  inputs,
  flowId,
  runTarget,
  sessionId,
  messageId,
  onRunError,
}: UseWorkflowInputRunOptions) {
  const { t } = useTranslation('workflows');

  const run = useCallback(async () => {
    const raw = useGenUiFormsStore.getState().getValues(formKey);
    const merged = { ...inputDefaults(inputs), ...raw };
    const missing = missingRequiredInputs(merged, inputs);
    if (missing.length > 0) {
      const msg = t('workflowInput.required', {
        defaultValue: 'Missing required inputs: {{names}}',
        names: missing.join(', '),
      });
      onRunError?.(msg);
      return;
    }
    const values = coerceFormValues(merged, inputs);

    if (runTarget?.kind === 'chat_embed') {
      await startChatWorkflowEmbedRun({
        sessionId: runTarget.sessionId,
        messageId: runTarget.messageId,
        digest: runTarget.digest,
        inputs: values,
        fallbackError: t('workflowInput.runFailed', 'Run failed'),
      });
      return;
    }

    if (runTarget?.kind === 'chat_step' && runTarget.stepId) {
      const userInput = values.user_input;
      await runChatWorkflowStep({
        sessionId: runTarget.sessionId,
        messageId: runTarget.messageId,
        stepId: runTarget.stepId,
        digest: runTarget.digest,
        userInput: typeof userInput === 'string' ? userInput : undefined,
        fallbackError: t('workflowInput.runFailed', 'Run failed'),
      });
      return;
    }

    if (!flowId) {
      onRunError?.(t('runPanel.saveFirst', 'Save the workflow to enable runs.'));
      return;
    }

    dispatchGenUiAction(
      {
        type: 'run_workflow',
        payload: {
          flowId,
          values,
          ...(runTarget ? { target: runTarget } : {}),
        },
      },
      { sessionId, messageId },
    );
  }, [formKey, inputs, flowId, runTarget, sessionId, messageId, onRunError, t]);

  return { run };
}
