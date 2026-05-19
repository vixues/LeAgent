import { useState } from 'react';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui';
import {
  Clock,
  Plus,
  RefreshCw,
  Search,
  Filter,
  Play,
  Pause,
  Trash2,
  Edit2,
  Copy,
  History,
  CheckCircle,
  XCircle,
  AlertTriangle,
  MoreHorizontal,
  Activity,
  Zap,
  TrendingUp,
} from 'lucide-react';
import { PageShell } from '@/components/layout/PageShell';
import { Button, Input, Select } from '@/components/ui';
import { StatsCard } from '@/components/common/StatsCard';
import { StatusBadge } from '@/components/common/StatusBadge';
import { DataTable, type Column } from '@/components/common/DataTable';
import { EmptyState } from '@/components/common/EmptyState';
import {
  useCronJobs,
  useCronSystemStats,
  useCronJobNextRuns,
  useCronJob,
  useCronHealth,
  useCreateCronJob,
  useUpdateCronJob,
  useDeleteCronJob,
  usePauseCronJob,
  useResumeCronJob,
  useTriggerCronJob,
  useCloneCronJob,
  type CronJobInfo,
  type CreateCronJobInput,
} from '@/controllers/API/queries/cron';
import { CronJobModal } from './components/CronJobModal';
import { ExecutionHistoryDrawer } from './components/ExecutionHistoryDrawer';
import { useToast } from '@/components/ui/Toaster';
import {
  buildCronJobUpdatePayload,
  mapCronJobStatusToBadge,
} from '@/pages/CronPage/cronJobPayload';

function formatNextRun(iso: string | undefined, t: TFunction): string {
  if (!iso) return '—';
  const date = new Date(iso);
  const now = new Date();
  const diff = date.getTime() - now.getTime();
  if (diff < 0) return t('cron.time.overdue');
  if (diff < 60000) return t('cron.time.inSeconds', { count: Math.round(diff / 1000) });
  if (diff < 3600000) return t('cron.time.inMinutes', { count: Math.round(diff / 60000) });
  if (diff < 86400000) return t('cron.time.inHours', { count: Math.round(diff / 3600000) });
  return date.toLocaleDateString();
}

function formatLastRun(iso: string | undefined, t: TFunction): string {
  if (!iso) return t('cron.time.never');
  const date = new Date(iso);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  if (diff < 60000) return t('cron.time.justNow');
  if (diff < 3600000) return t('cron.time.minutesAgo', { count: Math.round(diff / 60000) });
  if (diff < 86400000) return t('cron.time.hoursAgo', { count: Math.round(diff / 3600000) });
  return date.toLocaleDateString();
}

function NextRunScheduleCell({ row }: { row: CronJobInfo }) {
  const { t } = useTranslation();
  const [tipOpen, setTipOpen] = useState(false);
  const { data, isLoading, isError } = useCronJobNextRuns(row.id, 8, { enabled: tipOpen });

  return (
    <Tooltip open={tipOpen} onOpenChange={setTipOpen} delayDuration={0}>
      <TooltipTrigger className="cursor-help text-left w-full">
        <div className="text-sm">
          <div className="text-gray-700 dark:text-gray-300">{formatNextRun(row.next_run_at, t)}</div>
        </div>
      </TooltipTrigger>
      <TooltipContent side="left" className="max-w-xs px-3 py-2 whitespace-normal font-normal">
        <p className="text-[10px] uppercase tracking-wide text-gray-400 mb-1">{t('cron.nextRunsTitle')}</p>
        {isLoading && <p className="text-xs text-gray-500">{t('cron.nextRunsLoading')}</p>}
        {!isLoading && isError && <p className="text-xs text-red-400">{t('cron.nextRunsError')}</p>}
        {!isLoading && !isError && data?.next_runs?.length ? (
          <ul className="text-xs space-y-1 text-left max-h-40 overflow-y-auto">
            {data.next_runs.map((iso: string) => (
              <li key={iso}>{new Date(iso).toLocaleString()}</li>
            ))}
          </ul>
        ) : null}
        {!isLoading && !isError && !data?.next_runs?.length ? (
          <p className="text-xs text-gray-500">{t('cron.nextRunsEmpty')}</p>
        ) : null}
      </TooltipContent>
    </Tooltip>
  );
}

export default function CronPage() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [typeFilter, setTypeFilter] = useState<string>('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editingJobId, setEditingJobId] = useState<string | null>(null);
  const [historyJob, setHistoryJob] = useState<{ id: string; name: string } | null>(null);
  const [menuOpen, setMenuOpen] = useState<string | null>(null);

  const { data: jobsData, isLoading, isError: jobsError, refetch } = useCronJobs({
    status: statusFilter || undefined,
    job_type: typeFilter || undefined,
    search: search || undefined,
  });

  const { data: stats, isError: statsError } = useCronSystemStats();
  const { isError: healthError } = useCronHealth();

  const {
    data: editingDetail,
    isLoading: editingDetailLoading,
    isError: editingDetailError,
  } = useCronJob(editingJobId ?? '', {
    enabled: modalOpen && !!editingJobId,
  });

  const cronServiceDegraded = jobsError || statsError || healthError;

  const createMutation = useCreateCronJob();
  const updateMutation = useUpdateCronJob();
  const deleteMutation = useDeleteCronJob();
  const pauseMutation = usePauseCronJob();
  const resumeMutation = useResumeCronJob();
  const triggerMutation = useTriggerCronJob();
  const cloneMutation = useCloneCronJob();

  const jobs = jobsData?.jobs || [];

  const handleCreate = async (data: CreateCronJobInput) => {
    try {
      await createMutation.mutateAsync(data);
      setModalOpen(false);
      toast({ title: t('cron.toastCreated'), description: t('cron.toastCreatedDesc', { name: data.name }) });
    } catch (e: unknown) {
      toast({ title: t('cron.toastError'), description: String(e), variant: 'error' });
    }
  };

  const handleUpdate = async (data: CreateCronJobInput) => {
    if (!editingJobId) return;
    try {
      await updateMutation.mutateAsync(buildCronJobUpdatePayload(editingJobId, data));
      setEditingJobId(null);
      setModalOpen(false);
      toast({ title: t('cron.toastUpdated'), description: t('cron.toastUpdatedDesc', { name: data.name }) });
    } catch (e: unknown) {
      toast({ title: t('cron.toastError'), description: String(e), variant: 'error' });
    }
  };

  const handleDelete = async (job: CronJobInfo) => {
    if (!confirm(t('cron.confirmDelete', { name: job.name }))) return;
    try {
      await deleteMutation.mutateAsync(job.id);
      toast({ title: t('cron.toastDeleted') });
    } catch (e: unknown) {
      toast({ title: t('cron.toastError'), description: String(e), variant: 'error' });
    }
  };

  const handlePause = async (job: CronJobInfo) => {
    await pauseMutation.mutateAsync(job.id);
    toast({ title: t('cron.toastPaused'), description: t('cron.toastPausedDesc', { name: job.name }) });
  };

  const handleResume = async (job: CronJobInfo) => {
    await resumeMutation.mutateAsync(job.id);
    toast({ title: t('cron.toastResumed'), description: t('cron.toastResumedDesc', { name: job.name }) });
  };

  const handleTrigger = async (job: CronJobInfo) => {
    try {
      await triggerMutation.mutateAsync(job.id);
      toast({ title: t('cron.toastTriggered'), description: t('cron.toastTriggeredDesc', { name: job.name }) });
    } catch (e: unknown) {
      toast({ title: t('cron.toastError'), description: String(e), variant: 'error' });
    }
  };

  const handleClone = async (job: CronJobInfo) => {
    try {
      await cloneMutation.mutateAsync({ jobId: job.id });
      toast({ title: t('cron.toastCloned'), description: t('cron.toastClonedDesc', { name: job.name }) });
    } catch (e: unknown) {
      toast({ title: t('cron.toastError'), description: String(e), variant: 'error' });
    }
  };

  const columns: Column<CronJobInfo>[] = [
    {
      id: 'name',
      header: t('cron.colJob'),
      cell: ({ row }) => (
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{row.name}</p>
            <span className="flex-shrink-0 text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400">
              {row.job_type === 'flow' ||
              row.job_type === 'task' ||
              row.job_type === 'webhook' ||
              row.job_type === 'script'
                ? t(`cron.jobType.${row.job_type}`)
                : row.job_type}
            </span>
          </div>
          {row.description && (
            <p className="text-xs text-gray-500 dark:text-gray-400 truncate mt-0.5">{row.description}</p>
          )}
          <p className="text-xs font-mono text-gray-400 dark:text-gray-500 mt-0.5">{row.cron_expression}</p>
        </div>
      ),
      minWidth: 200,
    },
    {
      id: 'status',
      header: t('cron.colStatus'),
      cell: ({ row }) => (
        <StatusBadge
          status={mapCronJobStatusToBadge(row.status)}
          pulse={row.status === 'running'}
          size="sm"
        />
      ),
      width: 110,
      align: 'center',
    },
    {
      id: 'schedule',
      header: t('cron.colNextRun'),
      cell: ({ row }) => <NextRunScheduleCell row={row} />,
      width: 120,
    },
    {
      id: 'last_run',
      header: t('cron.colLastRun'),
      cell: ({ row }) => (
        <div className="text-sm text-gray-600 dark:text-gray-400">
          {formatLastRun(row.last_run_at, t)}
        </div>
      ),
      width: 100,
    },
    {
      id: 'stats',
      header: t('cron.colStats'),
      cell: ({ row }) => (
        <div className="flex items-center gap-3 text-xs">
          <span className="flex items-center gap-1 text-mint-600 dark:text-mint-400">
            <CheckCircle className="w-3 h-3" />
            {row.success_count}
          </span>
          <span className="flex items-center gap-1 text-red-600 dark:text-red-400">
            <XCircle className="w-3 h-3" />
            {row.error_count}
          </span>
          {row.success_rate > 0 && (
            <span className="text-gray-500 dark:text-gray-400">{row.success_rate}%</span>
          )}
        </div>
      ),
      width: 120,
    },
    {
      id: 'actions',
      header: '',
      cell: ({ row }) => (
        <div className="flex items-center justify-end gap-1">
          <button
            onClick={(e) => { e.stopPropagation(); handleTrigger(row); }}
            title={t('cron.titleRunNow')}
            className="p-1.5 rounded-lg text-gray-400 hover:text-mint-600 hover:bg-mint-50 dark:hover:bg-mint-900/20 transition-colors"
          >
            <Play className="w-4 h-4" />
          </button>
          {row.status === 'active' ? (
            <button
              onClick={(e) => { e.stopPropagation(); handlePause(row); }}
              title={t('cron.titlePause')}
              className="p-1.5 rounded-lg text-gray-400 hover:text-peach-600 hover:bg-peach-50 dark:hover:bg-peach-900/20 transition-colors"
            >
              <Pause className="w-4 h-4" />
            </button>
          ) : (
            <button
              onClick={(e) => { e.stopPropagation(); handleResume(row); }}
              title={t('cron.titleResume')}
              className="p-1.5 rounded-lg text-gray-400 hover:text-sky-600 hover:bg-sky-50 dark:hover:bg-sky-900/20 transition-colors"
            >
              <Play className="w-4 h-4" />
            </button>
          )}
          <button
            onClick={(e) => { e.stopPropagation(); setHistoryJob({ id: row.id, name: row.name }); }}
            title={t('cron.titleHistory')}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            <History className="w-4 h-4" />
          </button>
          <div className="relative">
            <button
              onClick={(e) => { e.stopPropagation(); setMenuOpen(menuOpen === row.id ? null : row.id); }}
              className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            >
              <MoreHorizontal className="w-4 h-4" />
            </button>
            {menuOpen === row.id && (
              <div
                className="absolute right-0 top-full mt-1 z-50 w-40 bg-surface rounded-xl border border-gray-200 dark:border-gray-700 shadow-lg py-1"
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  onClick={() => { setEditingJobId(row.id); setModalOpen(true); setMenuOpen(null); }}
                  className="flex items-center gap-2 w-full px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
                >
                  <Edit2 className="w-3.5 h-3.5" /> {t('cron.menuEdit')}
                </button>
                <button
                  onClick={() => { handleClone(row); setMenuOpen(null); }}
                  className="flex items-center gap-2 w-full px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
                >
                  <Copy className="w-3.5 h-3.5" /> {t('cron.menuClone')}
                </button>
                <button
                  onClick={() => { handleDelete(row); setMenuOpen(null); }}
                  className="flex items-center gap-2 w-full px-3 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20"
                >
                  <Trash2 className="w-3.5 h-3.5" /> {t('cron.menuDelete')}
                </button>
              </div>
            )}
          </div>
        </div>
      ),
      width: 140,
      align: 'right',
    },
  ];

  return (
    <PageShell
      title={t('cron.pageTitle')}
      description={t('cron.pageDescription')}
      icon={<Clock className="w-5 h-5" />}
      actions={
        <>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => refetch()}
            leftIcon={<RefreshCw className="w-4 h-4" />}
          >
            {t('cron.refresh')}
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => { setEditingJobId(null); setModalOpen(true); }}
            leftIcon={<Plus className="w-4 h-4" />}
          >
            {t('cron.newJob')}
          </Button>
        </>
      }
    >
      {/*
        onClick at the body level closes any open row menu when the user
        clicks an empty area of the page (the row's own ⋯ button stops
        propagation so it still toggles correctly).
      */}
      <div className="flex flex-col gap-6" onClick={() => setMenuOpen(null)}>
      {cronServiceDegraded && (
        <div
          className="rounded-xl border border-amber-200 dark:border-amber-900/50 bg-amber-50 dark:bg-amber-950/30 px-4 py-3 text-sm text-amber-900 dark:text-amber-100"
          role="alert"
        >
          {t('cron.serviceUnavailable')}
        </div>
      )}
      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-6">
          <StatsCard
            title={t('cron.statsActive')}
            value={stats.active_jobs}
            icon={<Activity className="w-full h-full" />}
            color="green"
            description={stats.scheduler_running ? t('cron.schedulerRunning') : t('cron.schedulerStopped')}
          />
          <StatsCard
            title={t('cron.statsPaused')}
            value={stats.paused_jobs}
            icon={<Pause className="w-full h-full" />}
            color="yellow"
          />
          <StatsCard
            title={t('cron.statsFailed')}
            value={stats.failed_jobs}
            icon={<AlertTriangle className="w-full h-full" />}
            color="red"
          />
          <StatsCard
            title={t('cron.statsTotalRuns')}
            value={stats.total_runs_all_jobs}
            icon={<TrendingUp className="w-full h-full" />}
            color="blue"
            description={t('cron.statsAllTime')}
          />
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex-1 min-w-[200px] max-w-sm">
          <Input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('cron.searchPlaceholder')}
            leftIcon={<Search className="w-4 h-4" />}
          />
        </div>
        <Select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="w-36"
        >
          <option value="">{t('cron.allStatuses')}</option>
          <option value="active">{t('cron.statusActive')}</option>
          <option value="paused">{t('cron.statusPaused')}</option>
          <option value="failed">{t('cron.statusFailed')}</option>
        </Select>
        <Select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="w-32"
        >
          <option value="">{t('cron.allTypes')}</option>
          <option value="flow">{t('cron.typeFlow')}</option>
          <option value="task">{t('cron.typeTask', { defaultValue: 'Task' })}</option>
          <option value="webhook">{t('cron.typeWebhook')}</option>
          <option value="script">{t('cron.typeScript')}</option>
        </Select>
        {(search || statusFilter || typeFilter) && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => { setSearch(''); setStatusFilter(''); setTypeFilter(''); }}
            leftIcon={<Filter className="w-4 h-4" />}
          >
            {t('cron.clearFilters')}
          </Button>
        )}
      </div>

      {/* Table */}
      {jobs.length === 0 && !isLoading ? (
        <div className="flex-1 flex items-center justify-center">
          <EmptyState
            icon={<Zap className="w-12 h-12" />}
            title={search || statusFilter || typeFilter ? t('cron.emptyNoMatch') : t('cron.emptyNone')}
            description={
              search || statusFilter || typeFilter
                ? t('cron.emptyNoMatchHint')
                : t('cron.emptyNoneHint')
            }
            action={
              !search && !statusFilter && !typeFilter
                ? { label: t('cron.createJob'), onClick: () => { setEditingJobId(null); setModalOpen(true); } }
                : undefined
            }
          />
        </div>
      ) : (
        <DataTable
          data={jobs}
          columns={columns}
          loading={isLoading}
          rowKey={(row) => row.id}
          hoverable
          stickyHeader
        />
      )}

      {/* Create / Edit Modal */}
      <CronJobModal
        open={modalOpen}
        onClose={() => { setModalOpen(false); setEditingJobId(null); }}
        onSave={editingJobId ? handleUpdate : handleCreate}
        mode={editingJobId ? 'edit' : 'create'}
        job={editingJobId ? editingDetail : undefined}
        detailLoading={!!editingJobId && editingDetailLoading && !editingDetail}
        detailError={!!editingJobId && editingDetailError}
        isLoading={createMutation.isPending || updateMutation.isPending}
      />

      {/* Execution History Drawer */}
      {historyJob && (
        <ExecutionHistoryDrawer
          open={true}
          onClose={() => setHistoryJob(null)}
          jobId={historyJob.id}
          jobName={historyJob.name}
        />
      )}
      </div>
    </PageShell>
  );
}
