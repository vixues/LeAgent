import { useTranslation } from 'react-i18next';
import { CheckCircle, Clock, GitBranch } from 'lucide-react';
import { Card, Badge } from '@/components/ui';
import { useDashboardTasks } from '@/hooks/useDashboard';
import { formatRelativeTime } from '@/lib/utils';
import type { Task } from '@/types/admin';

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)}m`;
}

export function DueThisWeekCard() {
  const { t } = useTranslation();
  const { data: tasksData, isLoading } = useDashboardTasks({
    page: 1,
    pageSize: 5,
    status: 'completed',
  });

  const completedTasks = tasksData?.items ?? [];

  return (
    <Card className="h-full flex flex-col">
      <div className="p-4 border-b border-border flex items-center justify-between">
        <h3 className="font-semibold text-sm text-foreground">
          {t('dashboard.recentCompletions', { defaultValue: '最近完成' })}
        </h3>
        {completedTasks.length > 0 && (
          <Badge variant="success">{completedTasks.length}</Badge>
        )}
      </div>
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="p-4 text-sm text-muted-foreground text-center">
            {t('common.loading')}
          </div>
        ) : completedTasks.length > 0 ? (
          <div className="divide-y divide-border">
            {completedTasks.map((task: Task) => (
              <div
                key={task.id}
                className="flex items-start gap-3 p-3 hover:bg-surface-sunken/80 transition-colors"
              >
                <div className="flex-shrink-0 mt-0.5">
                  <div className="w-7 h-7 rounded-lg bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                    <CheckCircle className="w-3.5 h-3.5 text-green-600 dark:text-green-400" />
                  </div>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">
                    {task.name}
                  </p>
                  <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                    {task.duration_ms != null && task.duration_ms > 0 && (
                      <span className="flex items-center gap-0.5">
                        <Clock className="w-3 h-3" />
                        {formatDuration(task.duration_ms)}
                      </span>
                    )}
                    <span>
                      {task.completed_at ? formatRelativeTime(task.completed_at) : ''}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center p-6 text-center">
            <div className="w-10 h-10 rounded-xl bg-surface-sunken flex items-center justify-center mb-2">
              <GitBranch className="w-5 h-5 text-muted-foreground" />
            </div>
            <p className="text-sm text-muted-foreground">
              {t('dashboard.noCompletions', { defaultValue: '暂无已完成任务' })}
            </p>
          </div>
        )}
      </div>
    </Card>
  );
}

export default DueThisWeekCard;
