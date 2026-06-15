import { useTranslation } from 'react-i18next';
import { MessageSquareText, Workflow } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { WorkflowsHubTab } from './workflowsHubTab';

interface WorkflowsHubTabBarProps {
  activeTab: WorkflowsHubTab;
  onChange: (tab: WorkflowsHubTab) => void;
  className?: string;
}

const TAB_DEFS: {
  id: WorkflowsHubTab;
  icon: typeof Workflow;
  labelKey: string;
}[] = [
  { id: 'workflows', icon: Workflow, labelKey: 'list.hub.savedFlowsTab' },
  { id: 'templates', icon: MessageSquareText, labelKey: 'list.hub.playbooksTab' },
];

/** Hub tab strip — matches chat `WorkspaceTabBar` styling. */
export function WorkflowsHubTabBar({ activeTab, onChange, className }: WorkflowsHubTabBarProps) {
  const { t } = useTranslation();

  return (
    <div
      role="tablist"
      aria-label={t('list.hub.tabListAria')}
      className={cn('flex min-w-[16rem] items-center gap-1 rounded-lg bg-surface-sunken p-1 sm:min-w-[20rem]', className)}
    >
      {TAB_DEFS.map(({ id, icon: Icon, labelKey }) => {
        const isActive = id === activeTab;
        return (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(id)}
            className={cn(
              'flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium transition-all duration-150',
              isActive
                ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300'
                : 'text-muted-foreground hover:bg-surface/60 hover:text-foreground dark:hover:bg-surface-elevated/40',
            )}
          >
            <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden />
            <span className="truncate">{t(labelKey)}</span>
          </button>
        );
      })}
    </div>
  );
}
