import { FileText, Image, Paperclip } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/lib/utils';
import type { Attachment } from '@/types/chat';

import {
  attachmentLabel,
  attachmentPath,
  isImageAttachment,
} from './workflowInputAttachments';
import { WORKFLOW_FIELD_CLASS, WorkflowInputFieldShell } from './WorkflowInputFieldShell';

function AttachmentIcon({ att }: { att: Attachment }) {
  if (isImageAttachment(att)) {
    return (
      <Image
        className="h-3.5 w-3.5 shrink-0 text-primary-600 dark:text-primary-400"
        aria-hidden
      />
    );
  }
  return <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground-tertiary" aria-hidden />;
}

export interface WorkflowFileFieldProps {
  name: string;
  label: string;
  description?: string;
  required?: boolean;
  value: string;
  onChange: (value: string) => void;
  attachments?: Attachment[];
  disabled?: boolean;
  compact?: boolean;
  error?: string;
}

export function WorkflowFileField({
  name,
  label,
  description,
  required,
  value,
  onChange,
  attachments = [],
  disabled,
  compact,
  error,
}: WorkflowFileFieldProps) {
  const { t } = useTranslation('workflows');
  const trimmed = value.trim();
  const selectedId =
    attachments.find((att) => attachmentPath(att) === trimmed)?.id ?? null;

  return (
    <WorkflowInputFieldShell
      label={label}
      name={name}
      required={required}
      description={description}
      error={error}
      compact={compact}
    >
      {attachments.length > 0 ? (
        <div className="space-y-2">
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground-tertiary">
            <Paperclip className="h-3 w-3 shrink-0" aria-hidden />
            {t('workflowInput.attachments', 'Session attachments')}
          </div>
          <div className="flex gap-1.5 overflow-x-auto pb-0.5">
            {attachments.map((att) => {
              const path = attachmentPath(att);
              const selected = selectedId === att.id;
              return (
                <button
                  key={att.id}
                  type="button"
                  disabled={disabled}
                  title={t('workflowInput.pickAttachment', 'Click to select')}
                  onClick={() => onChange(path)}
                  className={cn(
                    'inline-flex max-w-[12rem] shrink-0 items-center gap-1.5 rounded-lg border px-2 py-1.5 text-left text-xs transition-colors',
                    selected
                      ? 'border-primary-400 bg-primary-50 text-primary-800 ring-1 ring-primary-300 dark:border-primary-600 dark:bg-primary-950/40 dark:text-primary-100'
                      : 'border-border-subtle bg-surface-sunken/50 text-foreground hover:border-primary-300 hover:bg-surface-raised',
                    disabled && 'pointer-events-none opacity-60',
                  )}
                >
                  <AttachmentIcon att={att} />
                  <span className="truncate font-medium">{attachmentLabel(att)}</span>
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
      <input
        id={`wf-input-${name}`}
        type="text"
        className={cn(WORKFLOW_FIELD_CLASS, 'font-mono text-xs')}
        placeholder={t('workflowInput.pathPlaceholder', 'File path or attachment name')}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      />
    </WorkflowInputFieldShell>
  );
}
