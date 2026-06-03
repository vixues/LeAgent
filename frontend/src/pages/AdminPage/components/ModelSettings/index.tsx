import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import { RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui';
import { PageLoader } from '@/components/common/PageLoader';
import { SectionHeader } from '@/components/common/SectionHeader';
import {
  useProviders,
  useModelUsageSummary,
  useUsageTrends,
  useRequestLogs,
} from '@/hooks/useAdmin';
import { cn } from '@/lib/utils';
import { ModelUsageOverview } from './ModelUsageOverview';
import { ModelUsageCharts } from './ModelUsageCharts';
import { ModelUsageTables } from './ModelUsageTables';
import { DefaultModelCard } from './DefaultModelCard';
import { TaskRoutingPanel } from './TaskRoutingPanel';

const TIME_RANGES = [7, 30, 90] as const;
type TimeRange = (typeof TIME_RANGES)[number];

export function ModelSettings() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [days, setDays] = useState<TimeRange>(30);
  const [refreshing, setRefreshing] = useState(false);

  const { data: providers, isLoading: providersLoading } = useProviders();
  const { data: usage, isLoading: usageLoading } = useModelUsageSummary(days);
  const { data: trends, isLoading: trendsLoading } = useUsageTrends(days);
  const { data: requestLogs } = useRequestLogs(days, 100);

  const chartsLoading = usageLoading || trendsLoading;

  const handleRefresh = async () => {
    setRefreshing(true);
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['models', 'usage'] }),
      queryClient.invalidateQueries({ queryKey: ['models', 'routing'] }),
      queryClient.invalidateQueries({ queryKey: ['models', 'default'] }),
      queryClient.invalidateQueries({ queryKey: ['models', 'providers'] }),
    ]);
    setRefreshing(false);
  };

  if (providersLoading) {
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
        title={t('admin.modelSettings.title')}
        description={t('admin.modelSettings.description')}
        titleClassName="text-xl"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex gap-1 p-1 bg-gray-100 dark:bg-gray-800 rounded-lg">
              {TIME_RANGES.map((range) => (
                <button
                  key={range}
                  type="button"
                  onClick={() => setDays(range)}
                  className={cn(
                    'px-3 py-1 text-xs font-medium rounded-md transition-colors',
                    days === range
                      ? 'bg-white dark:bg-surface text-gray-900 dark:text-white shadow-sm'
                      : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white',
                  )}
                >
                  {t(`admin.modelSettings.timeRange.${range}d`)}
                </button>
              ))}
            </div>
            <Button
              size="sm"
              variant="secondary"
              leftIcon={<RefreshCw className="w-4 h-4" aria-hidden />}
              loading={refreshing}
              onClick={handleRefresh}
            >
              {t('admin.systemStatus.refresh')}
            </Button>
          </div>
        }
      />

      <ModelUsageOverview usage={usage} isLoading={usageLoading} />
      <ModelUsageCharts usage={usage} trends={trends} isLoading={chartsLoading} />

      {providers && providers.length > 0 && (
        <>
          <DefaultModelCard providers={providers} />
          <TaskRoutingPanel providers={providers} />
        </>
      )}

      <ModelUsageTables usage={usage} requestLogs={requestLogs} />
    </div>
  );
}
