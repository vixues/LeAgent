import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { RefreshCw } from 'lucide-react';
import { apiClient } from '@/api/client';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui';
import { PageShell } from '@/components/layout/PageShell';
import { useAdminStore } from '@/stores/admin';
import { ModelProviderConfig } from './components/ModelProviderConfig';
import { ModelSettings } from './components/ModelSettings';
import { ToolManagement } from './components/ToolManagement';
import { RuleEditor } from './components/RuleEditor';
import { TaskMonitor } from './components/TaskMonitor';
import type { SystemDetailedHealth, SystemMetricsPayload, SystemVersionPayload } from '@/types/admin';

function formatUptime(sec: number): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (h > 48) return `${Math.floor(h / 24)}d ${h % 24}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function formatMetricValue(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(2);
  return String(v);
}

function formatComponentSummary(comp: Record<string, unknown>): string {
  const st = String(comp.status ?? '—');
  const bits: string[] = [st];
  if (typeof comp.latency_ms === 'number') bits.push(`${comp.latency_ms}ms`);
  if (comp.error != null && String(comp.error).length > 0) {
    bits.push(String(comp.error).slice(0, 120));
  }
  const c = comp.connected;
  const tot = comp.total;
  if (typeof c === 'number' && typeof tot === 'number') {
    bits.push(`${c}/${tot}`);
  }
  return bits.join(' · ');
}

function SystemStatusPanel() {
  const { t } = useTranslation();
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ['admin', 'system-status'],
    queryFn: async () => {
      const errors: { detailed?: string; version?: string; metrics?: string } = {};
      const settled = await Promise.allSettled([
        apiClient.get<SystemDetailedHealth>('/health/detailed'),
        apiClient.get<SystemVersionPayload>('/health/version'),
      ]);

      let detailed: SystemDetailedHealth | null = null;
      let version: SystemVersionPayload | null = null;
      if (settled[0].status === 'fulfilled') {
        detailed = settled[0].value;
      } else {
        const r = settled[0].reason;
        errors.detailed = r instanceof Error ? r.message : String(r);
      }
      if (settled[1].status === 'fulfilled') {
        version = settled[1].value;
      } else {
        const r = settled[1].reason;
        errors.version = r instanceof Error ? r.message : String(r);
      }

      if (!detailed && !version) {
        throw new Error(errors.detailed ?? errors.version ?? 'unavailable');
      }

      let metrics: SystemMetricsPayload | null = null;
      try {
        metrics = await apiClient.get<SystemMetricsPayload>('/metrics/health');
      } catch {
        try {
          metrics = await apiClient.get<SystemMetricsPayload>('/health/metrics');
        } catch {
          try {
            const basic = await apiClient.get<{ uptime_seconds?: number; status?: string; version?: string }>('/health');
            metrics = {
              uptime_seconds: basic.uptime_seconds,
              status: basic.status,
              version: basic.version,
            };
          } catch (e) {
            errors.metrics = e instanceof Error ? e.message : String(e);
            metrics = null;
          }
        }
      }

      return { detailed, version, metrics, errors };
    },
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

  const status = data?.detailed?.status ?? 'unknown';
  const hasDetailed = data?.detailed != null;
  const healthy = hasDetailed && status === 'healthy';
  const degraded = hasDetailed && status === 'degraded';

  const metricEntries = data?.metrics
    ? Object.entries(data.metrics).filter(([, v]) => v !== undefined && v !== '')
    : [];

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-surface/50 p-4 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-wrap items-start gap-8">
          <div>
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
              {t('admin.systemStatus.service')}
            </p>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              {isLoading ? (
                <span className="text-sm text-gray-500 dark:text-gray-400">{t('admin.systemStatus.loading')}</span>
              ) : !hasDetailed ? (
                <span className="text-sm text-gray-500 dark:text-gray-400">—</span>
              ) : (
                <>
                  <span
                    className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      healthy
                        ? 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300'
                        : degraded
                          ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
                          : 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300'
                    }`}
                  >
                    {healthy ? t('admin.systemStatus.healthy') : degraded ? t('admin.systemStatus.degraded') : t('admin.systemStatus.unhealthy')}
                  </span>
                  {data?.detailed?.uptime_seconds != null && (
                    <span className="text-sm text-gray-600 dark:text-gray-300">
                      {t('admin.systemStatus.uptime', { uptime: formatUptime(data.detailed.uptime_seconds) })}
                    </span>
                  )}
                </>
              )}
            </div>
            {data?.errors?.detailed && (
              <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">{t('admin.systemStatus.partialDetailed')}</p>
            )}
          </div>
          <div>
            <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
              {t('admin.systemStatus.version')}
            </p>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
              <p className="text-sm text-gray-900 dark:text-white font-mono">
                {data?.version?.version ?? '—'}
                {data?.version?.build && (
                  <span className="text-gray-500 dark:text-gray-400 ml-2">({data.version.build})</span>
                )}
              </p>
              {data?.version?.api_version && (
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  {t('admin.systemStatus.apiVersion', { version: data.version.api_version })}
                </span>
              )}
              {data?.version?.python_version && (
                <span className="text-xs text-gray-500 dark:text-gray-400">{data.version.python_version}</span>
              )}
            </div>
            {data?.errors?.version && (
              <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">{t('admin.systemStatus.partialVersion')}</p>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={() => refetch()}
          className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700"
          disabled={isFetching}
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? 'animate-spin' : ''}`} />
          {t('admin.systemStatus.refresh')}
        </button>
      </div>

      {isError && (
        <p className="mt-3 text-sm text-red-600 dark:text-red-400">{t('admin.systemStatus.loadError')}</p>
      )}

      {data?.detailed?.components && Object.keys(data.detailed.components).length > 0 && (
        <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">{t('admin.systemStatus.components')}</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(data.detailed.components).map(([name, comp]) => (
              <span
                key={name}
                className="inline-flex max-w-full items-start gap-1 rounded-md bg-gray-100 dark:bg-gray-700/80 px-2 py-1 text-xs text-gray-700 dark:text-gray-200"
                title={formatComponentSummary(comp as Record<string, unknown>)}
              >
                <span className="font-medium capitalize shrink-0">{name}</span>
                <span className="text-gray-500 dark:text-gray-400 break-words">
                  {formatComponentSummary(comp as Record<string, unknown>)}
                </span>
              </span>
            ))}
          </div>
        </div>
      )}

      {(metricEntries.length > 0 || data?.errors?.metrics) && (
        <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">{t('admin.systemStatus.metrics')}</p>
          {data?.errors?.metrics && !metricEntries.length && (
            <p className="text-xs text-amber-700 dark:text-amber-300">{t('admin.systemStatus.partialMetrics')}</p>
          )}
          {metricEntries.length > 0 && (
            <dl className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
              {metricEntries.slice(0, 8).map(([key, value]) => (
                <div key={key}>
                  <dt className="text-gray-500 dark:text-gray-400 capitalize">{key.replace(/_/g, ' ')}</dt>
                  <dd className="font-mono text-gray-900 dark:text-white">{formatMetricValue(value)}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      )}
    </div>
  );
}

export default function AdminPage() {
  const { t } = useTranslation();
  const { activeTab, setActiveTab } = useAdminStore();

  return (
    <PageShell
      title={t('admin.title')}
      description={t('admin.description')}
    >
      <SystemStatusPanel />

      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as typeof activeTab)}>
        <TabsList className="mb-6 flex-wrap">
            <TabsTrigger value="providers">
              <span className="flex items-center gap-2">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                </svg>
                {t('admin.tabs.providers')}
              </span>
            </TabsTrigger>
            <TabsTrigger value="modelSettings">
              <span className="flex items-center gap-2">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
                {t('admin.tabs.modelSettings')}
              </span>
            </TabsTrigger>
            <TabsTrigger value="tools">
              <span className="flex items-center gap-2">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
                {t('admin.tabs.tools')}
              </span>
            </TabsTrigger>
            <TabsTrigger value="rules">
              <span className="flex items-center gap-2">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
                </svg>
                {t('admin.tabs.rules')}
              </span>
            </TabsTrigger>
            <TabsTrigger value="tasks">
              <span className="flex items-center gap-2">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                </svg>
                {t('admin.tabs.tasks')}
              </span>
            </TabsTrigger>
          </TabsList>

          <TabsContent value="providers" className="mt-4">
            <ModelProviderConfig />
          </TabsContent>
          <TabsContent value="modelSettings" className="mt-4">
            <ModelSettings />
          </TabsContent>
          <TabsContent value="tools" className="mt-4">
            <ToolManagement />
          </TabsContent>
          <TabsContent value="rules" className="mt-4">
            <RuleEditor />
          </TabsContent>
          <TabsContent value="tasks" className="mt-4">
            <TaskMonitor />
          </TabsContent>
        </Tabs>
    </PageShell>
  );
}
