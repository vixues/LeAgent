import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  GitBranch,
  Plus,
  Play,
  Edit2,
  Trash2,
  Copy,
  Clock,
  MoreHorizontal,
  Activity,
  Bot,
  Workflow,
  MessageSquare,
  Wrench,
  ChevronRight,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { EmptyState } from '@/components/common/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';
import { WorkflowsHubToolbar } from './WorkflowsHubToolbar';
import {
  useGetFlows,
  useDeleteFlow,
  useDuplicateFlow,
} from '@/controllers/API/queries/flows';
import { useRunFlow } from '@/controllers/API/queries/executions';
import { useToast } from '@/components/ui/Toaster';
import type { FlowData } from '@/types/flow';

const FLOW_TYPE_LUCIDE: Record<string, LucideIcon> = {
  agent: Bot,
  workflow: Workflow,
  chat: MessageSquare,
  tool: Wrench,
};

const FLOW_TYPE_COLORS: Record<string, string> = {
  agent: 'bg-primary-100 dark:bg-primary-900/30 text-primary-800 dark:text-primary-300',
  workflow: 'bg-sky-100 dark:bg-sky-900/30 text-sky-700 dark:text-sky-300',
  chat: 'bg-mint-100 dark:bg-mint-900/30 text-mint-700 dark:text-mint-300',
  tool: 'bg-peach-100 dark:bg-peach-900/30 text-peach-700 dark:text-peach-300',
};

function FlowCard({ flow, onEdit, onRun, onDuplicate, onDelete }: {
  flow: FlowData;
  onEdit: () => void;
  onRun: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation();
  const [menuOpen, setMenuOpen] = useState(false);
  const navigate = useNavigate();
  const flowTypeKey = flow.flow_type || 'workflow';
  const typeColor: string = FLOW_TYPE_COLORS[flowTypeKey] ?? FLOW_TYPE_COLORS.workflow ?? '';
  const TypeIcon: LucideIcon = FLOW_TYPE_LUCIDE[flowTypeKey] ?? Workflow;

  return (
    <div
      className={cn(
        'group relative rounded-xl p-5 bg-surface',
        'border border-border',
        'hover:border-primary-300 dark:hover:border-primary-600',
        'hover:shadow-md transition-[color,background-color,border-color,box-shadow,opacity,transform] cursor-pointer'
      )}
      onClick={onEdit}
    >
      {/* Type tag */}
      <div className="flex items-start justify-between mb-3">
        <span className={cn('flex items-center gap-1.5 text-xs font-medium px-2 py-1 rounded-full', typeColor)}>
          <TypeIcon className="w-4 h-4" strokeWidth={2} />
          {t(`list.flowType.${flowTypeKey}`)}
        </span>
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={(e) => { e.stopPropagation(); onRun(); }}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-mint-600 dark:hover:text-mint-400 hover:bg-mint-50 dark:hover:bg-mint-900/20 transition-colors"
            title={t('list.runTitle')}
          >
            <Play className="w-4 h-4" />
          </button>
          <div className="relative">
            <button
              onClick={(e) => { e.stopPropagation(); setMenuOpen(!menuOpen); }}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-surface-sunken transition-colors"
            >
              <MoreHorizontal className="w-4 h-4" />
            </button>
            {menuOpen && (
              <div
                className="absolute right-0 top-full mt-1 z-50 w-40 bg-surface rounded-xl border border-border shadow-lg py-1"
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  onClick={() => { onEdit(); setMenuOpen(false); }}
                  className="flex items-center gap-2 w-full px-3 py-2 text-sm text-foreground hover:bg-surface-sunken"
                >
                  <Edit2 className="w-3.5 h-3.5" /> {t('list.edit')}
                </button>
                <button
                  onClick={() => {
                    navigate(`/workflows/${flow.id}?panel=run`);
                    setMenuOpen(false);
                  }}
                  className="flex items-center gap-2 w-full px-3 py-2 text-sm text-foreground hover:bg-surface-sunken"
                >
                  <Activity className="w-3.5 h-3.5" /> {t('list.executions')}
                </button>
                <button
                  onClick={() => { onDuplicate(); setMenuOpen(false); }}
                  className="flex items-center gap-2 w-full px-3 py-2 text-sm text-foreground hover:bg-surface-sunken"
                >
                  <Copy className="w-3.5 h-3.5" /> {t('list.duplicate')}
                </button>
                <button
                  onClick={() => { onDelete(); setMenuOpen(false); }}
                  className="flex items-center gap-2 w-full px-3 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20"
                >
                  <Trash2 className="w-3.5 h-3.5" /> {t('list.delete')}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Icon & Name */}
      <div className="flex items-center gap-2.5 mb-1">
        <span
          className={cn(
            'inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg',
            typeColor
          )}
          aria-hidden
        >
          <TypeIcon className="w-[18px] h-[18px]" strokeWidth={2} />
        </span>
        <h3 className="text-sm font-semibold text-gray-900 dark:text-white truncate">{flow.name}</h3>
      </div>
      {flow.description && (
        <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-2 mb-3">{flow.description}</p>
      )}

      {/* Tags */}
      {flow.tags && flow.tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-3">
          {(typeof flow.tags === 'string' ? flow.tags.split(',') : flow.tags).slice(0, 3).map((tag: string) => (
            <span key={tag} className="text-xs px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400">
              {tag.trim()}
            </span>
          ))}
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between text-xs text-gray-400 dark:text-gray-500 mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1">
            <Activity className="w-3 h-3" />
            {t('list.runsCount', { count: flow.run_count || 0 })}
          </span>
          {flow.last_run_at && (
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {new Date(flow.last_run_at).toLocaleDateString()}
            </span>
          )}
        </div>
        <button
          onClick={(e) => { e.stopPropagation(); onEdit(); }}
          className="flex items-center gap-1 text-primary-600 dark:text-primary-400 hover:underline"
        >
          {t('list.open')} <ChevronRight className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
}

/** Workflow grid/list — the "Workflows" tab body of the unified hub. */
export function WorkflowListView() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [view, setView] = useState<'grid' | 'list'>('grid');

  const { data, isLoading, refetch } = useGetFlows({
    search: search || undefined,
    pageSize: 50,
  });

  const deleteMutation = useDeleteFlow();
  const duplicateMutation = useDuplicateFlow();
  const runMutation = useRunFlow();

  const flows = data?.data || [];
  const filtered = flows.filter((f) => {
    if (typeFilter && f.flow_type !== typeFilter) return false;
    return true;
  });

  const handleDelete = async (flow: FlowData) => {
    if (!confirm(t('list.confirmDelete', { name: flow.name }))) return;
    try {
      await deleteMutation.mutateAsync(flow.id);
      toast({ title: t('list.toastDeleted') });
    } catch {
      toast({ title: t('list.toastDeleteError'), variant: 'error' });
    }
  };

  const handleDuplicate = async (flow: FlowData) => {
    try {
      await duplicateMutation.mutateAsync({ id: flow.id });
      toast({ title: t('list.toastDuplicated') });
    } catch {
      toast({ title: t('list.toastDuplicateError'), variant: 'error' });
    }
  };

  const handleRun = async (flow: FlowData) => {
    try {
      const result = await runMutation.mutateAsync({ flowId: flow.id });
      toast({ title: t('list.toastStarted') });
      if (result.execution_id) {
        navigate(`/executions/${result.execution_id}`);
      }
    } catch {
      toast({ title: t('list.toastRunError'), variant: 'error' });
    }
  };

  return (
    <div className="space-y-6">
      <WorkflowsHubToolbar
        search={search}
        onSearchChange={setSearch}
        searchPlaceholder={t('list.searchPlaceholder')}
        filterValue={typeFilter}
        onFilterChange={setTypeFilter}
        filterOptions={[
          { value: '', label: t('list.allTypes') },
          { value: 'agent', label: t('list.flowType.agent'), icon: <Bot className="h-3 w-3" /> },
          { value: 'workflow', label: t('list.flowType.workflow'), icon: <Workflow className="h-3 w-3" /> },
          { value: 'chat', label: t('list.flowType.chat'), icon: <MessageSquare className="h-3 w-3" /> },
          { value: 'tool', label: t('list.flowType.tool'), icon: <Wrench className="h-3 w-3" /> },
        ]}
        view={view}
        onViewChange={setView}
        onRefresh={() => void refetch()}
        onFromTemplate={() => navigate('/templates')}
        primaryLabel={t('list.newWorkflow')}
        primaryIcon={<Plus className="h-4 w-4" />}
        onPrimaryClick={() => navigate('/workflows/new')}
      />

      {/* Content */}
      {isLoading ? (
        <div className={cn('grid gap-6', view === 'grid' ? 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3' : 'grid-cols-1')}>
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-48 rounded-xl" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <EmptyState
            icon={<GitBranch className="w-12 h-12" />}
            title={search || typeFilter ? t('list.emptyNoMatch') : t('list.emptyNone')}
            description={
              search || typeFilter
                ? t('list.emptyNoMatchHint')
                : t('list.emptyNoneHint')
            }
            action={
              !search && !typeFilter
                ? { label: t('list.createWorkflow'), onClick: () => navigate('/workflows/new') }
                : undefined
            }
          />
        </div>
      ) : (
        <div className={cn(
          'grid gap-6',
          view === 'grid' ? 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3' : 'grid-cols-1'
        )}>
          {filtered.map((flow) => (
            <FlowCard
              key={flow.id}
              flow={flow}
              onEdit={() => navigate(`/workflows/${flow.id}`)}
              onRun={() => handleRun(flow)}
              onDuplicate={() => handleDuplicate(flow)}
              onDelete={() => handleDelete(flow)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default WorkflowListView;
