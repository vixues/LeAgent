import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Search,
  Eye,
  RotateCcw,
  XCircle,
  GitBranch,
  Bot,
  Terminal,
  Wrench,
  Layers,
  Timer,
  Sparkles,
} from 'lucide-react';
import { Card, Button, Input, Badge, Select } from '@/components/ui';
import type { Task, TaskType, TaskStatus } from '@/types/admin';
import { useDashboardTasks } from '@/hooks/useDashboard';
import { formatRelativeTime, cn } from '@/lib/utils';

const taskTypeConfig: Record<
  TaskType,
  { icon: typeof GitBranch; label: string; color: string; bg: string }
> = {
  workflow: {
    icon: GitBranch,
    label: '工作流',
    color: 'text-primary-600 dark:text-primary-400',
    bg: 'bg-primary-100 dark:bg-primary-900/30',
  },
  agent: {
    icon: Bot,
    label: 'Agent',
    color: 'text-violet-600 dark:text-violet-400',
    bg: 'bg-violet-100 dark:bg-violet-900/30',
  },
  shell: {
    icon: Terminal,
    label: 'Shell',
    color: 'text-emerald-600 dark:text-emerald-400',
    bg: 'bg-emerald-100 dark:bg-emerald-900/30',
  },
  tool: {
    icon: Wrench,
    label: '工具',
    color: 'text-amber-600 dark:text-amber-400',
    bg: 'bg-amber-100 dark:bg-amber-900/30',
  },
  batch: {
    icon: Layers,
    label: '批量',
    color: 'text-sky-600 dark:text-sky-400',
    bg: 'bg-sky-100 dark:bg-sky-900/30',
  },
  dream: {
    icon: Sparkles,
    label: 'Dream',
    color: 'text-pink-600 dark:text-pink-400',
    bg: 'bg-pink-100 dark:bg-pink-900/30',
  },
};

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)}m`;
}

export function TaskTable() {
  const { t } = useTranslation();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<TaskStatus | 'all'>('all');
  const [page, setPage] = useState(1);

  const { data: tasksData, isLoading } = useDashboardTasks({
    page,
    pageSize: 10,
    search,
    status: statusFilter !== 'all' ? statusFilter : undefined,
  });

  const statusOptions: { value: TaskStatus | 'all'; label: string }[] = [
    { value: 'all', label: t('common.all') },
    { value: 'pending', label: t('tasks.pending') },
    { value: 'queued', label: t('tasks.queued', { defaultValue: 'Queued' }) },
    { value: 'running', label: t('tasks.active') },
    { value: 'completed', label: t('tasks.completed') },
    { value: 'failed', label: t('tasks.failed') },
    { value: 'cancelled', label: t('tasks.cancel') },
    { value: 'killed', label: t('tasks.killed', { defaultValue: 'Killed' }) },
    { value: 'timeout', label: t('tasks.timeout', { defaultValue: 'Timeout' }) },
  ];

  const getStatusBadge = (status: TaskStatus) => {
    const variants: Record<TaskStatus, 'default' | 'primary' | 'success' | 'error' | 'warning'> = {
      pending: 'default',
      queued: 'default',
      running: 'primary',
      completed: 'success',
      failed: 'error',
      cancelled: 'warning',
      killed: 'error',
      timeout: 'warning',
    };
    const labels: Record<TaskStatus, string> = {
      pending: t('tasks.pending'),
      queued: t('tasks.queued', { defaultValue: 'Queued' }),
      running: t('tasks.active'),
      completed: t('tasks.completed'),
      failed: t('tasks.failed'),
      cancelled: t('tasks.cancel'),
      killed: t('tasks.killed', { defaultValue: 'Killed' }),
      timeout: t('tasks.timeout', { defaultValue: 'Timeout' }),
    };
    return <Badge variant={variants[status]}>{labels[status]}</Badge>;
  };

  const getProgressColor = (status: TaskStatus) => {
    const colors: Record<TaskStatus, string> = {
      pending: 'bg-muted-foreground-tertiary',
      queued: 'bg-muted-foreground-tertiary',
      running: 'bg-primary-500',
      completed: 'bg-green-500',
      failed: 'bg-red-500',
      cancelled: 'bg-yellow-500',
      killed: 'bg-red-600',
      timeout: 'bg-orange-500',
    };
    return colors[status];
  };

  const renderTaskType = (task: Task) => {
    const config = taskTypeConfig[task.task_type] || taskTypeConfig.agent;
    const Icon = config.icon;
    return (
      <div className="flex items-center gap-2">
        <div className={cn('p-1.5 rounded-lg', config.bg)}>
          <Icon className={cn('w-3.5 h-3.5', config.color)} />
        </div>
        <span className="text-sm text-foreground font-medium">{config.label}</span>
      </div>
    );
  };

  const renderTimeCell = (task: Task) => {
    if (task.status === 'completed' || task.status === 'failed') {
      return (
        <div className="space-y-0.5">
          <p className="text-sm text-foreground">
            {task.completed_at ? formatRelativeTime(task.completed_at) : '-'}
          </p>
          {task.duration_ms != null && task.duration_ms > 0 && (
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              <Timer className="w-3 h-3" />
              {formatDuration(task.duration_ms)}
            </p>
          )}
        </div>
      );
    }
    return (
      <span className="text-sm text-muted-foreground">
        {task.started_at ? formatRelativeTime(task.started_at) : '-'}
      </span>
    );
  };

  return (
    <Card>
      <div className="p-4 border-b border-border">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <h2 className="text-lg font-semibold text-foreground">
            {t('dashboard.taskMonitor')}
          </h2>
          <div className="flex items-center gap-3">
            <Input
              placeholder={t('dashboard.searchTasks')}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              leftIcon={<Search className="w-4 h-4" />}
              className="w-64"
            />
            <Select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}
              className="w-32"
            >
              {statusOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </div>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-surface-sunken dark:bg-surface">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                {t('dashboard.table.taskName')}
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                {t('dashboard.table.workflow')}
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                {t('dashboard.table.status')}
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                {t('dashboard.table.progress')}
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                {t('dashboard.table.time')}
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                {t('dashboard.table.actions')}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                  {t('common.loading')}
                </td>
              </tr>
            ) : tasksData?.items && tasksData.items.length > 0 ? (
              tasksData.items.map((task: Task) => (
                <tr key={task.id} className="hover:bg-surface-sunken dark:hover:bg-surface-elevated/50 transition-colors">
                  <td className="px-4 py-3">
                    <div className="min-w-0">
                      <p className="font-medium text-foreground truncate max-w-[240px]">{task.name}</p>
                      <p className="text-xs text-muted-foreground font-mono mt-0.5">
                        {task.id.slice(0, 8)}
                      </p>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    {renderTaskType(task)}
                  </td>
                  <td className="px-4 py-3">{getStatusBadge(task.status)}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-1.5 bg-border-subtle dark:bg-surface-elevated rounded-full overflow-hidden max-w-24">
                        <div
                          className={cn(
                            'h-full rounded-full transition-all duration-500 ease-out',
                            getProgressColor(task.status),
                          )}
                          style={{ width: `${task.progress}%` }}
                        />
                      </div>
                      <span className="text-xs text-muted-foreground tabular-nums w-10 text-right">
                        {task.progress}%
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    {renderTimeCell(task)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button variant="ghost" size="icon" title={t('tasks.details')}>
                        <Eye className="w-4 h-4" />
                      </Button>
                      {task.status === 'failed' && (
                        <Button variant="ghost" size="icon" title={t('tasks.retry')}>
                          <RotateCcw className="w-4 h-4" />
                        </Button>
                      )}
                      {task.status === 'running' && (
                        <Button
                          variant="ghost"
                          size="icon"
                          title={t('tasks.cancel')}
                          className="text-red-600 hover:text-red-700"
                        >
                          <XCircle className="w-4 h-4" />
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                  {t('common.noData')}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {tasksData && tasksData.total > 0 && (
        <div className="flex items-center justify-between px-4 py-3 border-t border-border">
          <p className="text-sm text-muted-foreground">
            {t('dashboard.pagination', {
              from: (page - 1) * 10 + 1,
              to: Math.min(page * 10, tasksData.total),
              total: tasksData.total,
            })}
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page === 1}
              onClick={() => setPage((p) => p - 1)}
            >
              {t('common.previous')}
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={!tasksData.has_next}
              onClick={() => setPage((p) => p + 1)}
            >
              {t('common.next')}
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}
