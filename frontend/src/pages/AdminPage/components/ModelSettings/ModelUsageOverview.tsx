import { useTranslation } from 'react-i18next';
import { Zap, DollarSign, Activity, Layers } from 'lucide-react';
import { StatCard, formatCompactNumber, formatLatencyMs, formatUsd } from '../shared/adminFormat';
import type { UsageSummary } from '@/types/admin';

interface ModelUsageOverviewProps {
  usage: UsageSummary | undefined;
  isLoading: boolean;
}

export function ModelUsageOverview({ usage, isLoading }: ModelUsageOverviewProps) {
  const { t } = useTranslation();

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="h-24 rounded-xl bg-gray-100 dark:bg-surface animate-pulse"
          />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <StatCard
        label={t('admin.modelSettings.stats.requests')}
        value={formatCompactNumber(usage?.total_requests)}
        hint={
          usage?.days
            ? t('admin.modelSettings.stats.periodHint', { days: usage.days })
            : undefined
        }
        icon={<Zap className="w-5 h-5" />}
        accent="text-amber-600 dark:text-amber-400"
      />
      <StatCard
        label={t('admin.modelSettings.stats.tokens')}
        value={formatCompactNumber(usage?.total_tokens)}
        icon={<Layers className="w-5 h-5" />}
        accent="text-blue-600 dark:text-blue-400"
      />
      <StatCard
        label={t('admin.modelSettings.stats.cost')}
        value={formatUsd(usage?.total_cost_usd)}
        icon={<DollarSign className="w-5 h-5" />}
        accent="text-emerald-600 dark:text-emerald-400"
      />
      <StatCard
        label={t('admin.modelSettings.stats.avgLatency')}
        value={
          usage?.avg_latency_ms
            ? formatLatencyMs(usage.avg_latency_ms)
            : '—'
        }
        icon={<Activity className="w-5 h-5" />}
        accent="text-violet-600 dark:text-violet-400"
      />
    </div>
  );
}
