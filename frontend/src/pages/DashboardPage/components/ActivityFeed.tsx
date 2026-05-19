import { useTranslation } from 'react-i18next';
import { CheckCircle, XCircle, Play, Pause, AlertTriangle } from 'lucide-react';
import { Card, CardContent } from '@/components/ui';
import { useActivityFeed } from '@/hooks/useDashboard';
import { formatRelativeTime } from '@/lib/utils';
import { cn } from '@/lib/utils';

type ActivityType = 'task_completed' | 'task_failed' | 'task_started' | 'workflow_paused' | 'warning';

export function ActivityFeed() {
  const { t } = useTranslation();
  const { data: activities, isLoading } = useActivityFeed();

  const getActivityIcon = (type: ActivityType) => {
    const icons: Record<ActivityType, { icon: typeof CheckCircle; color: string; bg: string }> = {
      task_completed: {
        icon: CheckCircle,
        color: 'text-green-600 dark:text-green-400',
        bg: 'bg-green-100 dark:bg-green-900/30',
      },
      task_failed: {
        icon: XCircle,
        color: 'text-red-600 dark:text-red-400',
        bg: 'bg-red-100 dark:bg-red-900/30',
      },
      task_started: {
        icon: Play,
        color: 'text-blue-600 dark:text-blue-400',
        bg: 'bg-blue-100 dark:bg-blue-900/30',
      },
      workflow_paused: {
        icon: Pause,
        color: 'text-yellow-600 dark:text-yellow-400',
        bg: 'bg-yellow-100 dark:bg-yellow-900/30',
      },
      warning: {
        icon: AlertTriangle,
        color: 'text-orange-600 dark:text-orange-400',
        bg: 'bg-orange-100 dark:bg-orange-900/30',
      },
    };
    return icons[type];
  };

  return (
    <Card className="h-full">
      <div className="p-4 border-b border-border">
        <h2 className="text-lg font-semibold text-foreground">
          {t('dashboard.activityFeed')}
        </h2>
      </div>
      <CardContent padding="none" className="max-h-96 overflow-y-auto">
        {isLoading ? (
          <div className="p-4 text-center text-muted-foreground">
            {t('common.loading')}
          </div>
        ) : activities && activities.length > 0 ? (
          <div className="divide-y divide-border">
            {activities.map((activity, index) => {
              const iconConfig = getActivityIcon(activity.type);
              const IconComponent = iconConfig.icon;
              
              return (
                <div
                  key={activity.id}
                  className={cn(
                    'flex gap-3 p-4 hover:bg-surface-sunken/80 transition-colors',
                    index === 0 && 'bg-primary-50/50 dark:bg-primary-900/10'
                  )}
                >
                  <div className={cn('flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center', iconConfig.bg)}>
                    <IconComponent className={cn('w-4 h-4', iconConfig.color)} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">
                      {activity.title}
                    </p>
                    <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                      {activity.description}
                    </p>
                    <p className="text-xs text-muted-foreground/70 mt-1">
                      {formatRelativeTime(activity.timestamp)}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="p-8 text-center text-muted-foreground">
            {t('dashboard.noActivity')}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
