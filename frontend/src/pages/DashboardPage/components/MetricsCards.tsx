import { useTranslation } from 'react-i18next';
import { CheckCircle, XCircle, Clock, Activity, TrendingUp, TrendingDown } from 'lucide-react';
import { Card, CardContent } from '@/components/ui';
import { useDashboardStats } from '@/hooks/useDashboard';

export function MetricsCards() {
  const { t } = useTranslation();
  const { data: stats, isLoading } = useDashboardStats();

  const metrics = [
    {
      id: 'tasks-today',
      label: t('dashboard.metrics.tasksToday'),
      value: stats?.tasksToday || 0,
      change: stats?.tasksChange || 0,
      icon: Activity,
      color: 'text-blue-600 dark:text-blue-400',
      bgColor: 'bg-blue-100 dark:bg-blue-900/30',
    },
    {
      id: 'success-rate',
      label: t('dashboard.metrics.successRate'),
      value: `${stats?.successRate || 0}%`,
      change: stats?.successRateChange || 0,
      icon: CheckCircle,
      color: 'text-green-600 dark:text-green-400',
      bgColor: 'bg-green-100 dark:bg-green-900/30',
    },
    {
      id: 'failed-tasks',
      label: t('dashboard.metrics.failedTasks'),
      value: stats?.failedTasks || 0,
      change: stats?.failedChange || 0,
      icon: XCircle,
      color: 'text-red-600 dark:text-red-400',
      bgColor: 'bg-red-100 dark:bg-red-900/30',
      invertChange: true,
    },
    {
      id: 'avg-duration',
      label: t('dashboard.metrics.avgDuration'),
      value: stats?.avgDuration || '0s',
      change: stats?.durationChange || 0,
      icon: Clock,
      color: 'text-blue-600 dark:text-blue-400',
      bgColor: 'bg-blue-100 dark:bg-blue-900/30',
      invertChange: true,
    },
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {metrics.map((metric) => {
        const isPositive = metric.invertChange
          ? metric.change < 0
          : metric.change > 0;
        const TrendIcon = isPositive ? TrendingUp : TrendingDown;

        return (
          <Card key={metric.id} className="hover:shadow-md transition-shadow">
            <CardContent>
              <div className="flex items-start justify-between">
                <div className={`p-2.5 rounded-xl ${metric.bgColor}`}>
                  <metric.icon className={`w-5 h-5 ${metric.color}`} />
                </div>
                {metric.change !== 0 && (
                  <div
                    className={`flex items-center gap-1 text-xs font-medium ${
                      isPositive
                        ? 'text-green-600 dark:text-green-400'
                        : 'text-red-600 dark:text-red-400'
                    }`}
                  >
                    <TrendIcon className="w-3 h-3" />
                    <span>{Math.abs(metric.change)}%</span>
                  </div>
                )}
              </div>
              <div className="mt-3">
                <p className="text-2xl font-bold text-foreground">
                  {isLoading ? '-' : metric.value}
                </p>
                <p className="text-sm text-muted-foreground mt-1">
                  {metric.label}
                </p>
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
