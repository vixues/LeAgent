import { useTranslation } from 'react-i18next';
import { Brain, FileCode2, FileText, Monitor, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { WorkspaceTab } from '@/stores/layout';

interface WorkspaceTabBarProps {
  activeTab: WorkspaceTab;
  onChange: (tab: WorkspaceTab) => void;
  counts?: Partial<Record<WorkspaceTab, number>>;
  className?: string;
}

interface TabDef {
  id: WorkspaceTab;
  icon: typeof FileText;
  labelKey: string;
  fallback: string;
}

const TABS: TabDef[] = [
  { id: 'files', icon: FileText, labelKey: 'chat.workspace.tabs.files', fallback: 'Files' },
  { id: 'agent', icon: FileCode2, labelKey: 'chat.workspace.tabs.agent', fallback: 'Code' },
  { id: 'preview', icon: Monitor, labelKey: 'chat.workspace.tabs.preview', fallback: 'Preview' },
  { id: 'snippets', icon: Sparkles, labelKey: 'chat.workspace.tabs.snippets', fallback: 'Snippets' },
  { id: 'memory', icon: Brain, labelKey: 'chat.workspace.tabs.memory', fallback: 'Memory' },
];

export function WorkspaceTabBar({
  activeTab,
  onChange,
  counts,
  className,
}: WorkspaceTabBarProps) {
  const { t } = useTranslation();

  return (
    <div
      role="tablist"
      className={cn(
        'flex items-center gap-1 p-1 rounded-lg bg-surface-sunken',
        className
      )}
    >
      {TABS.map(({ id, icon: Icon, labelKey, fallback }) => {
        const isActive = id === activeTab;
        const count = counts?.[id];
        return (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(id)}
            className={cn(
              'flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 rounded-md text-xs font-medium transition-all duration-150',
              isActive
                ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300'
                : 'text-muted-foreground hover:text-foreground hover:bg-surface/60 dark:hover:bg-surface-elevated/40'
            )}
          >
            <Icon className="w-3.5 h-3.5" />
            <span className="truncate">
              {t(labelKey, { defaultValue: fallback })}
            </span>
            {typeof count === 'number' && count > 0 && (
              <span
                className={cn(
                  'ml-0.5 px-1.5 py-0.5 rounded-full text-[10px] leading-none font-semibold',
                  isActive
                    ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300'
                    : 'bg-surface text-muted-foreground-tertiary'
                )}
              >
                {count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
