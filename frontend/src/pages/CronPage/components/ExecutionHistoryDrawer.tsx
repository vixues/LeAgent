import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { cn } from '@/lib/utils';
import {
  X,
  CheckCircle,
  XCircle,
  Clock,
  Loader2,
  AlertTriangle,
  RefreshCw,
  ExternalLink,
} from 'lucide-react';
import { PageLoader } from '@/components/common/PageLoader';
import type { CronJobExecution } from '@/controllers/API/queries/cron';
import { useCronJobHistory } from '@/controllers/API/queries/cron';

interface ExecutionHistoryDrawerProps {
  open: boolean;
  onClose: () => void;
  jobId: string;
  jobName: string;
}

const STATUS_ICONS: Record<string, React.ReactNode> = {
  completed: <CheckCircle className="w-4 h-4 text-green-500" />,
  failed: <XCircle className="w-4 h-4 text-red-500" />,
  running: <Loader2 className="w-4 h-4 text-sky-500 animate-spin" />,
  pending: <Clock className="w-4 h-4 text-gray-400" />,
  timeout: <AlertTriangle className="w-4 h-4 text-yellow-500" />,
  cancelled: <X className="w-4 h-4 text-gray-400" />,
  skipped: <Clock className="w-4 h-4 text-gray-400" />,
};

const STATUS_COLORS: Record<string, string> = {
  completed: 'text-green-700 bg-green-100 dark:text-green-300 dark:bg-green-900/30',
  failed: 'text-red-700 bg-red-100 dark:text-red-300 dark:bg-red-900/30',
  running: 'text-blue-700 bg-blue-100 dark:text-blue-300 dark:bg-blue-900/30',
  pending: 'text-gray-700 bg-gray-100 dark:text-gray-300 dark:bg-surface',
  timeout: 'text-yellow-700 bg-yellow-100 dark:text-yellow-300 dark:bg-yellow-900/30',
  cancelled: 'text-gray-600 bg-gray-100 dark:text-gray-400 dark:bg-surface',
  skipped: 'text-gray-600 bg-gray-100 dark:text-gray-400 dark:bg-surface',
};

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`;
}

function formatDateTime(iso?: string): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export function ExecutionHistoryDrawer({
  open,
  onClose,
  jobId,
  jobName,
}: ExecutionHistoryDrawerProps) {
  const { t } = useTranslation();
  const { data, isLoading, refetch } = useCronJobHistory(jobId, 50, {
    enabled: open && !!jobId,
  });

  if (!open) return null;

  const executions = data?.executions || [];

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative ml-auto w-full max-w-xl h-full flex flex-col bg-surface shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-700">
          <div>
            <h3 className="text-base font-semibold text-gray-900 dark:text-white">{t('cron.historyDrawer.title')}</h3>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 truncate max-w-xs">{jobName}</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => refetch()}
              className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="flex items-center justify-center py-16">
              <PageLoader size="sm" message={t('common.loading')} />
            </div>
          ) : executions.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center px-8">
              <Clock className="w-10 h-10 text-gray-300 dark:text-gray-600 mb-3" />
              <p className="text-sm font-medium text-gray-600 dark:text-gray-400">{t('cron.historyDrawer.emptyTitle')}</p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">{t('cron.historyDrawer.emptyHint')}</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-100 dark:divide-gray-800">
              {executions.map((exec) => (
                <ExecutionRow key={exec.id} execution={exec} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ExecutionRow({ execution }: { execution: CronJobExecution }) {
  const { t } = useTranslation();
  const statusColor = STATUS_COLORS[execution.status] || STATUS_COLORS.pending;
  const icon = STATUS_ICONS[execution.status] || STATUS_ICONS.pending;

  // CronExecutor._execute_task records {"task_id": "..."} inside the
  // execution outputs. Surfacing it as a link lets operators jump from
  // the cron history into the TaskManager streaming view without
  // having to dig through JSON.
  const rawTaskId = (execution.outputs as Record<string, unknown> | undefined)?.task_id;
  const taskId = typeof rawTaskId === 'string' && rawTaskId ? rawTaskId : null;

  return (
    <div className="px-5 py-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="mt-0.5">{icon}</div>
          <div>
            <div className="flex items-center gap-2">
              <span className={cn('text-xs font-medium px-2 py-0.5 rounded-full', statusColor)}>
                {execution.status}
              </span>
              <span className="text-xs text-gray-400 dark:text-gray-500">#{execution.execution_number}</span>
              <span className="text-xs text-gray-400 dark:text-gray-500 capitalize">{execution.trigger_type}</span>
            </div>
            <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              {formatDateTime(execution.started_at)}
              {execution.duration_ms > 0 && (
                <span className="ml-2 font-medium">{formatDuration(execution.duration_ms)}</span>
              )}
            </div>
            {taskId && (
              <Link
                to={`/tasks/${taskId}`}
                className="mt-1.5 inline-flex items-center gap-1 text-xs text-primary-600 hover:text-primary-700 dark:text-primary-400"
              >
                <ExternalLink className="w-3 h-3" />
                {t('cron.historyDrawer.viewTask', {
                  defaultValue: 'View task',
                })}
              </Link>
            )}
            {execution.error && (
              <div className="mt-1.5 text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 rounded px-2 py-1 font-mono max-w-xs truncate">
                {execution.error}
              </div>
            )}
          </div>
        </div>
        {execution.retry_count > 0 && (
          <span className="text-xs text-gray-400 dark:text-gray-500 flex-shrink-0">
            {t('cron.historyDrawer.retryLabel', { count: execution.retry_count })}
          </span>
        )}
      </div>
    </div>
  );
}
