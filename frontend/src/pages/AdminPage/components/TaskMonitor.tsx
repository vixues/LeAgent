import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Card,
  Button,
  Select,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Badge,
} from '@/components/ui';
import { useAdminStore } from '@/stores/admin';
import {
  useTasks,
  useTask,
  useCancelTask,
  useKillTask,
  useRetryTask,
} from '@/hooks/useAdmin';
import type { Task, TaskStatus } from '@/types/admin';
import { formatDate, formatRelativeTime } from '@/lib/utils';

const STATUS_VARIANTS: Record<
  TaskStatus,
  'default' | 'primary' | 'success' | 'error' | 'warning'
> = {
  pending: 'default',
  queued: 'default',
  running: 'primary',
  completed: 'success',
  failed: 'error',
  cancelled: 'warning',
  killed: 'error',
  timeout: 'warning',
};

const STATUS_PROGRESS: Record<TaskStatus, string> = {
  pending: 'bg-gray-400',
  queued: 'bg-gray-400',
  running: 'bg-primary-500',
  completed: 'bg-green-500',
  failed: 'bg-red-500',
  cancelled: 'bg-yellow-500',
  killed: 'bg-red-600',
  timeout: 'bg-orange-500',
};

const ACTIVE_STATUSES: TaskStatus[] = ['pending', 'queued', 'running'];

function isTerminal(status: TaskStatus): boolean {
  return !ACTIVE_STATUSES.includes(status);
}

export function TaskMonitor() {
  const { t } = useTranslation();
  const STATUS_OPTIONS = useMemo(
    () =>
      (
        [
          'all',
          'pending',
          'queued',
          'running',
          'completed',
          'failed',
          'cancelled',
          'killed',
          'timeout',
        ] as const
      ).map((value) => ({
        value,
        label: t(`admin.task.filterStatus.${value}`, { defaultValue: value }),
      })),
    [t]
  );
  const {
    selectedTask,
    setSelectedTask,
    isTaskDetailModalOpen,
    setTaskDetailModalOpen,
    taskStatusFilter,
    setTaskStatusFilter,
  } = useAdminStore();

  const { data: tasksData, isLoading } = useTasks({
    page: 1,
    pageSize: 50,
    status: taskStatusFilter !== 'all' ? taskStatusFilter : undefined,
  });

  const { data: taskDetail } = useTask(selectedTask?.id || '');
  const cancelTask = useCancelTask();
  const killTask = useKillTask();
  const retryTask = useRetryTask();

  const handleOpenDetail = (task: Task) => {
    setSelectedTask(task);
    setTaskDetailModalOpen(true);
  };

  const handleCloseDetail = () => {
    setTaskDetailModalOpen(false);
    setSelectedTask(null);
  };

  const handleCancel = async (id: string) => {
    if (window.confirm(t('admin.task.confirmCancel'))) {
      await cancelTask.mutateAsync(id);
    }
  };

  const handleKill = async (id: string) => {
    if (
      window.confirm(
        t('admin.task.confirmKill', {
          defaultValue: 'Force kill this task? This cannot be undone.',
        }),
      )
    ) {
      await killTask.mutateAsync(id);
    }
  };

  const handleRetry = async (id: string) => {
    await retryTask.mutateAsync(id);
  };

  const getStatusBadge = (status: TaskStatus) => (
    <Badge variant={STATUS_VARIANTS[status]}>
      {t(`admin.task.filterStatus.${status}`, { defaultValue: status })}
    </Badge>
  );

  const getProgressColor = (status: TaskStatus) => STATUS_PROGRESS[status];

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-gray-500 dark:text-gray-400">{t('common.loading')}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            {t('admin.task.title')}
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {t('admin.task.description')}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            <span className="text-sm text-gray-500 dark:text-gray-400">
              {t('admin.task.realtime')}
            </span>
          </div>
          <Select
            value={taskStatusFilter}
            onChange={(e) => setTaskStatusFilter(e.target.value)}
            className="w-36"
          >
            {STATUS_OPTIONS.map((status) => (
              <option key={status.value} value={status.value}>
                {status.label}
              </option>
            ))}
          </Select>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {(['running', 'pending', 'completed', 'failed'] as TaskStatus[]).map((status) => {
          const count =
            tasksData?.items.filter((task: Task) => task.status === status).length || 0;
          return (
            <Card key={status} padding="sm">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    {t(`admin.task.filterStatus.${status}`, { defaultValue: status })}
                  </p>
                  <p className="text-2xl font-bold text-gray-900 dark:text-white mt-1">
                    {count}
                  </p>
                </div>
                <div
                  className={`w-12 h-12 rounded-lg flex items-center justify-center ${
                    status === 'pending'
                      ? 'bg-gray-100 dark:bg-surface'
                      : status === 'running'
                      ? 'bg-primary-100 dark:bg-primary-900/30'
                      : status === 'completed'
                      ? 'bg-green-100 dark:bg-green-900/30'
                      : 'bg-red-100 dark:bg-red-900/30'
                  }`}
                />
              </div>
            </Card>
          );
        })}
      </div>

      <Card padding="none">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 dark:bg-surface border-b border-gray-200 dark:border-gray-700">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  {t('admin.task.name')}
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  {t('admin.task.type', { defaultValue: 'Type' })}
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  {t('admin.task.status')}
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  {t('admin.task.progress')}
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  {t('admin.task.time')}
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                  {t('admin.task.actions')}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
              {tasksData?.items.map((task: Task) => (
                <tr key={task.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                  <td className="px-4 py-3">
                    <button
                      onClick={() => handleOpenDetail(task)}
                      className="text-left hover:text-primary-600 dark:hover:text-primary-400"
                    >
                      <p className="font-medium text-gray-900 dark:text-white">
                        {task.name}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-400">
                        ID: {task.id.slice(0, 8)}...
                      </p>
                    </button>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-300">
                    <Badge variant="default">{task.task_type}</Badge>
                  </td>
                  <td className="px-4 py-3">{getStatusBadge(task.status)}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                        <div
                          className={`h-full transition-[color,background-color,border-color,box-shadow,opacity,transform] duration-300 ${getProgressColor(task.status)}`}
                          style={{ width: `${task.progress}%` }}
                        />
                      </div>
                      <span className="text-xs text-gray-500 dark:text-gray-400 w-10">
                        {task.progress}%
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                    {task.started_at ? formatRelativeTime(task.started_at) : '-'}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleOpenDetail(task)}
                      >
                        {t('tasks.details')}
                      </Button>
                      {task.status === 'running' && (
                        <>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleCancel(task.id)}
                            loading={cancelTask.isPending}
                          >
                            {t('tasks.cancel')}
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-900/20"
                            onClick={() => handleKill(task.id)}
                            loading={killTask.isPending}
                          >
                            {t('tasks.kill', { defaultValue: 'Kill' })}
                          </Button>
                        </>
                      )}
                      {(task.status === 'failed' ||
                        task.status === 'killed' ||
                        task.status === 'timeout') && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleRetry(task.id)}
                          loading={retryTask.isPending}
                        >
                          {t('tasks.retry')}
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {(!tasksData?.items || tasksData.items.length === 0) && (
          <div className="py-12 text-center">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gray-100 dark:bg-surface flex items-center justify-center">
              <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
            </div>
            <p className="text-gray-500 dark:text-gray-400">{t('admin.task.empty')}</p>
          </div>
        )}
      </Card>

      <Modal isOpen={isTaskDetailModalOpen} onClose={handleCloseDetail} size="xl">
        <ModalHeader onClose={handleCloseDetail}>
          {t('admin.task.detail')}
        </ModalHeader>
        <ModalBody>
          {taskDetail && (
            <div className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {t('admin.task.name')}
                  </p>
                  <p className="font-medium text-gray-900 dark:text-white">
                    {taskDetail.name}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {t('admin.task.type', { defaultValue: 'Type' })}
                  </p>
                  <Badge variant="default">{taskDetail.task_type}</Badge>
                </div>
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {t('admin.task.status')}
                  </p>
                  <div className="mt-1">{getStatusBadge(taskDetail.status)}</div>
                </div>
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {t('admin.task.progress')}
                  </p>
                  <p className="font-medium text-gray-900 dark:text-white">
                    {taskDetail.progress}%
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {t('tasks.startTime')}
                  </p>
                  <p className="font-medium text-gray-900 dark:text-white">
                    {taskDetail.started_at ? formatDate(taskDetail.started_at) : '-'}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {t('tasks.endTime')}
                  </p>
                  <p className="font-medium text-gray-900 dark:text-white">
                    {taskDetail.completed_at ? formatDate(taskDetail.completed_at) : '-'}
                  </p>
                </div>
              </div>

              {taskDetail.error && (
                <div className="p-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800">
                  <p className="text-xs text-red-600 dark:text-red-400 font-medium mb-1">
                    {t('admin.task.error')}
                  </p>
                  <p className="text-sm text-red-700 dark:text-red-300 font-mono">
                    {taskDetail.error}
                  </p>
                </div>
              )}

              <p className="text-xs text-gray-500 dark:text-gray-400">
                {t('admin.task.openForLogs', {
                  defaultValue:
                    'Open the Tasks page to stream live output from this task.',
                })}
              </p>
            </div>
          )}
        </ModalBody>
        <ModalFooter>
          {taskDetail && !isTerminal(taskDetail.status) && (
            <>
              <Button
                variant="secondary"
                onClick={() => handleCancel(taskDetail.id)}
                loading={cancelTask.isPending}
              >
                {t('tasks.cancel')}
              </Button>
              <Button
                variant="danger"
                onClick={() => handleKill(taskDetail.id)}
                loading={killTask.isPending}
              >
                {t('tasks.kill', { defaultValue: 'Kill' })}
              </Button>
            </>
          )}
          {taskDetail &&
            (taskDetail.status === 'failed' ||
              taskDetail.status === 'killed' ||
              taskDetail.status === 'timeout') && (
              <Button
                variant="primary"
                onClick={() => handleRetry(taskDetail.id)}
                loading={retryTask.isPending}
              >
                {t('tasks.retry')}
              </Button>
            )}
          <Button variant="secondary" onClick={handleCloseDetail}>
            {t('common.close')}
          </Button>
        </ModalFooter>
      </Modal>
    </div>
  );
}
