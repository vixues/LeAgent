/**
 * Unified workflow page. One route namespace serves all workflow surfaces:
 *
 * - `/workflows`                  → hub (tabs via `?tab=playbooks`)
 * - `/workflows?tab=playbooks`    → hub, "Chat playbooks" tab
 * - `/workflows/templates`        → redirects to `?tab=playbooks` (legacy)
 * - `/workflows/new`        → ComfyUI-style graph editor (new draft)
 * - `/workflows/:id`        → graph editor for an existing flow
 *
 * Full DAG template gallery lives at `/templates` (YAML starters with graph preview).
 */
import { Navigate, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { GitBranch, LayoutTemplate } from 'lucide-react';

import { cn } from '@/lib/utils';
import { PageShell } from '@/components/layout/PageShell';
import { WorkflowGraphEditor } from '@/features/workflow/WorkflowGraphEditor';

import { WorkflowListView } from './WorkflowListView';
import { ChatTemplatesView } from './ChatTemplatesView';
import { WorkflowsHubTabBar } from './WorkflowsHubTabBar';
import { WORKFLOWS_HUB_PLAYBOOKS_TAB, resolveWorkflowsHubTab, type WorkflowsHubTab } from './workflowsHubTab';

const TAB_HINT_KEYS: Record<WorkflowsHubTab, string> = {
  workflows: 'list.hub.tabHintSavedFlows',
  templates: 'list.hub.tabHintPlaybooks',
};

export default function WorkflowsPage() {
  const { t } = useTranslation();
  const { id } = useParams<{ id?: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const [, setSearchParams] = useSearchParams();

  if (id && id !== 'templates' && location.pathname.endsWith('/executions')) {
    return <Navigate to={`/workflows/${id}?panel=run`} replace />;
  }

  const isEditor =
    Boolean(id && id !== 'templates') || location.pathname.endsWith('/workflows/new');
  if (isEditor) return <WorkflowGraphEditor />;

  const tab: WorkflowsHubTab = resolveWorkflowsHubTab(location.pathname, location.search);

  const setHubTab = (key: WorkflowsHubTab) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (key === 'templates') {
          next.set('tab', WORKFLOWS_HUB_PLAYBOOKS_TAB);
        } else {
          next.delete('tab');
        }
        return next;
      },
      { replace: true },
    );
  };

  return (
    <PageShell
      title={t('workflow.title')}
      description={t('list.pageDescription')}
      icon={<GitBranch className="w-5 h-5" />}
    >
      <div className="flex flex-col gap-3 border-b border-border pb-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <WorkflowsHubTabBar activeTab={tab} onChange={setHubTab} />
          <button
            type="button"
            onClick={() => navigate('/templates')}
            className="inline-flex items-center gap-1.5 text-xs text-primary-600 hover:underline dark:text-primary-400"
          >
            <LayoutTemplate className="h-3.5 w-3.5" />
            {t('list.hub.openTemplateGallery')}
          </button>
        </div>
        <p className="min-h-[2.5rem] max-w-3xl text-xs leading-relaxed text-muted-foreground">
          {t(TAB_HINT_KEYS[tab])}
        </p>
      </div>

      <div className={cn(tab !== 'workflows' && 'hidden')} aria-hidden={tab !== 'workflows'}>
        <WorkflowListView />
      </div>
      <div className={cn(tab !== 'templates' && 'hidden')} aria-hidden={tab !== 'templates'}>
        <ChatTemplatesView />
      </div>
    </PageShell>
  );
}
