import { useCallback, useEffect, useMemo, useState } from 'react';
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

/** Prefer short OpenInference / gen_ai labels in the inspector. */
const ATTR_LABELS: Record<string, string> = {
  'gen_ai.provider.name': 'provider',
  'gen_ai.request.model': 'request_model',
  'gen_ai.response.model': 'model',
  'gen_ai.usage.input_tokens': 'input_tokens',
  'gen_ai.usage.output_tokens': 'output_tokens',
  'gen_ai.usage.cache_read_tokens': 'cache_read',
  'gen_ai.usage.cache_miss_tokens': 'cache_miss',
  'gen_ai.operation.name': 'operation',
  'openinference.span.kind': 'kind',
  'tool.name': 'tool',
  'tool.call_id': 'call_id',
  'tool.success': 'success',
  'error.message': 'error',
  latency_ms: 'latency_ms',
  ttfb_ms: 'ttfb_ms',
  status_code: 'status',
  is_streaming: 'streaming',
  call_index: 'call#',
  call_kind: 'call_kind',
  total_cost_usd: 'cost_usd',
  scope: 'scope',
  agent_name: 'agent',
  phase: 'phase',
  reason: 'reason',
};

function kindIcon(kind: string) {
  if (kind === 'llm') return <Cpu className="h-3 w-3 shrink-0 text-sky-500" />;
  if (kind === 'tool') return <Wrench className="h-3 w-3 shrink-0 text-amber-500" />;
  if (kind === 'error') return <AlertCircle className="h-3 w-3 shrink-0 text-red-500" />;
  return <Bot className="h-3 w-3 shrink-0 text-muted-foreground-tertiary" />;
}

function normalizeAttrs(raw: TraceSpan['attrs']): Record<string, unknown> {
  if (!raw) return {};
  if (typeof raw === 'string') {
    try {
      const parsed = JSON.parse(raw) as unknown;
      return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
        ? (parsed as Record<string, unknown>)
        : {};
    } catch {
      return {};
    }
  }
  if (typeof raw === 'object' && !Array.isArray(raw)) return raw;
  return {};
}

function formatAttrValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return String(value);
    return Number.isInteger(value) ? String(value) : value.toFixed(3).replace(/\.?0+$/, '');
  }
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

/** Build Codex-style JSONL from an already-loaded TraceDetail (offline fallback). */
function buildTraceJsonlFromDetail(detail: TraceDetail): string {
  const lines: string[] = [
    JSON.stringify({
      type: 'manifest',
      schema: 'leagent.agent_trace.v1',
      trace: detail.trace,
    }),
  ];
  const flat: TraceSpan[] = [];
  const walk = (nodes: TraceSpan[]) => {
    for (const node of nodes) {
      const { children, ...rest } = node;
      flat.push(rest);
      if (children?.length) walk(children);
    }
  };
  if (detail.spans?.length) {
    for (const span of detail.spans) {
      const { children: _ch, ...rest } = span;
      void _ch;
      flat.push(rest);
    }
  } else if (detail.tree?.length) {
    walk(detail.tree);
  }
  flat.sort((a, b) => (a.seq ?? 0) - (b.seq ?? 0));
  for (const span of flat) {
    lines.push(JSON.stringify({ type: 'span', span }));
  }
  return `${lines.join('\n')}\n`;
}

function SpanAttrRows({ attrs }: { attrs: Record<string, unknown> }) {
  const entries = Object.entries(attrs).filter(([, v]) => v !== null && v !== undefined && v !== '');
  if (entries.length === 0) return null;

  // Stable, readable order: known labels first, then the rest alphabetically.
  const known = Object.keys(ATTR_LABELS);
  entries.sort(([a], [b]) => {
    const ia = known.indexOf(a);
    const ib = known.indexOf(b);
    if (ia >= 0 || ib >= 0) {
      if (ia < 0) return 1;
      if (ib < 0) return -1;
      return ia - ib;
    }
    return a.localeCompare(b);
  });

  return (
    <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-2 gap-y-0.5">
      {entries.map(([key, value]) => (
        <div key={key} className="contents">
          <dt className="shrink-0 text-muted-foreground-tertiary">{ATTR_LABELS[key] ?? key}</dt>
          <dd className="min-w-0 break-all text-foreground/80">{formatAttrValue(value)}</dd>
        </div>
      ))}
    </dl>
  );
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
  const attrs = useMemo(() => normalizeAttrs(span.attrs), [span.attrs]);
  const hasAttrs = Object.keys(attrs).length > 0;
  const hasDetail = Boolean(span.input_preview || span.output_preview || hasAttrs);
  const canExpand = hasDetail || children.length > 0;

  return (
    <li className="text-xs">
      <button
        type="button"
        className={cn(
          'flex w-full items-center gap-1.5 rounded px-1 py-0.5 text-left hover:bg-muted/40',
          span.status === 'error' && 'text-red-600 dark:text-red-400',
        )}
        style={{ paddingLeft: 4 + depth * 12 }}
        onClick={() => canExpand && setOpen((v) => !v)}
        aria-expanded={canExpand ? open : undefined}
      >
        {canExpand ? (
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
        <span className="shrink-0 text-[10px] uppercase tracking-wide text-muted-foreground-tertiary">
          {span.status && span.status !== 'ok' ? span.status : ''}
        </span>
        <span className="shrink-0 tabular-nums text-muted-foreground-tertiary">
          {span.latency_ms ? `${Math.round(span.latency_ms)}ms` : ''}
        </span>
      </button>
      {open && hasDetail ? (
        <div
          className="mb-1 space-y-1.5 rounded border border-border-subtle/60 bg-muted/20 p-1.5 font-mono text-[10px] text-muted-foreground"
          style={{ marginLeft: 16 + depth * 12 }}
        >
          <SpanAttrRows attrs={attrs} />
          {span.input_preview ? (
            <pre className="max-h-32 overflow-auto whitespace-pre-wrap break-all border-t border-border-subtle/40 pt-1">
              in: {span.input_preview}
            </pre>
          ) : null}
          {span.output_preview ? (
            <pre className="max-h-32 overflow-auto whitespace-pre-wrap break-all border-t border-border-subtle/40 pt-1">
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
    setError(null);
    try {
      let text: string;
      try {
        text = await tracesApi.exportJsonl(activeId);
      } catch (serverErr) {
        // Fallback: build JSONL from already-loaded detail so export still works
        // if the download route is blocked or briefly unavailable.
        if (!detail?.trace || detail.trace.trace_id !== activeId) throw serverErr;
        text = buildTraceJsonlFromDetail(detail);
      }
      const blob = new Blob([text], { type: 'application/x-ndjson' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `trace-${activeId}.jsonl`;
      a.rel = 'noopener';
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
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
        <ul className="max-h-[min(28rem,50vh)] overflow-y-auto rounded border border-border-subtle/60 bg-background/40 py-0.5">
          {tree.map((span) => (
            <SpanRow key={span.span_id} span={span} />
          ))}
        </ul>
      ) : null}
    </section>
  );
}
