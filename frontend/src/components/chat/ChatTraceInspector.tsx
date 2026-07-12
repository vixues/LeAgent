import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ChevronDown,
  ChevronRight,
  Download,
  Loader2,
  AlertCircle,
  Cpu,
  Wrench,
  Bot,
} from 'lucide-react';
import { tracesApi, type TraceDetail, type TraceSpan, type TraceSummary } from '@/api/traces';
import { cn } from '@/lib/utils';

interface ChatTraceInspectorProps {
  sessionId: string;
  runId?: string | null;
  className?: string;
}

function kindIcon(kind: string) {
  if (kind === 'llm') return <Cpu className="h-3 w-3 shrink-0 text-sky-500" />;
  if (kind === 'tool') return <Wrench className="h-3 w-3 shrink-0 text-amber-500" />;
  if (kind === 'error') return <AlertCircle className="h-3 w-3 shrink-0 text-red-500" />;
  return <Bot className="h-3 w-3 shrink-0 text-muted-foreground-tertiary" />;
}

function SpanRow({
  span,
  depth = 0,
}: {
  span: TraceSpan;
  depth?: number;
}) {
  const [open, setOpen] = useState(false);
  const children = span.children ?? [];
  const hasDetail = Boolean(span.input_preview || span.output_preview || span.attrs);

  return (
    <li className="text-xs">
      <button
        type="button"
        className={cn(
          'flex w-full items-center gap-1.5 rounded px-1 py-0.5 text-left hover:bg-muted/40',
          span.status === 'error' && 'text-red-600 dark:text-red-400',
        )}
        style={{ paddingLeft: 4 + depth * 12 }}
        onClick={() => setOpen((v) => !v)}
      >
        {hasDetail || children.length > 0 ? (
          open ? (
            <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground-tertiary" />
          ) : (
            <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground-tertiary" />
          )
        ) : (
          <span className="inline-block w-3" />
        )}
        {kindIcon(span.kind)}
        <span className="min-w-0 flex-1 truncate font-mono">{span.name}</span>
        <span className="shrink-0 tabular-nums text-muted-foreground-tertiary">
          {span.latency_ms ? `${Math.round(span.latency_ms)}ms` : ''}
        </span>
      </button>
      {open && hasDetail ? (
        <div
          className="mb-1 space-y-1 rounded border border-border-subtle/60 bg-muted/20 p-1.5 font-mono text-[10px] text-muted-foreground"
          style={{ marginLeft: 16 + depth * 12 }}
        >
          {span.input_preview ? (
            <pre className="max-h-24 overflow-auto whitespace-pre-wrap break-all">
              in: {span.input_preview}
            </pre>
          ) : null}
          {span.output_preview ? (
            <pre className="max-h-24 overflow-auto whitespace-pre-wrap break-all">
              out: {span.output_preview}
            </pre>
          ) : null}
        </div>
      ) : null}
      {open && children.length > 0 ? (
        <ul>
          {children.map((child) => (
            <SpanRow key={child.span_id} span={child} depth={depth + 1} />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

export function ChatTraceInspector({ sessionId, runId, className }: ChatTraceInspectorProps) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [detail, setDetail] = useState<TraceDetail | null>(null);
  const [summaries, setSummaries] = useState<TraceSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(runId ?? null);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      let list: TraceSummary[] = [];
      if (sessionId && sessionId !== '—') {
        list = await tracesApi.listSession(sessionId, 10);
        setSummaries(list);
      } else {
        setSummaries([]);
      }
      const preferred = runId || list[0]?.trace_id || null;
      setActiveId(preferred);
      if (preferred) {
        const d = await tracesApi.get(preferred);
        setDetail(d);
      } else {
        setDetail(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [sessionId, runId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    (async () => {
      try {
        const d = await tracesApi.get(runId);
        if (!cancelled) {
          setActiveId(runId);
          setDetail(d);
        }
      } catch {
        /* ignore until persisted */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [runId]);

  const handleSelect = async (traceId: string) => {
    setActiveId(traceId);
    setLoading(true);
    try {
      setDetail(await tracesApi.get(traceId));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleExport = async () => {
    if (!activeId) return;
    setExporting(true);
    try {
      const text = await tracesApi.exportJsonl(activeId);
      const blob = new Blob([text], { type: 'application/x-ndjson' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `trace-${activeId}.jsonl`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setExporting(false);
    }
  };

  const tree = detail?.tree?.length ? detail.tree : detail?.spans ?? [];

  return (
    <section className={cn('space-y-1.5', className)}>
      <div className="flex items-center gap-2">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground-tertiary">
          {t('chat.execution.panel.trace')}
        </h3>
        {loading ? <Loader2 className="h-3 w-3 animate-spin text-muted-foreground-tertiary" /> : null}
        <button
          type="button"
          disabled={!activeId || exporting}
          onClick={() => void handleExport()}
          className="ml-auto inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-muted-foreground hover:bg-muted/40 hover:text-foreground disabled:opacity-40"
          title={t('chat.execution.panel.traceExport')}
        >
          <Download className="h-3 w-3" />
          {t('chat.execution.panel.traceExport')}
        </button>
      </div>

      {summaries.length > 1 ? (
        <select
          className="w-full rounded border border-border bg-background px-1.5 py-1 text-[11px]"
          value={activeId ?? ''}
          onChange={(e) => void handleSelect(e.target.value)}
        >
          {summaries.map((s) => (
            <option key={s.trace_id} value={s.trace_id}>
              {s.model || s.agent_name || s.trace_id.slice(0, 8)} · {s.status} ·{' '}
              {Math.round(s.latency_ms)}ms
            </option>
          ))}
        </select>
      ) : null}

      {error ? (
        <p className="text-[11px] text-red-600 dark:text-red-400">{error}</p>
      ) : null}

      {detail?.trace ? (
        <p className="text-[11px] text-muted-foreground">
          {detail.trace.model || '—'} · {detail.trace.status}
          {detail.trace.terminal_reason ? ` (${detail.trace.terminal_reason})` : ''} ·{' '}
          {detail.trace.llm_call_count} LLM · {detail.trace.tool_call_count} tools ·{' '}
          {detail.trace.input_tokens + detail.trace.output_tokens} tok
        </p>
      ) : !loading ? (
        <p className="text-[11px] text-muted-foreground-tertiary">
          {t('chat.execution.panel.traceEmpty')}
        </p>
      ) : null}

      {tree.length > 0 ? (
        <ul className="max-h-48 overflow-y-auto rounded border border-border-subtle/60 bg-background/40 py-0.5">
          {tree.map((span) => (
            <SpanRow key={span.span_id} span={span} />
          ))}
        </ul>
      ) : null}
    </section>
  );
}
