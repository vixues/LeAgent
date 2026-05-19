import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardContent } from '@/components/ui';
import { useUsageData } from '@/hooks/useDashboard';
import { useDashboardStore } from '@/stores/dashboard';

export function UsageChart() {
  const { t } = useTranslation();
  const { timeRange } = useDashboardStore();
  const { data: usageData, isLoading } = useUsageData(timeRange);

  const maxValue = useMemo(() => {
    if (!usageData) return 100;
    return Math.max(...usageData.map((d) => Math.max(d.success, d.failed))) * 1.2;
  }, [usageData]);

  return (
    <Card className="h-full">
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
          {t('dashboard.usageChart')}
        </h2>
        <div className="flex items-center gap-4 mt-2">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-green-500" />
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {t('dashboard.chart.success')}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-red-500" />
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {t('dashboard.chart.failed')}
            </span>
          </div>
        </div>
      </div>
      <CardContent>
        {isLoading ? (
          <div className="h-64 flex items-center justify-center text-gray-500 dark:text-gray-400">
            {t('common.loading')}
          </div>
        ) : usageData && usageData.length > 0 ? (
          <div className="h-64 flex items-end gap-2">
            {usageData.map((item, index) => (
              <div key={index} className="flex-1 flex flex-col items-center gap-1">
                <div className="w-full flex flex-col gap-0.5" style={{ height: '200px' }}>
                  <div
                    className="w-full bg-red-500 rounded-t transition-[color,background-color,border-color,box-shadow,opacity,transform] duration-300"
                    style={{
                      height: `${(item.failed / maxValue) * 100}%`,
                    }}
                  />
                  <div
                    className="w-full bg-green-500 rounded-b transition-[color,background-color,border-color,box-shadow,opacity,transform] duration-300"
                    style={{
                      height: `${(item.success / maxValue) * 100}%`,
                    }}
                  />
                </div>
                <span className="text-xs text-gray-500 dark:text-gray-400 truncate w-full text-center">
                  {item.label}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="h-64 flex items-center justify-center text-gray-500 dark:text-gray-400">
            {t('common.noData')}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
