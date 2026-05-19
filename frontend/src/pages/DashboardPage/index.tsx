import { useTranslation } from 'react-i18next';
import { RefreshCw } from 'lucide-react';
import { Button, Select } from '@/components/ui';
import { PageShell } from '@/components/layout/PageShell';
import { useDashboardStore } from '@/stores/dashboard';
import { useDashboardStats } from '@/hooks/useDashboard';
import { MetricsCards } from './components/MetricsCards';
import { TaskTable } from './components/TaskTable';
import { ActivityFeed } from './components/ActivityFeed';
import { UsageChart } from './components/UsageChart';
import { DueThisWeekCard } from './components/DueThisWeekCard';

export default function DashboardPage() {
  const { t } = useTranslation();
  const { timeRange, setTimeRange } = useDashboardStore();
  const { refetch, isRefetching } = useDashboardStats();

  const timeRangeOptions = [
    { value: 'today', label: t('dashboard.timeRange.today') },
    { value: 'week', label: t('dashboard.timeRange.week') },
    { value: 'month', label: t('dashboard.timeRange.month') },
  ];

  return (
    <PageShell
      title={t('dashboard.title')}
      description={t('dashboard.description')}
      actions={
        <>
          <Select
            value={timeRange}
            onChange={(e) => setTimeRange(e.target.value as typeof timeRange)}
            className="w-32"
          >
            {timeRangeOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            loading={isRefetching}
            leftIcon={<RefreshCw className="w-4 h-4" />}
          >
            {t('dashboard.refresh')}
          </Button>
        </>
      }
    >
      <MetricsCards />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <UsageChart />
        </div>
        <div>
          <ActivityFeed />
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <TaskTable />
        </div>
        <div>
          <DueThisWeekCard />
        </div>
      </div>
    </PageShell>
  );
}
