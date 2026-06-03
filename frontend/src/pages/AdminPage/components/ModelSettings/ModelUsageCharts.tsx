import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import type { TooltipProps } from 'recharts';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui';
import {
  formatCompactNumber,
  formatLatencyAxisTick,
  formatLatencyMs,
  formatUsd,
  truncateModelName,
} from '../shared/adminFormat';
import { chartLegendStyle, seriesColor, useChartTheme } from './chartTheme';
import type { ModelUsageRow, UsageSummary, UsageTrendRow } from '@/types/admin';
import { parseApiDateTime } from '@/lib/utils';

interface ModelUsageChartsProps {
  usage: UsageSummary | undefined;
  trends: UsageTrendRow[] | undefined;
  isLoading: boolean;
}

interface LatencyChartRow {
  model: string;
  fullModel: string;
  latency: number;
}

function formatBucketLabel(bucket: string): string {
  try {
    const d = parseApiDateTime(bucket);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  } catch {
    return bucket.slice(5, 10);
  }
}

function buildTokenShare(rows: ModelUsageRow[], otherLabel: string) {
  const sorted = [...rows].sort((a, b) => b.total_tokens - a.total_tokens);
  const top = sorted.slice(0, 8);
  const restTokens = sorted.slice(8).reduce((s, r) => s + r.total_tokens, 0);
  const data = top.map((r) => ({
    name: r.model,
    label: truncateModelName(r.model, 18),
    value: r.total_tokens,
  }));
  if (restTokens > 0) {
    data.push({ name: otherLabel, label: otherLabel, value: restTokens });
  }
  return data;
}

function buildLatencyData(rows: ModelUsageRow[]): LatencyChartRow[] {
  return [...rows]
    .filter((r) => r.request_count > 0 && r.avg_latency_ms > 0)
    .sort((a, b) => b.avg_latency_ms - a.avg_latency_ms)
    .slice(0, 10)
    .map((r) => ({
      fullModel: r.model,
      model: truncateModelName(r.model, 22),
      latency: Math.round(r.avg_latency_ms),
    }));
}

function buildCostData(rows: ModelUsageRow[]) {
  return [...rows]
    .filter((r) => (r.total_cost_usd ?? 0) > 0)
    .sort((a, b) => (b.total_cost_usd ?? 0) - (a.total_cost_usd ?? 0))
    .slice(0, 10)
    .map((r) => ({
      fullModel: r.model,
      model: truncateModelName(r.model, 22),
      cost: Number((r.total_cost_usd ?? 0).toFixed(4)),
    }));
}

function ChartEmpty({ message }: { message: string }) {
  return (
    <div className="flex h-[280px] items-center justify-center text-sm text-text-secondary">
      {message}
    </div>
  );
}

function ModelLatencyTooltip({
  active,
  payload,
  labelKey = 'fullModel',
}: TooltipProps<number, string> & { labelKey?: string }) {
  const { t } = useTranslation();
  const theme = useChartTheme();
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload as Record<string, unknown> | undefined;
  const name = String(row?.[labelKey] ?? row?.model ?? '');
  const latency = payload[0]?.value as number;
  return (
    <div style={theme.tooltip} className="px-3 py-2 shadow-sm">
      <p className="font-mono text-xs mb-1 break-all">{name}</p>
      <p className="text-xs text-text-secondary">
        {t('admin.modelSettings.usage.avgLatency')}:{' '}
        <span className="font-medium text-text tabular-nums">{formatLatencyMs(latency)}</span>
      </p>
    </div>
  );
}

function PieTooltipContent({ active, payload }: TooltipProps<number, string>) {
  const { t } = useTranslation();
  const theme = useChartTheme();
  if (!active || !payload?.length) return null;
  const item = payload[0];
  const name = String(item?.name ?? '');
  const value = item?.value as number;
  return (
    <div style={theme.tooltip} className="px-3 py-2 shadow-sm max-w-[220px]">
      <p className="font-mono text-xs break-all mb-1">{name}</p>
      <p className="text-xs text-text-secondary tabular-nums">
        {formatCompactNumber(value)} {t('admin.modelSettings.stats.tokens')}
      </p>
    </div>
  );
}

function TrendTooltipContent({ active, payload, label }: TooltipProps<number, string> & { label?: string | number }) {
  const { t } = useTranslation();
  const theme = useChartTheme();
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload as { requests?: number; tokens?: number; cost?: number } | undefined;
  return (
    <div style={theme.tooltip} className="px-3 py-2 shadow-sm">
      <p className="text-xs font-medium mb-1.5">{label}</p>
      <div className="space-y-0.5 text-xs text-text-secondary tabular-nums">
        <p>
          {t('admin.modelSettings.stats.requests')}:{' '}
          <span className="text-text">{formatCompactNumber(row?.requests ?? 0)}</span>
        </p>
        <p>
          {t('admin.modelSettings.stats.tokens')}:{' '}
          <span className="text-text">{formatCompactNumber(row?.tokens ?? 0)}</span>
        </p>
        <p>
          {t('admin.modelSettings.charts.cost')}:{' '}
          <span className="text-text">{formatUsd(row?.cost ?? 0)}</span>
        </p>
      </div>
    </div>
  );
}

export function ModelUsageCharts({ usage, trends, isLoading }: ModelUsageChartsProps) {
  const { t } = useTranslation();
  const theme = useChartTheme();

  const trendData = useMemo(
    () =>
      (trends ?? []).map((row) => ({
        date: formatBucketLabel(row.bucket),
        bucket: row.bucket,
        requests: row.request_count,
        tokens: row.total_tokens,
        cost: Number(row.total_cost_usd.toFixed(6)),
      })),
    [trends],
  );

  const maxTrendCost = useMemo(
    () => Math.max(0, ...trendData.map((d) => d.cost)),
    [trendData],
  );

  const tokenShare = useMemo(
    () => buildTokenShare(usage?.rows ?? [], t('admin.modelSettings.charts.other')),
    [usage?.rows, t],
  );

  const latencyData = useMemo(() => buildLatencyData(usage?.rows ?? []), [usage?.rows]);
  const costData = useMemo(() => buildCostData(usage?.rows ?? []), [usage?.rows]);

  const costAxisFormatter = useMemo(() => {
    if (maxTrendCost <= 0) return (v: number) => formatUsd(v);
    if (maxTrendCost < 0.1) return (v: number) => `$${v.toFixed(4)}`;
    if (maxTrendCost < 1) return (v: number) => `$${v.toFixed(3)}`;
    return (v: number) => formatUsd(v);
  }, [maxTrendCost]);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="h-[320px] rounded-xl bg-surface-sunken animate-pulse" />
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="h-[320px] rounded-xl bg-surface-sunken animate-pulse" />
          <div className="h-[320px] rounded-xl bg-surface-sunken animate-pulse" />
        </div>
      </div>
    );
  }

  const noData = !usage?.rows?.length && !trends?.length;

  if (noData) {
    return (
      <Card>
        <CardContent className="py-12">
          <ChartEmpty message={t('common.noData')} />
        </CardContent>
      </Card>
    );
  }

  const legendStyle = chartLegendStyle(theme);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">{t('admin.modelSettings.charts.dailyTrend')}</CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          {trendData.length === 0 ? (
            <ChartEmpty message={t('common.noData')} />
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <ComposedChart data={trendData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={theme.borderSubtle} strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="date"
                  tick={{ fill: theme.textMuted, fontSize: 11 }}
                  axisLine={{ stroke: theme.border }}
                  tickLine={false}
                />
                <YAxis
                  yAxisId="left"
                  tick={{ fill: theme.textMuted, fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v) => formatCompactNumber(v as number)}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  tick={{ fill: theme.textMuted, fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={costAxisFormatter}
                  domain={[0, maxTrendCost > 0 ? maxTrendCost * 1.15 : 'auto']}
                />
                <Tooltip
                  content={(props) => (
                    <TrendTooltipContent
                      active={props.active}
                      payload={props.payload as TooltipProps<number, string>['payload']}
                      label={props.label}
                    />
                  )}
                />
                <Legend
                  wrapperStyle={{ ...legendStyle, paddingTop: 8 }}
                  iconType="circle"
                  iconSize={8}
                />
                <Bar
                  yAxisId="left"
                  dataKey="requests"
                  name={t('admin.modelSettings.stats.requests')}
                  fill={theme.semantic.requests}
                  fillOpacity={0.88}
                  radius={[4, 4, 0, 0]}
                  maxBarSize={32}
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="cost"
                  name={t('admin.modelSettings.charts.cost')}
                  stroke={theme.semantic.cost}
                  strokeWidth={2}
                  dot={{ r: 3, fill: theme.semantic.cost, strokeWidth: 0 }}
                  activeDot={{ r: 4, fill: theme.semantic.tokens }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{t('admin.modelSettings.charts.tokenShare')}</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            {tokenShare.length === 0 ? (
              <ChartEmpty message={t('common.noData')} />
            ) : (
              <ResponsiveContainer width="100%" height={280}>
                <PieChart margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
                  <Pie
                    data={tokenShare}
                    dataKey="value"
                    nameKey="name"
                    cx="42%"
                    cy="50%"
                    innerRadius={52}
                    outerRadius={88}
                    paddingAngle={2}
                    stroke={theme.surface}
                    strokeWidth={2}
                  >
                    {tokenShare.map((_, i) => (
                      <Cell key={i} fill={seriesColor(theme, i)} />
                    ))}
                  </Pie>
                  <Tooltip content={<PieTooltipContent />} />
                  <Legend
                    layout="vertical"
                    align="right"
                    verticalAlign="middle"
                    iconType="circle"
                    iconSize={8}
                    formatter={(value: string) => (
                      <span className="text-xs text-text-secondary ml-1">
                        {truncateModelName(value, 20)}
                      </span>
                    )}
                    wrapperStyle={{ ...legendStyle, maxWidth: 140, lineHeight: '20px' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{t('admin.modelSettings.charts.latencyByModel')}</CardTitle>
            <p className="text-[11px] text-text-secondary mt-0.5">
              {t('admin.modelSettings.charts.latencyHint')}
            </p>
          </CardHeader>
          <CardContent className="pt-0">
            {latencyData.length === 0 ? (
              <ChartEmpty message={t('common.noData')} />
            ) : (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart
                  data={latencyData}
                  layout="vertical"
                  margin={{ top: 4, right: 16, left: 4, bottom: 4 }}
                >
                  <CartesianGrid stroke={theme.borderSubtle} strokeDasharray="3 3" horizontal={false} />
                  <XAxis
                    type="number"
                    tick={{ fill: theme.textMuted, fontSize: 11 }}
                    axisLine={{ stroke: theme.border }}
                    tickLine={false}
                    tickFormatter={(v) => `${formatLatencyAxisTick(v as number)} ms`}
                    domain={[0, 'auto']}
                  />
                  <YAxis
                    type="category"
                    dataKey="model"
                    width={112}
                    tick={{ fill: theme.textMuted, fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip content={<ModelLatencyTooltip labelKey="fullModel" />} />
                  <Bar dataKey="latency" radius={[0, 4, 4, 0]} maxBarSize={18}>
                    {latencyData.map((_, i) => (
                      <Cell key={i} fill={seriesColor(theme, i)} fillOpacity={0.9} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      {costData.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{t('admin.modelSettings.charts.costByModel')}</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <ResponsiveContainer width="100%" height={280}>
              <BarChart
                data={costData}
                layout="vertical"
                margin={{ top: 4, right: 16, left: 4, bottom: 4 }}
              >
                <CartesianGrid stroke={theme.borderSubtle} strokeDasharray="3 3" horizontal={false} />
                <XAxis
                  type="number"
                  tick={{ fill: theme.textMuted, fontSize: 11 }}
                  axisLine={{ stroke: theme.border }}
                  tickLine={false}
                  tickFormatter={(v) => formatUsd(v as number)}
                />
                <YAxis
                  type="category"
                  dataKey="model"
                  width={112}
                  tick={{ fill: theme.textMuted, fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const row = payload[0]?.payload as { fullModel?: string; cost?: number };
                    return (
                      <div style={theme.tooltip} className="px-3 py-2 shadow-sm">
                        <p className="font-mono text-xs break-all mb-1">{row?.fullModel}</p>
                        <p className="text-xs tabular-nums">{formatUsd(row?.cost ?? 0)}</p>
                      </div>
                    );
                  }}
                />
                <Bar dataKey="cost" radius={[0, 4, 4, 0]} maxBarSize={18}>
                  {costData.map((_, i) => (
                    <Cell key={i} fill={seriesColor(theme, i + 2)} fillOpacity={0.9} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
