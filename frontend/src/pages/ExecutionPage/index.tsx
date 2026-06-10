import { useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  RefreshCw,
  StopCircle,
  Pause,
  Play,
  Clock,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Loader2,
  GitBranch,
  Activity,
  ChevronRight,
} from 'lucide-react';

import { PageShell } from '@/components/layout/PageShell';
import { StatusBadge } from '@/components/common/StatusBadge';
import { TimelineView, type TimelineItem } from '@/components/common/TimelineView';
import { JsonViewer } from '@/components/common/JsonViewer';
import { Skeleton } from '@/components/ui/Skeleton';
import { Button } from '@/components/ui';
import {
  useExecution,
  useCancelExecution,
  usePauseExecution,
  useResumeExecution,
  type NodeExecutionResult,
} from '@/controllers/API/queries/executions';
import { useToast } from '@/components/ui/Toaster';
import { GenUiTreeView } from '@/components/canvas/GenUiRegistry';
import { outputsToGenUiTree } from '@/features/workflow/genui/outputsToGenUiTree';

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const m = Math.floor(ms / 60000);
  const s = Math.floor((ms % 60000) / 1000);
  return `${m}m ${s}s`;
}

function mapNodeStatus(status: string): TimelineItem['status'] {
  if (status === 'success' || status === 'completed') return 'success';
  if (status === 'error' || status === 'failed') return 'error';
  if (status === 'running') return 'running';
  if (status === 'skipped') return 'skipped';
  if (status === 'warning') return 'warning';
  return 'pending';
}

function mapExecStatus(status: string): 'active' | 'paused' | 'running' | 'success' | 'error' | 'pending' | 'cancelled' {
  const map: Record<string, 'active' | 'paused' | 'running' | 'success' | 'error' | 'pending' | 'cancelled'> = {
    running: 'running',
    pending: 'pending',
    paused: 'paused',
    waiting_human: 'paused',
    completed: 'success',
    failed: 'error',
    cancelled: 'cancelled',
    timeout: 'error',
  };
  return map[status] || 'pending';
}

export default function ExecutionPage() {
  const { t } = useTranslation();
  const { executionId } = useParams<{ executionId: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [selectedNode, setSelectedNode] = useState<NodeExecutionResult | null>(null);

  const { data: execution, isLoading, refetch } = useExecution(executionId || '', {
    enabled: !!executionId,
  });

  const cancelMutation = useCancelExecution();
  const pauseMutation = usePauseExecution();
  const resumeMutation = useResumeExecution();

  // Structured GenUI rendering of resolved workflow outputs.
  const outputsTree = useMemo(() => {
    if (execution?.status !== 'completed') return null;
    return outputsToGenUiTree(
      (execution.outputs as Record<string, unknown>) ?? null,
      null,
    );
  }, [execution?.status, execution?.outputs]);

  const handleCancel = async () => {
    if (!executionId || !confirm(t('execution.confirmCancel'))) return;
    try {
      await cancelMutation.mutateAsync(executionId);
      toast({ title: t('execution.toastCancelled') });
    } catch {
      toast({ title: t('execution.toastCancelError'), variant: 'error' });
    }
  };

  const handlePause = async () => {
    if (!executionId) return;
    try {
      await pauseMutation.mutateAsync(executionId);
      toast({ title: t('execution.toastPaused') });
    } catch {
      toast({ title: t('execution.toastPauseError'), variant: 'error' });
    }
  };

  const handleResume = async () => {
    if (!executionId || !execution?.flow_id) return;
    try {
      await resumeMutation.mutateAsync({
        executionId,
        flowId: execution.flow_id,
      });
      toast({ title: t('execution.toastResumed') });
    } catch {
      toast({ title: t('execution.toastResumeError'), variant: 'error' });
    }
  };

  const timelineItems: TimelineItem[] = (execution?.execution_history || []).map((node, i) => ({
    id: node.node_id || String(i),
    title: node.node_id || t('execution.fallbackNode', { index: i + 1 }),
    description: node.error || undefined,
    status: mapNodeStatus(node.status),
    duration: node.duration_ms ? formatDuration(node.duration_ms) : undefined,
    details: node.output ? (
      <div className="text-xs font-mono text-gray-600 dark:text-gray-400 truncate">
        {typeof node.output === 'string' ? node.output : JSON.stringify(node.output).slice(0, 80)}
      </div>
    ) : undefined,
  }));

  const execStatus = execution ? mapExecStatus(execution.status) : 'pending';

  if (isLoading) {
    return (
      <div className="flex flex-col flex-1 gap-4">
        <Skeleton className="h-12 w-64" />
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-24" />)}
        </div>
        <Skeleton className="h-96" />
      </div>
    );
  }

  if (!execution) {
    return (
      <div className="flex items-center justify-center flex-1">
        <div className="text-center">
          <XCircle className="w-12 h-12 text-gray-300 mx-auto mb-3" />
          <p className="text-gray-600 dark:text-gray-400">{t('execution.notFound')}</p>
          <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="mt-4">
            {t('execution.goBack')}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <PageShell
      title={t('execution.pageTitle', { id: executionId?.slice(-8)?.toUpperCase() ?? '' })}
      description={t('execution.pageDesc', {
        flowId: execution.flow_id || '—',
        trigger: execution.trigger_type,
      })}
      icon={<Activity className="w-5 h-5" />}
      breadcrumbs={[
        { label: t('execution.breadcrumbWorkflows'), onClick: () => navigate('/workflows') },
        { label: t('execution.breadcrumbExecution') },
      ]}
      badge={
        <StatusBadge
          status={execStatus}
          pulse={execution.status === 'running'}
          size="sm"
        />
      }
      actions={
        <>
            <Button variant="ghost" size="icon" onClick={() => refetch()}>
              <RefreshCw className="w-4 h-4" />
            </Button>
            {execution.status === 'running' && (
              <>
                <button
                  onClick={handlePause}
                  disabled={pauseMutation.isPending}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-yellow-700 dark:text-yellow-300 bg-yellow-100 dark:bg-yellow-900/30 hover:bg-yellow-200 rounded-lg transition-colors"
                >
                  <Pause className="w-3.5 h-3.5" /> {t('execution.pause')}
                </button>
                <button
                  onClick={handleCancel}
                  disabled={cancelMutation.isPending}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-red-700 dark:text-red-300 bg-red-100 dark:bg-red-900/30 hover:bg-red-200 rounded-lg transition-colors"
                >
                  <StopCircle className="w-3.5 h-3.5" /> {t('execution.cancel')}
                </button>
              </>
            )}
            {execution.status === 'paused' && (
              <button
                onClick={handleResume}
                disabled={resumeMutation.isPending}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-green-700 dark:text-green-300 bg-green-100 dark:bg-green-900/30 hover:bg-green-200 rounded-lg transition-colors"
              >
                <Play className="w-3.5 h-3.5" /> {t('execution.resume')}
              </button>
            )}
            {execution.flow_id && (
              <Button
                variant="secondary"
                size="sm"
                leftIcon={<GitBranch className="w-3.5 h-3.5" />}
                onClick={() => navigate(`/workflows/${execution.flow_id}`)}
              >
                {t('execution.viewWorkflow')}
              </Button>
            )}
        </>
      }
    >
      {/* Summary metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-6">
        {[
          {
            label: t('execution.metricStatus'),
            value: execution.status,
            icon: execution.status === 'completed' ? <CheckCircle className="w-5 h-5 text-green-500" /> :
                  execution.status === 'failed' ? <XCircle className="w-5 h-5 text-red-500" /> :
                  execution.status === 'running' ? <Loader2 className="w-5 h-5 text-sky-500 animate-spin" /> :
                  <Clock className="w-5 h-5 text-gray-400" />,
          },
          {
            label: t('execution.metricDuration'),
            value: execution.duration_ms ? formatDuration(execution.duration_ms) : (execution.status === 'running' ? t('execution.runningEllipsis') : t('execution.dash')),
            icon: <Clock className="w-5 h-5 text-gray-400" />,
          },
          {
            label: t('execution.metricNodes'),
            value: String(execution.node_count || execution.execution_history?.length || 0),
            icon: <Activity className="w-5 h-5 text-gray-400" />,
          },
          {
            label: t('execution.metricStarted'),
            value: execution.started_at ? new Date(execution.started_at).toLocaleTimeString() : t('execution.dash'),
            icon: <Clock className="w-5 h-5 text-gray-400" />,
          },
        ].map((metric) => (
          <div key={metric.label} className="rounded-xl p-4 bg-surface border border-gray-200 dark:border-gray-700">
            <div className="flex items-center gap-2 mb-1">
              {metric.icon}
              <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">{metric.label}</span>
            </div>
            <p className="text-lg font-semibold text-gray-900 dark:text-white">{metric.value}</p>
          </div>
        ))}
      </div>

      {/* Error banner */}
      {execution.error && (
        <div className="flex items-start gap-3 p-4 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800">
          <AlertTriangle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-red-700 dark:text-red-300">{t('execution.executionError')}</p>
            <p className="text-xs text-red-600 dark:text-red-400 font-mono mt-1">{execution.error}</p>
          </div>
        </div>
      )}

      {/* Main split layout */}
      <div className="flex gap-5 flex-1 min-h-0">
        {/* Left: Timeline */}
        <div className="flex-1 min-w-0 bg-surface rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-200 dark:border-gray-700">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{t('execution.nodeTimeline')}</h3>
          </div>
          <div className="p-5 overflow-y-auto max-h-96">
            {timelineItems.length === 0 ? (
              <div className="text-center py-8 text-gray-400 dark:text-gray-500 text-sm">
                {execution.status === 'pending' ? t('execution.pendingMessage') : t('execution.noNodeData')}
              </div>
            ) : (
              <TimelineView
                items={timelineItems.map((item, i) => ({
                  ...item,
                  meta: (
                    <button
                      onClick={() => setSelectedNode(execution.execution_history[i] ?? null)}
                      className="text-xs text-primary-600 dark:text-primary-400 hover:underline flex items-center gap-1 mt-1"
                    >
                      {t('execution.viewDetails')} <ChevronRight className="w-3 h-3" />
                    </button>
                  ),
                }))}
                compact
              />
            )}
          </div>
        </div>

        {/* Right: Detail panel */}
        <div className="w-80 flex-shrink-0 space-y-4">
          {/* Node detail */}
          {selectedNode ? (
            <div className="bg-surface rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
                <h4 className="text-sm font-semibold text-gray-900 dark:text-white">
                  {selectedNode.node_id || t('execution.nodeFallback')}
                </h4>
                <StatusBadge status={mapNodeStatus(selectedNode.status)} size="sm" />
              </div>
              <div className="p-4 space-y-3">
                {selectedNode.duration_ms !== undefined && (
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-gray-500 dark:text-gray-400">{t('execution.nodeDuration')}</span>
                    <span className="font-medium">{formatDuration(selectedNode.duration_ms)}</span>
                  </div>
                )}
                {selectedNode.error && (
                  <div className="text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 p-2 rounded font-mono">
                    {selectedNode.error}
                  </div>
                )}
                {selectedNode.output !== undefined && (
                  <JsonViewer
                    data={selectedNode.output}
                    label={t('execution.output')}
                    maxHeight="200px"
                    defaultExpanded={false}
                  />
                )}
              </div>
            </div>
          ) : (
            <div className="bg-gray-50 dark:bg-surface/50 rounded-xl border border-gray-200 dark:border-gray-700 p-4 text-center text-xs text-gray-500 dark:text-gray-400">
              {t('execution.clickNodeHint')}
            </div>
          )}

          {/* Inputs */}
          <JsonViewer
            data={execution.inputs || {}}
            label={t('execution.inputs')}
            maxHeight="150px"
            defaultExpanded={false}
          />

          {/* Outputs — structured GenUI rendering with raw JSON fallback */}
          {outputsTree && (
            <div className="overflow-hidden rounded-lg border border-border">
              <div className="border-b border-border bg-surface px-3 py-1.5 text-xs font-medium text-muted-foreground">
                {t('execution.outputs')}
              </div>
              <GenUiTreeView tree={outputsTree} />
            </div>
          )}
          <JsonViewer
            data={execution.outputs || {}}
            label={t('execution.outputs')}
            maxHeight="240px"
            defaultExpanded={
              outputsTree == null &&
              execution.status === 'completed' &&
              execution.outputs != null &&
              typeof execution.outputs === 'object' &&
              Object.keys(execution.outputs as Record<string, unknown>).length > 0
            }
          />
        </div>
      </div>
    </PageShell>
  );
}
