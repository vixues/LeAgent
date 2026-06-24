import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { RunWorkflowActionPayload } from '@/lib/genUiActionBus';

import { type WorkflowInputSpec } from '../genui/inputsToGenUiTree';
import { type WorkflowOutputSpec } from '../genui/outputsToGenUiTree';
import { useWorkflowGenUiBridge } from '../genui/useWorkflowGenUiBridge';
import { WorkflowOperationPanel } from './WorkflowOperationPanel';

export interface WorkflowRunPanelProps {
  flowId: string | null;
  /** Declared workflow inputs (drives the generated GenUI form). */
  inputs?: WorkflowInputSpec[] | null;
  /** Declared workflow outputs (render hints for results). */
  outputs?: WorkflowOutputSpec[] | null;
  /** Editor surfaces save the draft before running. */
  onBeforeRun?: (p: RunWorkflowActionPayload) => Promise<void> | void;
  onRunStarted?: (res: { prompt_id: string; execution_id: string }) => void;
  className?: string;
}

/**
 * GenUI-driven workflow I/O surface for the graph editor's Run panel and the
 * Playground. A thin wrapper over the shared {@link WorkflowOperationPanel}
 * that wires the saved-Flow run/resume bridge and reads the editor-synced
 * execution overlay.
 */
export function WorkflowRunPanel({
  flowId,
  inputs,
  outputs,
  onBeforeRun,
  onRunStarted,
  className,
}: WorkflowRunPanelProps) {
  const { t } = useTranslation();
  const [error, setError] = useState<string | null>(null);

  useWorkflowGenUiBridge({
    inputs,
    onBeforeRun,
    onRunStarted: (res) => {
      setError(null);
      onRunStarted?.(res);
    },
    onError: setError,
  });

  return (
    <WorkflowOperationPanel
      flowId={flowId}
      inputs={flowId ? inputs : null}
      outputs={outputs}
      overlaySource="editor"
      runTarget={{ kind: 'flow' }}
      submitLabel={t('runPanel.run', 'Run')}
      inputsHint={t(
        'runPanel.inputsHint',
        'Set workflow inputs below, then click Run. Values are injected into nodes that reference ${input.name}.',
      )}
      emptyInputsMessage={
        !flowId
          ? t('runPanel.saveFirst', 'Save the workflow to enable runs.')
          : t(
              'runPanel.noInputs',
              'No workflow inputs declared. Add inputs under Inputs / Outputs, or edit prompt fields directly on nodes.',
            )
      }
      error={error}
      className={className}
    />
  );
}
