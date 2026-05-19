import { useEffect, useCallback, useState, useRef } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ReactFlowProvider } from '@xyflow/react';
import { useQuery } from '@tanstack/react-query';
import {
  X,
  AlertTriangle,
  Info,
  Tag,
  Trash2,
  Copy,
  Activity,
  Clock,
} from 'lucide-react';

import { apiClient } from '@/api/client';
import { Input, Textarea, Button } from '@/components/ui';
import { PageLoader } from '@/components/common/PageLoader';
import { EmptyState } from '@/components/common/EmptyState';
import { FlowCanvas } from './components/FlowCanvas';
import { FlowSidebar } from './components/FlowSidebar';
import { FlowToolbar } from './components/FlowToolbar';
import { NodeConfigPanel } from './components/NodeConfigPanel';
import { useFlowStore, FlowNode } from '../../stores/flow';
import { cn } from '../../lib/utils';
import { useFlowExecutions } from '@/controllers/API/queries/executions';
import { CronJobModal } from '@/pages/CronPage/components/CronJobModal';
import { useCreateCronJob } from '@/controllers/API/queries/cron';
import { fetchFlow } from './fetchFlow';
import { useSaveFlow } from '@/hooks/flows/useSaveFlow';

interface FlowRunResponse {
  execution_id: string;
  flow_id: string;
  status: string;
  message: string;
}

async function runFlow(flowId: string, _nodes: FlowNode[]): Promise<{ executionId: string }> {
  const res = await apiClient.post<FlowRunResponse>(`/workflow/flows/${flowId}/run`, {
    input_data: {},
  });
  return { executionId: res.execution_id };
}

export function FlowPage() {
  const { t } = useTranslation();
  const { id: flowId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const { saveFlow } = useSaveFlow();
  const {
    loadFlow,
    resetFlow,
    isDirty,
    flowId: currentFlowId,
    selectedNodeId,
    nodes,
    removeNode,
    selectNode,
  } = useFlowStore();

  const [showSettings, setShowSettings] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [showExecutionsPanel, setShowExecutionsPanel] = useState(false);
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const canvasRef = useRef<HTMLDivElement>(null);

  const { data: executionsData } = useFlowExecutions(flowId || '', undefined, {
    enabled: showExecutionsPanel && !!flowId,
    refetchInterval: 5000,
  });
  const createCronMutation = useCreateCronJob();

  const selectedNode = selectedNodeId
    ? nodes.find((n) => n.id === selectedNodeId)
    : null;

  const { data: flowData, isLoading, error, refetch } = useQuery({
    queryKey: ['flow', flowId],
    queryFn: () => fetchFlow(flowId!),
    enabled: !!flowId && flowId !== 'new',
    staleTime: 30000,
    retry: 2,
  });

  useEffect(() => {
    if (flowData) {
      loadFlow({
        id: flowData.id,
        name: flowData.name,
        nodes: flowData.nodes as never[],
        edges: flowData.edges as never[],
      });
    }
  }, [flowData, loadFlow]);

  useEffect(() => {
    if (!flowId && !currentFlowId) {
      resetFlow();
    }
  }, [flowId, currentFlowId, resetFlow]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const isInputFocused = ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName);

      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault();
        document.querySelector<HTMLButtonElement>('[data-action="save"]')?.click();
      }

      if ((e.metaKey || e.ctrlKey) && e.key === 'z') {
        if (isInputFocused) return;
        e.preventDefault();
        if (e.shiftKey) {
          useFlowStore.getState().redo();
        } else {
          useFlowStore.getState().undo();
        }
      }

      if ((e.metaKey || e.ctrlKey) && e.key === 'y') {
        if (isInputFocused) return;
        e.preventDefault();
        useFlowStore.getState().redo();
      }

      if (e.key === 'Delete' || e.key === 'Backspace') {
        if (isInputFocused) return;
        if (selectedNodeId) {
          e.preventDefault();
          removeNode(selectedNodeId);
        }
      }

      if (e.key === 'Escape') {
        selectNode(null);
        setShowSettings(false);
        setShowDeleteConfirm(false);
      }

      if ((e.metaKey || e.ctrlKey) && e.key === 'b') {
        e.preventDefault();
        setSidebarCollapsed((prev) => !prev);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedNodeId, removeNode, selectNode]);

  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (isDirty) {
        e.preventDefault();
        e.returnValue = '';
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [isDirty]);

  const handleRun = useCallback(async () => {
    let fd = useFlowStore.getState().getFlowData();

    if (fd.nodes.length === 0) {
      setRunError(t('flowEditor.runNeedNodes'));
      return;
    }

    setIsRunning(true);
    setRunError(null);

    try {
      if (!fd.id) {
        try {
          await saveFlow();
        } catch {
          setRunError(t('flowEditor.runSaveFailed'));
          return;
        }
        fd = useFlowStore.getState().getFlowData();
        if (!fd.id) {
          setRunError(t('flowEditor.runSaveFailed'));
          return;
        }
        const isNewRoute = location.pathname === '/workflows/new';
        if (isNewRoute) {
          navigate(`/workflows/${fd.id}`, { replace: true });
        }
      }

      const result = await runFlow(fd.id!, fd.nodes);
      navigate(`/executions/${result.executionId}`);
    } catch (err) {
      setRunError(err instanceof Error ? err.message : t('flowEditor.runFailed'));
    } finally {
      setIsRunning(false);
    }
  }, [navigate, t, saveFlow, location.pathname]);

  const handleSettings = useCallback(() => {
    setShowSettings(true);
  }, []);

  const handleDeleteFlow = useCallback(async () => {
    if (!currentFlowId) return;

    try {
      await apiClient.delete(`/workflow/flows/${currentFlowId}`);
      navigate('/workflows');
    } catch (err) {
      console.error('Delete failed:', err);
    }
  }, [currentFlowId, navigate]);

  const handleDuplicateFlow = useCallback(async () => {
    const fd = useFlowStore.getState().getFlowData();
    loadFlow({
      id: null,
      name: `${fd.name}${t('flowEditor.duplicateSuffix')}`,
      nodes: fd.nodes,
      edges: fd.edges,
    });
  }, [loadFlow, t]);

  /**
   * Only block the whole page with a full-screen loader when we have NO usable
   * flow to paint yet. If the persisted store already holds the same flow
   * (e.g. the user is refreshing the same page they were on), render the
   * shell + canvas immediately and let the background refetch update the
   * nodes/edges when it arrives — this turns a "loading → content" flash
   * into an instant paint.
   */
  if (isLoading && flowId && flowId !== 'new' && currentFlowId !== flowId) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center bg-background">
        <PageLoader message={t('flowEditor.loadingFlow')} />
      </div>
    );
  }

  if (error && flowId && flowId !== 'new' && currentFlowId !== flowId) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center bg-background">
        <div className="text-center max-w-md px-4">
          <div className="w-16 h-16 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center mx-auto mb-4">
            <AlertTriangle className="w-8 h-8 text-red-500" />
          </div>
          <h2 className="text-xl font-semibold text-foreground mb-2">
            {t('flowEditor.loadFailedTitle')}
          </h2>
          <p className="text-muted-foreground mb-6">
            {error instanceof Error ? error.message : t('flowEditor.loadFailedDesc')}
          </p>
          <div className="flex items-center justify-center gap-3">
            <Button variant="outline" onClick={() => refetch()}>
              {t('flowEditor.tryAgain')}
            </Button>
            <Button onClick={() => navigate('/workflows')}>
              {t('flowEditor.backToWorkflows')}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <ReactFlowProvider>
      <div className="flex min-h-0 flex-1 flex-col bg-background">
        <FlowToolbar
          onRun={handleRun}
          onSettings={handleSettings}
          isRunning={isRunning}
          extraActions={
            flowId ? (
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setShowExecutionsPanel((p) => !p)}
                  className={cn(
                    'flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg transition-colors',
                    showExecutionsPanel
                      ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300'
                      : 'text-muted-foreground hover:bg-surface-sunken'
                  )}
                  title={t('flowEditor.runHistory')}
                >
                  <Activity className="w-3.5 h-3.5" />
                  {t('flowEditor.executions')}
                  {executionsData && executionsData.total > 0 && (
                    <span className="ml-1 bg-primary-500 text-white text-xs rounded-full w-4 h-4 flex items-center justify-center">
                      {Math.min(executionsData.total, 9)}
                    </span>
                  )}
                </button>
                <button
                  onClick={() => setShowScheduleModal(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-muted-foreground hover:bg-surface-sunken rounded-lg transition-colors"
                  title={t('flowEditor.scheduleWorkflow')}
                >
                  <Clock className="w-3.5 h-3.5" />
                  {t('flowEditor.schedule')}
                </button>
              </div>
            ) : null
          }
        />

        {runError && (
          <div className="px-4 py-2 bg-red-50 dark:bg-red-900/30 border-b border-red-200 dark:border-red-800 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0" />
            <p className="text-sm text-red-700 dark:text-red-300 flex-1">{runError}</p>
            <button
              onClick={() => setRunError(null)}
              className="p-1 hover:bg-red-100 dark:hover:bg-red-800/50 rounded"
            >
              <X className="w-4 h-4 text-red-500" />
            </button>
          </div>
        )}

        <div className="flex flex-1 overflow-hidden">
          <FlowSidebar
            collapsed={sidebarCollapsed}
            onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
          />

          <main ref={canvasRef} className="flex-1 relative">
            {flowId && currentFlowId !== flowId ? (
              <div className="flex h-full w-full items-center justify-center bg-background">
                <PageLoader message={t('flowEditor.loadingFlow')} />
              </div>
            ) : (
              <FlowCanvas />
            )}
          </main>

          {selectedNode && (
            <NodeConfigPanel
              node={selectedNode}
              onClose={() => selectNode(null)}
            />
          )}
        </div>

        {showSettings && (
          <SettingsModal
            onClose={() => setShowSettings(false)}
            onDelete={() => setShowDeleteConfirm(true)}
            onDuplicate={handleDuplicateFlow}
            isExisting={!!currentFlowId}
          />
        )}

        {showDeleteConfirm && (
          <ConfirmDeleteModal
            flowName={useFlowStore.getState().flowName}
            onConfirm={handleDeleteFlow}
            onCancel={() => setShowDeleteConfirm(false)}
          />
        )}

        {/* Executions side panel */}
        {showExecutionsPanel && flowId && (
          <div className="absolute right-0 top-14 bottom-0 z-30 flex w-80 flex-col border-l border-border bg-surface shadow-soft">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <h3 className="text-sm font-semibold text-foreground">{t('flowEditor.runHistoryTitle')}</h3>
              <button
                onClick={() => setShowExecutionsPanel(false)}
                className="rounded p-1 text-muted-foreground-tertiary hover:bg-surface-sunken hover:text-foreground"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="flex-1 divide-y divide-border overflow-y-auto">
              {!executionsData || executionsData.executions.length === 0 ? (
                <div className="py-8 px-4">
                  <EmptyState
                    type="data"
                    title={t('flowEditor.noExecutionsTitle')}
                    description={t('flowEditor.noExecutionsDesc')}
                    size="sm"
                  />
                </div>
              ) : (
                executionsData.executions.map((exec) => (
                  <button
                    key={exec.id}
                    onClick={() => navigate(`/executions/${exec.id}`)}
                    className="w-full text-left px-4 py-3 transition-colors hover:bg-surface-sunken"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className={cn(
                        'text-xs font-medium px-2 py-0.5 rounded-full',
                        exec.status === 'completed' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300' :
                        exec.status === 'failed' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300' :
                        exec.status === 'running' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300' :
                        'bg-surface-sunken text-muted-foreground'
                      )}>
                        {exec.status}
                      </span>
                      <span className="text-xs text-muted-foreground-tertiary">
                        {exec.duration_ms ? `${(exec.duration_ms / 1000).toFixed(1)}s` : ''}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Clock className="w-3 h-3" />
                      {exec.started_at ? new Date(exec.started_at).toLocaleString() : new Date(exec.created_at).toLocaleString()}
                    </div>
                    {exec.error && (
                      <p className="text-xs text-red-600 dark:text-red-400 mt-1 truncate">{exec.error}</p>
                    )}
                  </button>
                ))
              )}
            </div>
            <div className="border-t border-border p-3">
              <button
                onClick={() => navigate(`/workflows/${flowId}/executions`)}
                className="w-full text-center text-xs text-primary-600 dark:text-primary-400 hover:underline"
              >
                {t('flowEditor.viewAllExecutions')}
              </button>
            </div>
          </div>
        )}

        {/* Schedule cron modal */}
        {showScheduleModal && flowId && (
          <CronJobModal
            open={showScheduleModal}
            onClose={() => setShowScheduleModal(false)}
            onSave={async (data) => {
              await createCronMutation.mutateAsync({ ...data, target_id: flowId, job_type: 'flow' });
              setShowScheduleModal(false);
            }}
            mode="create"
            isLoading={createCronMutation.isPending}
          />
        )}
      </div>
    </ReactFlowProvider>
  );
}

interface SettingsModalProps {
  onClose: () => void;
  onDelete: () => void;
  onDuplicate: () => void;
  isExisting: boolean;
}

function SettingsModal({ onClose, onDelete, onDuplicate, isExisting }: SettingsModalProps) {
  const { t } = useTranslation();
  const { flowName, setFlowName, nodes, edges } = useFlowStore();
  const [description, setDescription] = useState('');
  const [tags, setTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState('');

  const handleAddTag = useCallback(() => {
    const trimmed = tagInput.trim().toLowerCase();
    if (trimmed && !tags.includes(trimmed)) {
      setTags([...tags, trimmed]);
      setTagInput('');
    }
  }, [tagInput, tags]);

  const handleRemoveTag = useCallback((tag: string) => {
    setTags(tags.filter((t) => t !== tag));
  }, [tags]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAddTag();
    }
  }, [handleAddTag]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      <div
        className={cn(
          'relative w-full max-w-xl rounded-2xl shadow-2xl',
          'bg-surface',
          'border border-border',
          'animate-in fade-in-0 zoom-in-95 duration-200'
        )}
      >
        <div className="flex items-center justify-between border-b border-border p-6">
          <h2 className="text-xl font-semibold text-foreground">
            {t('flowEditor.flowSettingsTitle')}
          </h2>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-muted-foreground-tertiary transition-colors hover:bg-surface-sunken hover:text-foreground"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="max-h-[60vh] space-y-5 overflow-y-auto p-6">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-muted-foreground">
              {t('flowEditor.flowNameLabel')}
            </label>
            <Input
              value={flowName}
              onChange={(e) => setFlowName(e.target.value)}
              placeholder={t('flowEditor.namePlaceholder')}
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-muted-foreground">
              {t('flowEditor.flowDescLabel')}
            </label>
            <Textarea
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="resize-none"
              placeholder={t('flowEditor.descPlaceholder')}
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-muted-foreground">
              {t('flowEditor.tagsLabel')}
            </label>
            <div className="flex flex-wrap gap-2 mb-2">
              {tags.map((tag) => (
                <span
                  key={tag}
                  className="inline-flex items-center gap-1 px-2 py-1 bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 rounded-full text-sm"
                >
                  <Tag className="w-3 h-3" />
                  {tag}
                  <button
                    onClick={() => handleRemoveTag(tag)}
                    className="p-0.5 hover:bg-primary-200 dark:hover:bg-primary-800/50 rounded-full"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
            <Input
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={t('flowEditor.tagsPlaceholder')}
            />
          </div>

          <div className="rounded-lg bg-surface-sunken/80 p-4">
            <h3 className="mb-2 flex items-center gap-2 text-sm font-medium text-foreground">
              <Info className="w-4 h-4" />
              {t('flowEditor.flowStatsTitle')}
            </h3>
            <div className="grid grid-cols-1 gap-4 text-sm sm:grid-cols-2">
              <div>
                <span className="text-muted-foreground">{t('flowEditor.nodesStat')}</span>
                <span className="ml-2 font-medium text-foreground">{nodes.length}</span>
              </div>
              <div>
                <span className="text-muted-foreground">{t('flowEditor.connectionsStat')}</span>
                <span className="ml-2 font-medium text-foreground">{edges.length}</span>
              </div>
            </div>
          </div>

          {isExisting && (
            <div className="flex items-center gap-2 pt-2">
              <Button variant="secondary" size="sm" leftIcon={<Copy className="w-4 h-4" />} onClick={onDuplicate}>
                {t('flowEditor.duplicateFlow')}
              </Button>
              <Button variant="danger" size="sm" leftIcon={<Trash2 className="w-4 h-4" />} onClick={onDelete}>
                {t('flowEditor.deleteFlow')}
              </Button>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3 border-t border-border px-6 py-4">
          <Button variant="outline" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button onClick={onClose}>
            {t('flowEditor.saveChanges')}
          </Button>
        </div>
      </div>
    </div>
  );
}

interface ConfirmDeleteModalProps {
  flowName: string;
  onConfirm: () => void;
  onCancel: () => void;
}

function ConfirmDeleteModal({ flowName, onConfirm, onCancel }: ConfirmDeleteModalProps) {
  const { t } = useTranslation();
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onCancel} />

      <div
        className={cn(
          'relative w-full max-w-md rounded-2xl p-6 shadow-2xl',
          'bg-surface',
          'border border-border',
          'animate-in fade-in-0 zoom-in-95 duration-200'
        )}
      >
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/30">
          <Trash2 className="w-6 h-6 text-red-500" />
        </div>

        <h2 className="mb-2 text-center text-xl font-semibold text-foreground">
          {t('flowEditor.confirmDeleteFlowTitle')}
        </h2>
        <p className="mb-6 text-center text-muted-foreground">
          {t('flowEditor.confirmDeleteFlowBody', { name: flowName })}
        </p>

        <div className="flex items-center gap-3">
          <Button variant="outline" onClick={onCancel} className="flex-1">
            {t('common.cancel')}
          </Button>
          <Button variant="danger" onClick={onConfirm} className="flex-1">
            {t('flowEditor.delete')}
          </Button>
        </div>
      </div>
    </div>
  );
}

export default FlowPage;
