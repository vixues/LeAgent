/**
 * Unified workflow page. One route namespace serves all workflow surfaces:
 *
 * - `/workflows`            → hub, "Workflows" tab (grid/list of flows)
 * - `/workflows/templates`  → hub, "Chat templates" tab
 * - `/workflows/new`        → ComfyUI-style graph editor (new draft)
 * - `/workflows/:id`        → graph editor for an existing flow
 *
 * The legacy standalone pages (`FlowPage`, `WorkflowListPage`,
 * `ChatWorkflowTemplatesPage`) were folded in here; their old routes
 * redirect to this namespace.
 */
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { GitBranch, LayoutList, Workflow } from 'lucide-react';

import { cn } from '@/lib/utils';
import { PageShell } from '@/components/layout/PageShell';
import { WorkflowGraphEditor } from '@/features/workflow/WorkflowGraphEditor';

import { WorkflowListView } from './WorkflowListView';
import { ChatTemplatesView } from './ChatTemplatesView';

const HUB_TABS = ['workflows', 'templates'] as const;
type HubTab = (typeof HUB_TABS)[number];

export default function WorkflowsPage() {
  const { t } = useTranslation();
  const { id } = useParams<{ id?: string }>();
  const location = useLocation();
  const navigate = useNavigate();

  // `/workflows/new` and `/workflows/:uuid` open the full-bleed editor.
  const isEditor = Boolean(id && id !== 'templates') ||
    location.pathname.endsWith('/workflows/new');
  if (isEditor) return <WorkflowGraphEditor />;

  const tab: HubTab = id === 'templates' ? 'templates' : 'workflows';

  return (
    <PageShell
      title={t('workflow.title')}
      description={
        tab === 'templates'
          ? t('chat.workflowTemplatesPage.description')
          : t('list.pageDescription')
      }
      icon={<GitBranch className="w-5 h-5" />}
    >
      {/* Tab strip */}
      <div className="flex items-center gap-1 border-b border-border">
        {HUB_TABS.map((key) => {
          const Icon = key === 'workflows' ? Workflow : LayoutList;
          return (
            <button
              key={key}
              onClick={() =>
                navigate(key === 'workflows' ? '/workflows' : '/workflows/templates')
              }
              className={cn(
                'flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium transition-colors',
                tab === key
                  ? 'border-primary-500 text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground',
              )}
            >
              <Icon className="h-4 w-4" />
              {key === 'workflows'
                ? t('nav.workflows')
                : t('nav.chatWorkflowTemplates')}
            </button>
          );
        })}
      </div>

      {tab === 'workflows' ? <WorkflowListView /> : <ChatTemplatesView />}
    </PageShell>
  );
}
