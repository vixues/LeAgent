import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import {
  Activity,
  ChevronRight,
  GitBranch,
  ListOrdered,
  MessageSquare,
  MessageSquareText,
} from 'lucide-react';
import { apiClient } from '@/api/client';
import { EmptyState } from '@/components/common/EmptyState';
import { Skeleton } from '@/components/ui/Skeleton';
import { cn } from '@/lib/utils';
import type { ChatWorkflowSpecModel } from '@/types/chat';
import { WorkflowsHubToolbar } from './WorkflowsHubToolbar';

interface ChatWorkflowTemplateRow {
  id: string;
  title: string;
  description: string;
  spec: ChatWorkflowSpecModel;
  digest: string;
  category?: string;
  playbook_id?: string | null;
}

interface MaterializeResponse {
  session_id: string;
  templates: { template_id: string; message_id: string }[];
}

const PLAYBOOK_BADGE_CLASS =
  'bg-mint-100 dark:bg-mint-900/30 text-mint-700 dark:text-mint-300';
const DEMO_BADGE_CLASS =
  'bg-sky-100 dark:bg-sky-900/30 text-sky-700 dark:text-sky-300';

function PlaybookCard({ row }: { row: ChatWorkflowTemplateRow }) {
  const { t } = useTranslation();
  const isPlaybook = row.category === 'playbook';
  const typeColor = isPlaybook ? PLAYBOOK_BADGE_CLASS : DEMO_BADGE_CLASS;
  const stepCount = row.spec.steps.length;

  return (
    <div
      className={cn(
        'group relative rounded-xl bg-surface p-5',
        'border border-border',
        'hover:border-primary-300 dark:hover:border-primary-600',
        'transition-[color,background-color,border-color,box-shadow] hover:shadow-md',
      )}
    >
      <div className="mb-3 flex items-start justify-between">
        <span className={cn('flex items-center gap-1.5 rounded-full px-2 py-1 text-xs font-medium', typeColor)}>
          <MessageSquareText className="h-4 w-4" strokeWidth={2} />
          {isPlaybook ? t('list.hub.playbookBadge') : t('list.hub.demoBadge')}
        </span>
      </div>

      <div className="mb-1 flex items-center gap-2.5">
        <span
          className={cn(
            'inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg',
            typeColor,
          )}
          aria-hidden
        >
          <MessageSquareText className="h-[18px] w-[18px]" strokeWidth={2} />
        </span>
        <h3 className="truncate text-sm font-semibold text-foreground">{row.title}</h3>
      </div>

      {row.description ? (
        <p className="mb-3 line-clamp-2 text-xs text-muted-foreground">{row.description}</p>
      ) : null}

      <div className="mt-3 flex items-center justify-between border-t border-border-subtle pt-3 text-xs text-muted-foreground-tertiary">
        <span className="flex items-center gap-1">
          <ListOrdered className="h-3 w-3" />
          {t('list.hub.stepsCount', { count: stepCount })}
        </span>
        {row.playbook_id ? (
          <Link
            to={`/templates?search=${encodeURIComponent(row.playbook_id.replace(/_/g, ' '))}`}
            className="flex items-center gap-1 text-primary-600 hover:underline dark:text-primary-400"
          >
            {t('list.open')}
            <ChevronRight className="h-3 w-3" />
          </Link>
        ) : (
          <span className="flex items-center gap-1 text-muted-foreground-tertiary">
            <Activity className="h-3 w-3" />
            {row.id}
          </span>
        )}
      </div>
    </div>
  );
}

/** Chat workflow template catalog — the "Chat playbooks" tab of the hub. */
export function ChatTemplatesView() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [view, setView] = useState<'grid' | 'list'>('grid');

  const templatesQuery = useQuery({
    queryKey: ['chat', 'workflow-templates'],
    queryFn: () => apiClient.get<ChatWorkflowTemplateRow[]>('/chat/workflow-templates'),
    staleTime: 60_000,
  });

  const materialize = useMutation({
    mutationFn: () =>
      apiClient.post<MaterializeResponse>('/chat/workflow-templates/materialize', {}),
    onSuccess: (data) => {
      navigate(`/chat/${data.session_id}`);
    },
  });

  const items = templatesQuery.data ?? [];

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((row) => {
      if (categoryFilter && row.category !== categoryFilter) return false;
      if (!q) return true;
      const haystack = [row.title, row.description, row.id, row.playbook_id ?? '']
        .join(' ')
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [items, search, categoryFilter]);

  return (
    <div className="space-y-6">
      <WorkflowsHubToolbar
        search={search}
        onSearchChange={setSearch}
        searchPlaceholder={t('list.hub.searchPlaybooksPlaceholder')}
        filterValue={categoryFilter}
        onFilterChange={setCategoryFilter}
        filterOptions={[
          { value: '', label: t('list.hub.filterAll') },
          {
            value: 'playbook',
            label: t('list.hub.playbookBadge'),
            icon: <MessageSquareText className="h-3 w-3" />,
          },
          {
            value: 'demo',
            label: t('list.hub.demoBadge'),
            icon: <MessageSquare className="h-3 w-3" />,
          },
        ]}
        view={view}
        onViewChange={setView}
        onRefresh={() => void templatesQuery.refetch()}
        onFromTemplate={() => navigate('/templates')}
        primaryLabel={t('list.hub.openTestLabShort')}
        primaryTitle={t('chat.workflowTemplatesPage.createLab')}
        primaryLoading={materialize.isPending}
        primaryIcon={<MessageSquare className="h-4 w-4" />}
        onPrimaryClick={() => materialize.mutate()}
      />

      {materialize.isError ? (
        <p className="text-sm text-red-600 dark:text-red-400">
          {t('chat.workflowTemplatesPage.materializeError')}
        </p>
      ) : null}

      {templatesQuery.isLoading ? (
        <div
          className={cn(
            'grid gap-6',
            view === 'grid' ? 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3' : 'grid-cols-1',
          )}
        >
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-48 rounded-xl" />
          ))}
        </div>
      ) : templatesQuery.isError ? (
        <p className="text-sm text-red-600 dark:text-red-400">
          {t('chat.workflowTemplatesPage.loadError')}
        </p>
      ) : filtered.length === 0 ? (
        <div className="flex flex-1 items-center justify-center">
          <EmptyState
            icon={<GitBranch className="h-12 w-12" />}
            title={search || categoryFilter ? t('list.hub.emptyNoMatch') : t('list.hub.emptyNone')}
            description={
              search || categoryFilter
                ? t('list.hub.emptyNoMatchHint')
                : t('list.hub.emptyNoneHint')
            }
            action={
              !search && !categoryFilter
                ? {
                    label: t('list.hub.openTestLabShort'),
                    onClick: () => materialize.mutate(),
                  }
                : undefined
            }
          />
        </div>
      ) : (
        <div
          className={cn(
            'grid gap-6',
            view === 'grid' ? 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3' : 'grid-cols-1',
          )}
        >
          {filtered.map((row) => (
            <PlaybookCard key={row.id} row={row} />
          ))}
        </div>
      )}
    </div>
  );
}

export default ChatTemplatesView;
