import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Play, RefreshCw } from 'lucide-react';
import { tracesApi, type TraceSummary } from '@/api/traces';
import { adminApi } from '@/api/admin';
import { Button } from '@/components/ui';
import { SectionHeader } from '@/components/common/SectionHeader';
import { PageLoader } from '@/components/common/PageLoader';
import { ChatTraceInspector } from '@/components/chat/ChatTraceInspector';
import { cn } from '@/lib/utils';

type SubTab = 'runs' | 'byModel' | 'compare';

function formatMs(v: number): string {
  if (!v) return '—';
  if (v < 1000) return `${Math.round(v)}ms`;
  return `${(v / 1000).toFixed(1)}s`;
}

function TraceRunsTable({
  rows,
  selected,
  onSelect,
}: {
  rows: TraceSummary[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const { t } = useTranslation();
  if (rows.length === 0) {
    return <p className="text-sm text-muted-foreground">{t('admin.traces.empty')}</p>;
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="min-w-full text-left text-xs">
        <thead className="bg-muted/40 text-muted-foreground">
          <tr>
            <th className="px-2 py-1.5 font-medium">{t('admin.traces.colModel')}</th>
            <th className="px-2 py-1.5 font-medium">{t('admin.traces.colStatus')}</th>
            <th className="px-2 py-1.5 font-medium">{t('admin.traces.colLatency')}</th>
            <th className="px-2 py-1.5 font-medium">{t('admin.traces.colTokens')}</th>
            <th className="px-2 py-1.5 font-medium">{t('admin.traces.colTools')}</th>
            <th className="px-2 py-1.5 font-medium">{t('admin.traces.colSession')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.trace_id}
              className={cn(
                'cursor-pointer border-t border-border/60 hover:bg-muted/30',
                selected === row.trace_id && 'bg-primary-50/60 dark:bg-primary-950/30',
              )}
              onClick={() => onSelect(row.trace_id)}
            >
              <td className="px-2 py-1.5 font-mono">{row.model || '—'}</td>
              <td className="px-2 py-1.5">{row.status}</td>
              <td className="px-2 py-1.5 tabular-nums">{formatMs(row.latency_ms)}</td>
              <td className="px-2 py-1.5 tabular-nums">
                {row.input_tokens + row.output_tokens}
              </td>
              <td className="px-2 py-1.5 tabular-nums">{row.tool_call_count}</td>
              <td className="max-w-[140px] truncate px-2 py-1.5 font-mono text-muted-foreground">
                {row.session_id ?? '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function AgentTraces() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [subTab, setSubTab] = useState<SubTab>('runs');
  const [days, setDays] = useState(30);
  const [modelFilter, setModelFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [selectedTrace, setSelectedTrace] = useState<string | null>(null);
  const [prompt, setPrompt] = useState('');
  const [selectedModels, setSelectedModels] = useState<string[]>([]);
  const [activeExperiment, setActiveExperiment] = useState<string | null>(null);

  const [refreshing, setRefreshing] = useState(false);

  const tracesQuery = useQuery({
    queryKey: ['traces', 'list', modelFilter, statusFilter],
    queryFn: () =>
      tracesApi.list({
        model: modelFilter || undefined,
        status: statusFilter || undefined,
        limit: 100,
      }),
  });

  const statsQuery = useQuery({
    queryKey: ['traces', 'stats', days],
    queryFn: () => tracesApi.statsByModel(days),
    enabled: subTab === 'byModel',
  });

  const experimentsQuery = useQuery({
    queryKey: ['traces', 'experiments'],
    queryFn: () => tracesApi.listExperiments(30),
    enabled: subTab === 'compare',
  });

  const modelsQuery = useQuery({
    queryKey: ['models', 'available'],
    queryFn: () => adminApi.availableModels.list(),
    enabled: subTab === 'compare',
  });

  const createRunMutation = useMutation({
    mutationFn: async () => {
      const exp = await tracesApi.createExperiment({
        name: `compare-${Date.now()}`,
        prompt,
        model_ids: selectedModels,
      });
      return tracesApi.runExperiment(exp.experiment_id);
    },
    onSuccess: (exp) => {
      setActiveExperiment(exp.experiment_id);
      void queryClient.invalidateQueries({ queryKey: ['traces'] });
    },
  });

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await queryClient.invalidateQueries({ queryKey: ['traces'] });
    } finally {
      setRefreshing(false);
    }
  };

  const availableModels = useMemo(
    () =>
      (modelsQuery.data ?? [])
        .filter((m) => m.kind === 'chat')
        .map((m) => m.model_name)
        .filter(Boolean),
    [modelsQuery.data],
  );

  const selectedDetailSession =
    tracesQuery.data?.find((r) => r.trace_id === selectedTrace)?.session_id ?? null;

  if (tracesQuery.isLoading && subTab === 'runs') {
    return (
      <div className="flex items-center justify-center py-12">
        <PageLoader size="sm" message={t('common.loading')} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <SectionHeader
        titleAs="h2"
        title={t('admin.traces.title')}
        description={t('admin.traces.subtitle')}
        titleClassName="text-xl"
        actions={
          <Button
            type="button"
            size="sm"
            variant="secondary"
            leftIcon={<RefreshCw className="h-4 w-4" aria-hidden />}
            loading={refreshing}
            onClick={() => void handleRefresh()}
          >
            {t('common.refresh')}
          </Button>
        }
      />

      <div className="flex gap-1 rounded-lg bg-gray-100 p-1 dark:bg-gray-800">
        {(['runs', 'byModel', 'compare'] as const).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setSubTab(key)}
            className={cn(
              'rounded-md px-3 py-1 text-xs font-medium transition-colors',
              subTab === key
                ? 'bg-white text-gray-900 shadow-sm dark:bg-surface dark:text-white'
                : 'text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white',
            )}
          >
            {t(`admin.traces.tabs.${key}`)}
          </button>
        ))}
      </div>

      {subTab === 'runs' ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <input
                className="rounded border border-border bg-background px-2 py-1 text-xs"
                placeholder={t('admin.traces.filterModel')}
                value={modelFilter}
                onChange={(e) => setModelFilter(e.target.value)}
              />
              <input
                className="rounded border border-border bg-background px-2 py-1 text-xs"
                placeholder={t('admin.traces.filterStatus')}
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              />
            </div>
            <TraceRunsTable
              rows={tracesQuery.data ?? []}
              selected={selectedTrace}
              onSelect={setSelectedTrace}
            />
          </div>
          <div className="rounded-lg border border-border p-3">
            {selectedTrace && selectedDetailSession ? (
              <ChatTraceInspector sessionId={selectedDetailSession} runId={selectedTrace} />
            ) : selectedTrace ? (
              <ChatTraceInspector sessionId="—" runId={selectedTrace} />
            ) : (
              <p className="text-sm text-muted-foreground">{t('admin.traces.selectRun')}</p>
            )}
          </div>
        </div>
      ) : null}

      {subTab === 'byModel' ? (
        <div className="space-y-3">
          <div className="flex gap-1 rounded-lg bg-gray-100 p-1 dark:bg-gray-800">
            {[7, 30, 90].map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => setDays(d)}
                className={cn(
                  'rounded-md px-3 py-1 text-xs font-medium transition-colors',
                  days === d
                    ? 'bg-white text-gray-900 shadow-sm dark:bg-surface dark:text-white'
                    : 'text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white',
                )}
              >
                {d}d
              </button>
            ))}
          </div>
          {statsQuery.isLoading ? (
            <PageLoader size="sm" message={t('common.loading')} />
          ) : (
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="min-w-full text-left text-xs">
                <thead className="bg-muted/40 text-muted-foreground">
                  <tr>
                    <th className="px-2 py-1.5">{t('admin.traces.colModel')}</th>
                    <th className="px-2 py-1.5">{t('admin.traces.colRuns')}</th>
                    <th className="px-2 py-1.5">{t('admin.traces.colSuccess')}</th>
                    <th className="px-2 py-1.5">{t('admin.traces.colLatency')}</th>
                    <th className="px-2 py-1.5">p95</th>
                    <th className="px-2 py-1.5">{t('admin.traces.colTokens')}</th>
                    <th className="px-2 py-1.5">{t('admin.traces.colCost')}</th>
                    <th className="px-2 py-1.5">{t('admin.traces.colTools')}</th>
                  </tr>
                </thead>
                <tbody>
                  {(statsQuery.data ?? []).map((row) => (
                    <tr key={row.model} className="border-t border-border/60">
                      <td className="px-2 py-1.5 font-mono">{row.model}</td>
                      <td className="px-2 py-1.5 tabular-nums">{row.runs}</td>
                      <td className="px-2 py-1.5 tabular-nums">
                        {(row.success_rate * 100).toFixed(1)}%
                      </td>
                      <td className="px-2 py-1.5 tabular-nums">
                        {formatMs(row.avg_latency_ms)}
                      </td>
                      <td className="px-2 py-1.5 tabular-nums">
                        {formatMs(row.p95_latency_ms)}
                      </td>
                      <td className="px-2 py-1.5 tabular-nums">
                        {Math.round(row.avg_input_tokens + row.avg_output_tokens)}
                      </td>
                      <td className="px-2 py-1.5 tabular-nums">
                        ${row.avg_cost_usd.toFixed(4)}
                      </td>
                      <td className="px-2 py-1.5 tabular-nums">
                        {row.avg_tool_calls.toFixed(1)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : null}

      {subTab === 'compare' ? (
        <div className="space-y-4">
          <div className="space-y-2 rounded-lg border border-border p-3">
            <label className="block text-xs font-medium text-muted-foreground">
              {t('admin.traces.comparePrompt')}
            </label>
            <textarea
              className="min-h-[80px] w-full rounded border border-border bg-background px-2 py-1.5 text-sm"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder={t('admin.traces.comparePromptPlaceholder')}
            />
            <label className="block text-xs font-medium text-muted-foreground">
              {t('admin.traces.compareModels')}
            </label>
            <div className="flex max-h-32 flex-wrap gap-2 overflow-y-auto">
              {availableModels.map((id) => {
                const on = selectedModels.includes(id);
                return (
                  <button
                    key={id}
                    type="button"
                    onClick={() =>
                      setSelectedModels((prev) =>
                        on ? prev.filter((x) => x !== id) : [...prev, id],
                      )
                    }
                    className={cn(
                      'rounded-full border px-2 py-0.5 font-mono text-[11px]',
                      on
                        ? 'border-primary-500 bg-primary-50 text-primary-800 dark:bg-primary-950/40'
                        : 'border-border text-muted-foreground',
                    )}
                  >
                    {id}
                  </button>
                );
              })}
            </div>
            <Button
              type="button"
              size="sm"
              variant="primarySolid"
              leftIcon={<Play className="h-4 w-4" aria-hidden />}
              loading={createRunMutation.isPending}
              disabled={!prompt.trim() || selectedModels.length === 0}
              onClick={() => createRunMutation.mutate()}
            >
              {t('admin.traces.runCompare')}
            </Button>
            {createRunMutation.isError ? (
              <p className="text-xs text-red-600">
                {(createRunMutation.error as Error).message}
              </p>
            ) : null}
          </div>

          {(experimentsQuery.data ?? []).map((exp) => (
            <div
              key={exp.experiment_id}
              className={cn(
                'rounded-lg border border-border p-3',
                activeExperiment === exp.experiment_id && 'ring-1 ring-primary-400',
              )}
            >
              <div className="mb-2 flex items-center gap-2 text-sm">
                <span className="font-medium">{exp.name}</span>
                <span className="text-xs text-muted-foreground">{exp.status}</span>
                <span className="ml-auto text-[11px] text-muted-foreground">
                  {exp.model_ids.join(', ')}
                </span>
              </div>
              <p className="mb-2 line-clamp-2 text-xs text-muted-foreground">{exp.prompt}</p>
              <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
                {exp.traces.map((tr) => (
                  <div
                    key={tr.trace_id}
                    className="rounded border border-border-subtle bg-muted/20 p-2 text-xs"
                  >
                    <div className="font-mono font-medium">{tr.model || '—'}</div>
                    <div className="mt-1 text-muted-foreground">
                      {tr.status} · {formatMs(tr.latency_ms)} ·{' '}
                      {tr.input_tokens + tr.output_tokens} tok · {tr.tool_call_count} tools
                    </div>
                    {tr.error ? (
                      <div className="mt-1 line-clamp-2 text-red-600">{tr.error}</div>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
