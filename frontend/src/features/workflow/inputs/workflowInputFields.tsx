import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';
import type { Attachment } from '@/types/chat';

import type { WorkflowInputSpec } from '../genui/inputsToGenUiTree';
import { WorkflowFileField } from './WorkflowFileField';
import { WORKFLOW_FIELD_CLASS, WorkflowInputFieldShell } from './WorkflowInputFieldShell';

export interface WorkflowInputFieldProps {
  spec: WorkflowInputSpec;
  value: unknown;
  onChange: (value: unknown) => void;
  attachments?: Attachment[];
  disabled?: boolean;
  compact?: boolean;
  fieldError?: string;
}

function normalizeType(spec: WorkflowInputSpec): string {
  return String(spec.type ?? 'string').toLowerCase();
}

function usesAttachmentPicker(spec: WorkflowInputSpec, attachments?: Attachment[]): boolean {
  if (normalizeType(spec) === 'file') return true;
  if (spec.name === 'user_input' && (attachments?.length ?? 0) > 0) return true;
  return false;
}

export function WorkflowInputField({
  spec,
  value,
  onChange,
  attachments,
  disabled,
  compact,
  fieldError,
}: WorkflowInputFieldProps) {
  const { t } = useTranslation('workflows');
  const label = spec.label?.trim() || spec.name;
  const type = normalizeType(spec);

  if (usesAttachmentPicker(spec, attachments)) {
    return (
      <WorkflowFileField
        name={spec.name}
        label={label}
        description={spec.description}
        required={Boolean(spec.required)}
        value={typeof value === 'string' ? value : value != null ? String(value) : ''}
        onChange={(v) => onChange(v)}
        attachments={attachments}
        disabled={disabled}
        compact={compact}
        error={fieldError}
      />
    );
  }

  if (Array.isArray(spec.choices) && spec.choices.length > 0) {
    const strValue = typeof value === 'string' ? value : value != null ? String(value) : '';
    return (
      <WorkflowInputFieldShell
        label={label}
        name={spec.name}
        required={spec.required}
        description={spec.description}
        error={fieldError}
        compact={compact}
      >
        <select
          id={`wf-input-${spec.name}`}
          className={cn(WORKFLOW_FIELD_CLASS, 'appearance-none')}
          value={strValue}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        >
          {!strValue ? <option value="" /> : null}
          {spec.choices.map((choice, i) => (
            <option key={i} value={String(choice)}>
              {String(choice)}
            </option>
          ))}
        </select>
      </WorkflowInputFieldShell>
    );
  }

  switch (type) {
    case 'boolean':
    case 'bool': {
      const checked = Boolean(value);
      return (
        <WorkflowInputFieldShell
          label={label}
          name={spec.name}
          required={spec.required}
          description={spec.description}
          error={fieldError}
          compact={compact}
        >
          <button
            id={`wf-input-${spec.name}`}
            type="button"
            role="switch"
            aria-checked={checked}
            disabled={disabled}
            onClick={() => onChange(!checked)}
            className={cn(
              'relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors',
              checked ? 'bg-primary-500' : 'bg-border',
              disabled && 'opacity-60',
            )}
          >
            <span
              className={cn(
                'inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform',
                checked ? 'translate-x-[18px]' : 'translate-x-0.5',
              )}
            />
          </button>
        </WorkflowInputFieldShell>
      );
    }
    case 'number':
    case 'float':
    case 'integer':
    case 'int': {
      const numStr = value === undefined || value === null ? '' : String(value);
      return (
        <WorkflowInputFieldShell
          label={label}
          name={spec.name}
          required={spec.required}
          description={spec.description}
          error={fieldError}
          compact={compact}
        >
          <input
            id={`wf-input-${spec.name}`}
            type="number"
            className={WORKFLOW_FIELD_CLASS}
            value={numStr}
            min={typeof spec.min === 'number' ? spec.min : undefined}
            max={typeof spec.max === 'number' ? spec.max : undefined}
            step={
              typeof spec.step === 'number'
                ? spec.step
                : type === 'integer' || type === 'int'
                  ? 1
                  : undefined
            }
            disabled={disabled}
            onChange={(e) => onChange(e.target.value)}
          />
        </WorkflowInputFieldShell>
      );
    }
    case 'array':
    case 'object':
    case 'json': {
      const text = typeof value === 'string' ? value : value != null ? JSON.stringify(value, null, 2) : '';
      let jsonError: string | undefined;
      if (text.trim()) {
        try {
          JSON.parse(text);
        } catch {
          jsonError = t('workflowInput.invalidJson', 'Invalid JSON');
        }
      }
      return (
        <WorkflowInputFieldShell
          label={label}
          name={spec.name}
          required={spec.required}
          description={spec.description ?? 'JSON'}
          error={fieldError ?? jsonError}
          compact={compact}
        >
          <textarea
            id={`wf-input-${spec.name}`}
            className={cn(WORKFLOW_FIELD_CLASS, 'min-h-[5rem] resize-y font-mono text-xs')}
            rows={typeof spec.rows === 'number' ? spec.rows : 4}
            placeholder={type === 'array' ? '[ ... ]' : '{ ... }'}
            value={text}
            disabled={disabled}
            onChange={(e) => onChange(e.target.value)}
          />
        </WorkflowInputFieldShell>
      );
    }
    default:
      if (spec.multiline) {
        const text = typeof value === 'string' ? value : value != null ? String(value) : '';
        return (
          <WorkflowInputFieldShell
            label={label}
            name={spec.name}
            required={spec.required}
            description={spec.description}
            error={fieldError}
            compact={compact}
          >
            <textarea
              id={`wf-input-${spec.name}`}
              className={cn(WORKFLOW_FIELD_CLASS, 'min-h-[5rem] resize-y')}
              rows={typeof spec.rows === 'number' ? spec.rows : 5}
              value={text}
              disabled={disabled}
              onChange={(e) => onChange(e.target.value)}
            />
          </WorkflowInputFieldShell>
        );
      }
      return (
        <WorkflowInputFieldShell
          label={label}
          name={spec.name}
          required={spec.required}
          description={spec.description}
          error={fieldError}
          compact={compact}
        >
          <input
            id={`wf-input-${spec.name}`}
            type="text"
            className={WORKFLOW_FIELD_CLASS}
            value={typeof value === 'string' ? value : value != null ? String(value) : ''}
            disabled={disabled}
            onChange={(e) => onChange(e.target.value)}
          />
        </WorkflowInputFieldShell>
      );
  }
}
