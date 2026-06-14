/**
 * Unified workflow page. One route namespace serves all workflow surfaces:
 *
 * - `/workflows`            → hub, "Saved flows" tab (grid/list of user flows)
 * - `/workflows/templates`  → hub, "Chat playbooks" tab (runnable chat cards)
 * - `/workflows/new`        → ComfyUI-style graph editor (new draft)
 * - `/workflows/:id`        → graph editor for an existing flow
 *
 * Full DAG template gallery lives at `/templates` (YAML starters with graph preview).
 */
import { Navigate, useLocation, useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { GitBranch, LayoutTemplate, MessageSquareText, Workflow } from 'lucide-react';

import { cn } from '@/lib/utils';
import { PageShell } from '@/components/layout/PageShell';
import { WorkflowGraphEditor } from '@/features/workflow/WorkflowGraphEditor';

import { WorkflowListView } from './WorkflowListView';
import { ChatTemplatesView } from './ChatTemplatesView';

const HUB_TABS = ['workflows', 'templates'] as const;
type HubTab = (typeof HUB_TABS)[number];

const TAB_HINT_KEYS: Record<HubTab, string> = {
  workflows: 'list.hub.savedFlowsHint',
  templates: 'list.hub.playbooksHint',
};

export default function WorkflowsPage() {
  const { t } = useTranslation();
  const { id } = useParams<{ id?: string }>();
  const location = useLocation();
  const navigate = useNavigate();

  if (id && id !== 'templates' && location.pathname.endsWith('/executions')) {
    return <Navigate to={`/workflows/${id}?panel=run`} replace />;
  }

  const isEditor =
    Boolean(id && id !== 'templates') || location.pathname.endsWith('/workflows/new');
  if (isEditor) return <WorkflowGraphEditor />;

  const tab: HubTab = id === 'templates' ? 'templates' : 'workflows';

  return (
    <PageShell
      title={t('workflow.title')}
      description={t(TAB_HINT_KEYS[tab])}
      icon={<GitBranch className="w-5 h-5" />}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-border pb-3">
        <div className="flex items-center gap-1">
          {HUB_TABS.map((key) => {
            const Icon = key === 'workflows' ? Workflow : MessageSquareText;
            return (
              <button
                key={key}
                onClick={() =>
                  navigate(key === 'workflows' ? '/workflows' : '/workflows/templates')
                }
                className={cn(
                  'flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition-colors -mb-3',
                  tab === key
                    ? 'border-primary-500 text-foreground'
                    : 'border-transparent text-muted-foreground hover:text-foreground',
                )}
              >
                <Icon className="h-4 w-4" />
                {key === 'workflows' ? t('list.hub.savedFlowsTab') : t('list.hub.playbooksTab')}
              </button>
            );
          })}
        </div>
        <button
          type="button"
          onClick={() => navigate('/templates')}
          className="inline-flex items-center gap-1.5 text-xs text-primary-600 hover:underline dark:text-primary-400"
        >
          <LayoutTemplate className="h-3.5 w-3.5" />
          {t('list.hub.openTemplateGallery')}
        </button>
      </div>

      {tab === 'workflows' ? <WorkflowListView /> : <ChatTemplatesView />}
    </PageShell>
  );
}
