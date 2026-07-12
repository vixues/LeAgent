import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

export interface WorkflowInputFieldShellProps {
  label: string;
  name: string;
  required?: boolean;
  description?: string;
  error?: string;
  compact?: boolean;
  children: ReactNode;
}

export function WorkflowInputFieldShell({
  label,
  name,
  required,
  description,
  error,
  compact,
  children,
}: WorkflowInputFieldShellProps) {
  return (
    <div className={cn('space-y-1.5', compact ? 'px-3' : 'px-4')}>
      <label htmlFor={`wf-input-${name}`} className="flex items-center gap-1 text-xs font-medium text-foreground">
        <span>{label}</span>
        {required ? <span className="text-rose-500" aria-hidden>*</span> : null}
      </label>
      {description ? (
        <p className="text-[11px] leading-relaxed text-muted-foreground-tertiary">{description}</p>
      ) : null}
      {children}
      {error ? <p className="text-xs text-rose-600 dark:text-rose-400">{error}</p> : null}
    </div>
  );
}

export const WORKFLOW_FIELD_CLASS =
  'w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground-tertiary focus:outline-none focus:ring-1 focus:ring-primary-400 disabled:cursor-not-allowed disabled:opacity-60';
