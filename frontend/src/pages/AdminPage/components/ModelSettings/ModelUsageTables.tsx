import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui';
import { Paginator } from '@/components/common/Paginator';
import {
  formatCompactNumber,
  formatLatencyMs,
  formatRelativeTime,
  formatUsd,
} from '../shared/adminFormat';
import type { RequestLogRow, UsageSummary } from '@/types/admin';

const REQUEST_LOG_MAX = 100;
const DEFAULT_PAGE_SIZE = 20;

interface ModelUsageTablesProps {
  usage: UsageSummary | undefined;
  requestLogs: RequestLogRow[] | undefined;
}

export function ModelUsageTables({ usage, requestLogs }: ModelUsageTablesProps) {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  const logs = useMemo(
    () => (requestLogs ?? []).slice(0, REQUEST_LOG_MAX),
    [requestLogs],
  );

  useEffect(() => {
    setPage(1);
  }, [logs.length, pageSize]);

  const totalPages = Math.max(1, Math.ceil(logs.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const pageRows = useMemo(() => {
    const start = (safePage - 1) * pageSize;
    return logs.slice(start, start + pageSize);
  }, [logs, safePage, pageSize]);

  return (
    <>
      {usage && usage.rows.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-base">{t('admin.modelSettings.usage.title')}</CardTitle>
                <p className="text-xs text-text-secondary mt-0.5">
                  {t('admin.modelSettings.usage.desc', { days: usage.days })}
                </p>
              </div>
            </div>
          </CardHeader>
          <CardContent className="pt-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs font-medium text-text-secondary uppercase tracking-wide border-b border-border">
                  <th className="py-2 pr-4">{t('admin.modelSettings.usage.model')}</th>
                  <th className="py-2 px-4 text-right">{t('admin.modelSettings.usage.requests')}</th>
                  <th className="py-2 px-4 text-right">{t('admin.modelSettings.usage.inTokens')}</th>
                  <th className="py-2 px-4 text-right">{t('admin.modelSettings.usage.outTokens')}</th>
                  <th className="py-2 px-4 text-right">{t('admin.modelSettings.usage.totalTokens')}</th>
                  <th className="py-2 px-4 text-right">{t('admin.modelSettings.usage.cost')}</th>
                  <th className="py-2 px-4 text-right">{t('admin.modelSettings.usage.avgLatency')}</th>
                  <th className="py-2 pl-4">{t('admin.modelSettings.usage.lastUsed')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {usage.rows.map((row) => (
                  <tr key={row.model} className="hover:bg-surface-sunken/60">
                    <td className="py-2 pr-4 font-mono text-xs text-text truncate max-w-xs">
                      {row.model}
                    </td>
                    <td className="py-2 px-4 text-right tabular-nums">
                      {formatCompactNumber(row.request_count)}
                    </td>
                    <td className="py-2 px-4 text-right tabular-nums text-text-secondary">
                      {formatCompactNumber(row.total_input_tokens)}
                    </td>
                    <td className="py-2 px-4 text-right tabular-nums text-text-secondary">
                      {formatCompactNumber(row.total_output_tokens)}
                    </td>
                    <td className="py-2 px-4 text-right tabular-nums font-medium">
                      {formatCompactNumber(row.total_tokens)}
                    </td>
                    <td className="py-2 px-4 text-right tabular-nums text-text-secondary">
                      {row.total_cost_usd != null ? formatUsd(row.total_cost_usd) : '—'}
                    </td>
                    <td className="py-2 px-4 text-right tabular-nums text-text-secondary">
                      {formatLatencyMs(row.avg_latency_ms)}
                    </td>
                    <td className="py-2 pl-4 text-xs text-text-secondary">
                      {formatRelativeTime(row.last_used_at, t)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">{t('admin.modelSettings.requestLog.title')}</CardTitle>
          <p className="text-xs text-text-secondary">
            {t('admin.modelSettings.requestLog.desc', { max: REQUEST_LOG_MAX })}
          </p>
        </CardHeader>
        <CardContent className="pt-0">
          {logs.length === 0 ? (
            <p className="py-8 text-center text-sm text-text-secondary">{t('common.noData')}</p>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-text-secondary">
                      <th className="py-2.5 pr-4 font-medium">{t('admin.modelSettings.requestLog.time')}</th>
                      <th className="py-2.5 px-4 font-medium">{t('admin.modelSettings.requestLog.provider')}</th>
                      <th className="py-2.5 px-4 font-medium">{t('admin.modelSettings.requestLog.model')}</th>
                      <th className="py-2.5 px-4 text-right font-medium">{t('admin.modelSettings.requestLog.tokens')}</th>
                      <th className="py-2.5 px-4 text-right font-medium">{t('admin.modelSettings.requestLog.cost')}</th>
                      <th className="py-2.5 pl-4 text-right font-medium">{t('admin.modelSettings.requestLog.latency')}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border-subtle">
                    {pageRows.map((row) => (
                      <tr key={row.id} className="hover:bg-surface-sunken/60">
                        <td className="py-2.5 pr-4 text-xs text-text-secondary whitespace-nowrap">
                          {formatRelativeTime(row.created_at, t)}
                        </td>
                        <td className="py-2.5 px-4 text-text">{row.provider_name}</td>
                        <td className="py-2.5 px-4 font-mono text-xs text-text max-w-[200px] truncate" title={row.model}>
                          {row.model}
                        </td>
                        <td className="py-2.5 px-4 text-right tabular-nums text-text">
                          {formatCompactNumber(row.input_tokens + row.output_tokens)}
                        </td>
                        <td className="py-2.5 px-4 text-right tabular-nums text-text-secondary">
                          {formatUsd(row.total_cost_usd)}
                        </td>
                        <td className="py-2.5 pl-4 text-right tabular-nums text-text">
                          {formatLatencyMs(row.latency_ms)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Paginator
                className="mt-4 pt-4 border-t border-border"
                currentPage={safePage}
                totalPages={totalPages}
                totalItems={logs.length}
                pageSize={pageSize}
                pageSizeOptions={[10, 20, 50]}
                onPageChange={setPage}
                onPageSizeChange={(size) => {
                  setPageSize(size);
                  setPage(1);
                }}
                showPageSizeSelector
                showPageInfo
              />
            </>
          )}
        </CardContent>
      </Card>
    </>
  );
}
