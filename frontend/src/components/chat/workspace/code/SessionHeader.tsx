import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronsDownUp, ChevronsUpDown, ClipboardCopy, WrapText } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui';
import type { AgentEventKind, SessionEventSummary } from '@/lib/agentSessionEvents';
import { eventKindMeta } from './eventMeta';

interface SessionHeaderProps {
  summary: SessionEventSummary;
  running: boolean;
  wrap: boolean;
  onWrapToggle: () => void;
  onExpandAll: () => void;
  onCollapseAll: () => void;
  onCopySession: () => void;
  availableKinds: AgentEventKind[];
  selectedKinds: Set<AgentEventKind>;
  onToggleFilter: (kind: AgentEventKind) => void;
}

function IconButton({
  label,
  active,
  onClick,
  children,
}: {
  label: string;
  active?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger>
          <button
            type="button"
            onClick={onClick}
            aria-label={label}
            aria-pressed={active}
            className={cn(
              'flex size-6 items-center justify-center rounded-md text-muted-foreground/70 transition-colors',
              'hover:bg-surface hover:text-foreground',
              active && 'bg-primary/10 text-primary',
            )}
          >
            {children}
          </button>
        </TooltipTrigger>
        <TooltipContent side="bottom">{label}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export function SessionHeader({
  summary,
  running,
  wrap,
  onWrapToggle,
  onExpandAll,
  onCollapseAll,
  onCopySession,
  availableKinds,
  selectedKinds,
  onToggleFilter,
}: SessionHeaderProps) {
  const { t } = useTranslation();

  const summaryParts = useMemo(() => {
    const parts: string[] = [];
    if (summary.fileCount > 0) {
      parts.push(
        t('chat.workspace.agent.summaryFiles', {
          count: summary.fileCount,
          defaultValue: `${summary.fileCount} files`,
        }),
      );
    }
    if (summary.execCount > 0) {
      parts.push(
        t('chat.workspace.agent.summaryRuns', {
          count: summary.execCount,
          defaultValue: `${summary.execCount} runs`,
        }),
      );
    }
    if (summary.readCount > 0) {
      parts.push(
        t('chat.workspace.agent.summaryReads', {
          count: summary.readCount,
          defaultValue: `${summary.readCount} reads`,
        }),
      );
    }
    return parts;
  }, [summary, t]);

  return (
    <div className="shrink-0 overflow-hidden rounded-lg border border-border-subtle/50 bg-surface-sunken/40">
      {/* Status + summary */}
      <div className="flex items-center gap-2 px-3 py-2">
        {running ? (
          <span className="relative flex size-2 shrink-0">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary/60" />
            <span className="relative inline-flex size-2 rounded-full bg-primary" />
          </span>
        ) : (
          <span
            className={cn(
              'size-2 shrink-0 rounded-full',
              summary.errorCount > 0 ? 'bg-rose-500' : 'bg-emerald-500/70',
            )}
          />
        )}
        <span className="text-[11px] font-semibold text-foreground/90">
          {running
            ? t('chat.workspace.agent.statusRunning', { defaultValue: 'Agent working…' })
            : t('chat.workspace.agent.statusIdle', { defaultValue: 'Session' })}
        </span>
        {summaryParts.length > 0 && (
          <span className="min-w-0 flex-1 truncate text-[10px] tabular-nums text-muted-foreground/60">
            {summaryParts.join(' · ')}
          </span>
        )}
        {summary.errorCount > 0 && (
          <span className="ml-auto shrink-0 rounded bg-rose-500/15 px-1.5 py-px text-[9px] font-bold uppercase text-rose-500">
            {t('chat.workspace.agent.summaryErrors', {
              count: summary.errorCount,
              defaultValue: `${summary.errorCount} errors`,
            })}
          </span>
        )}
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-1 border-t border-border-subtle/40 bg-surface/20 px-2 py-1">
        <div className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
          {availableKinds.map((kind) => {
            const meta = eventKindMeta(kind);
            const active = selectedKinds.size === 0 || selectedKinds.has(kind);
            return (
              <button
                key={kind}
                type="button"
                onClick={() => onToggleFilter(kind)}
                className={cn(
                  'flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[9px] font-bold uppercase leading-none transition-opacity',
                  meta.accent,
                  active ? 'opacity-100' : 'opacity-35',
                )}
                title={t(meta.labelKey, { defaultValue: meta.verb })}
              >
                {meta.badge}
              </button>
            );
          })}
        </div>
        <div className="mx-1 h-4 w-px shrink-0 bg-border-subtle/60" />
        <div className="flex shrink-0 items-center gap-0.5">
          <IconButton
            label={t('chat.workspace.agent.expandAll', { defaultValue: 'Expand all' })}
            onClick={onExpandAll}
          >
            <ChevronsUpDown className="size-3.5" aria-hidden />
          </IconButton>
          <IconButton
            label={t('chat.workspace.agent.collapseAll', { defaultValue: 'Collapse all' })}
            onClick={onCollapseAll}
          >
            <ChevronsDownUp className="size-3.5" aria-hidden />
          </IconButton>
          <IconButton
            label={t('chat.workspace.agent.wordWrap', { defaultValue: 'Toggle word wrap' })}
            active={wrap}
            onClick={onWrapToggle}
          >
            <WrapText className="size-3.5" aria-hidden />
          </IconButton>
          <IconButton
            label={t('chat.workspace.agent.copySession', { defaultValue: 'Copy session log' })}
            onClick={onCopySession}
          >
            <ClipboardCopy className="size-3.5" aria-hidden />
          </IconButton>
        </div>
      </div>
    </div>
  );
}
