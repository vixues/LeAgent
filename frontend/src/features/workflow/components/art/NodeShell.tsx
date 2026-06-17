import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

import type { NodeRunStatus } from '../../store/executionOverlay';

const STATUS_RING: Record<string, string> = {
  running: 'ring-2 ring-blue-400 animate-pulse',
  success: 'ring-2 ring-emerald-400',
  error: 'ring-2 ring-red-500',
  blocked: 'ring-2 ring-amber-400',
  cached: 'ring-2 ring-slate-400',
  skipped: 'ring-2 ring-slate-300 opacity-70',
};

export function NodeShell({
  title,
  accent = 'rgb(var(--color-primary))',
  selected,
  status,
  mode,
  width,
  className,
  headerActions,
  children,
  footer,
}: {
  title: string;
  accent?: string;
  selected?: boolean;
  status?: NodeRunStatus;
  mode?: 'mute' | 'bypass';
  width?: number | string;
  className?: string;
  headerActions?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div
      className={cn(
        'relative overflow-visible rounded-lg border border-border bg-surface-elevated text-foreground shadow-md',
        selected && 'ring-2 ring-primary',
        status ? STATUS_RING[status] : '',
        mode === 'mute' && 'opacity-40 saturate-50',
        mode === 'bypass' &&
          'border-violet-400 bg-violet-50/80 dark:border-violet-600 dark:bg-violet-950/50',
        className,
      )}
      style={width != null ? { width } : undefined}
    >
      <div
        className="flex items-center justify-between gap-2 border-b border-border px-2 py-1.5"
        style={{
          backgroundColor: `color-mix(in srgb, ${accent} 22%, rgb(var(--color-surface-sunken)))`,
        }}
      >
        <span className="truncate text-xs font-semibold">{title}</span>
        <div className="flex shrink-0 items-center gap-1">{headerActions}</div>
      </div>
      {children}
      {footer}
    </div>
  );
}
