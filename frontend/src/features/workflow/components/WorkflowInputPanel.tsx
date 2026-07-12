import { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Play } from 'lucide-react';

import { Button } from '@/components/ui/Button';
import { cn } from '@/lib/utils';
import { useGenUiFormsStore } from '@/stores/genUiForms';
import type { Attachment } from '@/types/chat';

import type { OperationRunTarget } from './WorkflowOperationPanel';
import { useWorkflowInputRun } from '../hooks/useWorkflowInputRun';
import {
  type WorkflowInputSpec,
} from '../genui/inputsToGenUiTree';
import { inputDefaults } from '../genui/workflowRunForm';
import { WorkflowInputField } from '../inputs/workflowInputFields';

const EMPTY_FORM_VALUES: Record<string, unknown> = {};

export interface WorkflowInputPanelProps {
  inputs: WorkflowInputSpec[];
  formKey: string;
  runTarget?: OperationRunTarget;
  flowId: string;
  includeSubmit?: boolean;
  submitLabel?: string;
  sessionId?: string;
  messageId?: string;
  attachments?: Attachment[];
  compact?: boolean;
  inputsHint?: string;
  onRunError?: (msg: string) => void;
  disabled?: boolean;
}

function resolveScopedFormKey(formKey: string, sessionId?: string, messageId?: string): string {
  if (formKey.includes('::')) return formKey;
  return `${sessionId ?? 'scope'}::${messageId ?? 'root'}::${formKey}`;
}

/**
 * Native workflow run input form — shared by the editor Run panel and in-chat
 * workflow cards. Values bind to {@link useGenUiFormsStore} using the same keys
 * as the legacy GenUI form path so step rails and run collectors stay compatible.
 */
export function WorkflowInputPanel({
  inputs,
  formKey,
  runTarget,
  flowId,
  includeSubmit = true,
  submitLabel,
  sessionId,
  messageId,
  attachments,
  compact = false,
  inputsHint,
  onRunError,
  disabled = false,
}: WorkflowInputPanelProps) {
  const { t } = useTranslation('workflows');
  const scopedKey = resolveScopedFormKey(formKey, sessionId, messageId);
  const specs = useMemo(
    () => inputs.filter((s): s is WorkflowInputSpec => Boolean(s?.name)),
    [inputs],
  );

  const values = useGenUiFormsStore((s) => s.values[scopedKey] ?? EMPTY_FORM_VALUES);
  const setField = useGenUiFormsStore((s) => s.setField);
  const seedField = useGenUiFormsStore((s) => s.seedField);

  useEffect(() => {
    for (const spec of specs) {
      if (spec.default !== undefined) {
        seedField(scopedKey, spec.name, spec.default);
      }
    }
  }, [scopedKey, specs, seedField]);

  const { run } = useWorkflowInputRun({
    formKey: scopedKey,
    inputs: specs,
    flowId,
    runTarget,
    sessionId,
    messageId,
    onRunError,
  });

  if (specs.length === 0) return null;

  return (
    <div
      className={cn('space-y-4', compact ? 'py-2.5' : 'py-3')}
      data-testid="workflow-input-panel"
      data-form-key={scopedKey}
    >
      {inputsHint ? (
        <p
          className={cn(
            'text-[11px] leading-relaxed text-muted-foreground',
            compact ? 'px-3' : 'px-4',
          )}
        >
          {inputsHint}
        </p>
      ) : null}

      <div className="space-y-4">
        {specs.map((spec) => (
          <WorkflowInputField
            key={spec.name}
            spec={spec}
            value={values[spec.name] ?? inputDefaults([spec])[spec.name] ?? ''}
            onChange={(v) => setField(scopedKey, spec.name, v)}
            attachments={attachments}
            disabled={disabled}
            compact={compact}
          />
        ))}
      </div>

      {includeSubmit ? (
        <div className={cn(compact ? 'px-3' : 'px-4')}>
          <Button
            type="button"
            variant="primarySolid"
            size={compact ? 'sm' : 'md'}
            leftIcon={<Play className="h-3.5 w-3.5" aria-hidden />}
            disabled={disabled}
            onClick={() => void run()}
          >
            {submitLabel ?? t('runPanel.run', 'Run')}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
