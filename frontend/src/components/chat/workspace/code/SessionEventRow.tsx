import { useMemo, type Ref } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ClipboardCopy,
  ExternalLink,
  Loader2,
  XCircle,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { AgentSessionEvent } from '@/lib/agentSessionEvents';
import { eventKindMeta } from './eventMeta';
import { CodeSurface } from './CodeSurface';

interface SessionEventRowProps {
  event: AgentSessionEvent;
  expanded: boolean;
  wrap: boolean;
  onToggle: () => void;
  innerRef?: Ref<HTMLDivElement>;
}

function StatusIcon({ status }: { status: AgentSessionEvent['status'] }) {
  if (status === 'running' || status === 'pending') {
    return <Loader2 className="size-3 shrink-0 animate-spin text-primary/70" aria-hidden />;
  }
  if (status === 'error') {
    return <XCircle className="size-3 shrink-0 text-rose-500" aria-hidden />;
  }
  if (status === 'success') {
    return <CheckCircle2 className="size-3 shrink-0 text-emerald-500" aria-hidden />;
  }
  return null;
}

function bodyTextFor(event: AgentSessionEvent): string {
  if (event.diff) return event.diff.after;
  if (event.code) return event.code;
  if (event.stdout || event.stderr) {
    return [event.stdout, event.stderr].filter(Boolean).join('\n');
  }
  return '';
}

export function SessionEventRow({
  event,
  expanded,
  wrap,
  onToggle,
  innerRef,
}: SessionEventRowProps) {
  const { t } = useTranslation();
  const meta = eventKindMeta(event.kind);
  const Icon = meta.icon;
  const verb = t(meta.labelKey, { defaultValue: meta.verb });

  const lineCount = useMemo(() => {
    const text = bodyTextFor(event);
    return text ? text.split('\n').length : 0;
  }, [event]);

  const hasBody =
    Boolean(event.code) ||
    Boolean(event.diff) ||
    Boolean(event.stdout) ||
    Boolean(event.stderr) ||
    Boolean(event.changedFiles?.length) ||
    Boolean(event.previewUrl) ||
    Boolean(event.errorText);

  const copyText = bodyTextFor(event);

  return (
    <div
      ref={innerRef}
      className={cn(
        'group relative rounded-lg border transition-colors',
        event.status === 'error'
          ? 'border-rose-500/30 bg-rose-500/[0.03]'
          : event.streaming
            ? 'border-primary/30 bg-primary/[0.03]'
            : 'border-border-subtle/50 bg-surface-sunken/40',
      )}
    >
      <div className="flex w-full min-w-0 items-center gap-1.5">
        <button
          type="button"
          onClick={onToggle}
          disabled={!hasBody}
          aria-expanded={expanded}
          className={cn(
            'flex min-w-0 flex-1 items-center gap-2 px-2.5 py-2 text-left',
            hasBody && 'transition-colors hover:bg-surface/40',
          )}
        >
          <span className="flex w-3 shrink-0 items-center justify-center">
            {hasBody ? (
              expanded ? (
                <ChevronDown className="size-3 text-muted-foreground" aria-hidden />
              ) : (
                <ChevronRight className="size-3 text-muted-foreground" aria-hidden />
              )
            ) : (
              <span className="text-muted-foreground/40">·</span>
            )}
          </span>
          <span
            className={cn(
              'flex size-4 shrink-0 items-center justify-center rounded',
              meta.accent,
            )}
          >
            <Icon className="size-2.5" aria-hidden />
          </span>
          <span className="shrink-0 text-[11px] font-semibold text-foreground/80">
            {verb}
          </span>
          <span
            className="min-w-0 flex-1 truncate font-mono text-[11px] text-muted-foreground"
            title={event.path ?? event.label}
          >
            {event.label}
          </span>
          {lineCount > 0 && (
            <span className="shrink-0 text-[10px] tabular-nums text-muted-foreground/50">
              {lineCount}L
            </span>
          )}
          {typeof event.durationMs === 'number' &&
            event.status !== 'running' &&
            event.status !== 'pending' && (
              <span className="shrink-0 text-[10px] tabular-nums text-muted-foreground/50">
                {event.durationMs}ms
              </span>
            )}
          {event.syntaxValid === false && (
            <AlertTriangle className="size-3 shrink-0 text-amber-500" aria-hidden />
          )}
          <StatusIcon status={event.status} />
        </button>
        {expanded && copyText.length > 0 && (
          <button
            type="button"
            className="mr-1.5 shrink-0 rounded p-1 text-muted-foreground/60 transition-colors hover:bg-surface hover:text-foreground"
            aria-label={t('chat.workspace.agent.copyContents', { defaultValue: 'Copy contents' })}
            onClick={() => void navigator.clipboard?.writeText(copyText)}
          >
            <ClipboardCopy className="size-3" aria-hidden />
          </button>
        )}
      </div>

      {expanded && hasBody && (
        <div className="border-t border-border-subtle/40">
          {event.kind === 'project_run' && (event.previewUrl || event.port) && (
            <div className="flex items-center gap-2 border-b border-border-subtle/30 px-3 py-1.5 text-[11px]">
              {event.port && (
                <span className="font-mono text-muted-foreground">:{event.port}</span>
              )}
              {event.previewUrl && (
                <a
                  href={event.previewUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex min-w-0 items-center gap-1 truncate text-primary hover:underline"
                >
                  <span className="truncate">{event.previewUrl}</span>
                  <ExternalLink className="size-3 shrink-0" aria-hidden />
                </a>
              )}
            </div>
          )}

          {event.diff ? (
            <CodeSurface
              diff={event.diff}
              language={event.language}
              wrap={wrap}
              maxHeightClass="max-h-[40vh]"
            />
          ) : event.code ? (
            <CodeSurface
              code={event.code}
              language={event.language}
              wrap={wrap}
              tail={event.streaming}
              maxHeightClass="max-h-[40vh]"
              showLineNumbers={event.kind !== 'patch'}
            />
          ) : null}

          {(event.stdout?.trim() || event.stderr?.trim()) && event.kind !== 'shell' && (
            <div className="border-t border-border-subtle/30 bg-surface-sunken/50">
              <div className="px-3 pt-2 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground/55">
                {t('chat.workspace.agent.outputLabel', { defaultValue: 'Output' })}
              </div>
              <pre className="max-h-[28vh] overflow-auto whitespace-pre-wrap break-words px-3 pb-2 pt-1 font-mono text-[11px] leading-relaxed text-foreground/80">
                {event.stdout?.trimEnd()}
                {event.stderr?.trim() ? (
                  <span className="text-rose-600 dark:text-rose-400">
                    {event.stdout?.trim() ? '\n' : ''}
                    {event.stderr.trimEnd()}
                  </span>
                ) : null}
              </pre>
            </div>
          )}

          {event.changedFiles && event.changedFiles.length > 0 && (
            <ul className="max-h-40 space-y-0.5 overflow-y-auto border-t border-border-subtle/30 px-3 py-2 font-mono text-[10px] text-foreground/80">
              {event.changedFiles.map((p) => (
                <li key={p} className="truncate" title={p}>
                  {p}
                </li>
              ))}
            </ul>
          )}

          {event.errorText && (
            <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words border-t border-rose-500/20 bg-rose-500/[0.05] px-3 py-2 font-mono text-[11px] text-rose-600 dark:text-rose-400">
              {event.errorText}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
