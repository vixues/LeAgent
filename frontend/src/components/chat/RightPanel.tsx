import { useTranslation } from 'react-i18next';
import { X, Layers } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useArtifactStore } from '@/stores/artifact';
import { useLayoutStore } from '@/stores/layout';
import { ArtifactViewer } from '@/components/workspace/ArtifactViewer';
import { ChatWorkspacePanel } from './workspace/ChatWorkspacePanel';
import { getArtifactIcon } from './workspace/artifactIcon';

/** Align with NavRail nav links — rounded pills, primary tint when active */
const railTabActive =
  'bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300';
const railTabIdle =
  'text-muted-foreground hover:bg-surface-sunken dark:hover:bg-surface-elevated hover:text-foreground';

export function RightPanel() {
  const { t } = useTranslation();
  const {
    artifacts,
    openTabIds,
    activeTabId,
    setActiveTab,
    closeTab,
  } = useArtifactStore();

  const workspaceOpen = useLayoutStore((s) => s.workspaceOpen);
  const setWorkspaceOpen = useLayoutStore((s) => s.setWorkspaceOpen);

  const hasArtifactTabs = openTabIds.length > 0;
  const showWorkspace = workspaceOpen;

  if (!hasArtifactTabs && !showWorkspace) return null;

  const isShowingWorkspace =
    !hasArtifactTabs || (activeTabId === null && showWorkspace);

  const handleCloseAll = () => {
    useArtifactStore.getState().closeArtifact();
    useArtifactStore.setState({ openTabIds: [], activeTabId: null });
    setWorkspaceOpen(false);
  };

  return (
    <div
      id="right-panel-shell"
      className={cn(
        'flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-2xl border border-border bg-surface',
        'shadow-soft ring-1 ring-black/[0.06] dark:ring-white/[0.08]',
        'transition-colors duration-150 ease-out',
        'chat-panel-enter'
      )}
    >
      {/* Tab bar — rounded pills (NavRail-style), no underline strip */}
      <div className="flex items-center gap-1.5 flex-shrink-0 overflow-x-auto no-scrollbar px-2 pt-2 pb-1.5">
        {/* Workspace tab (always first if open) */}
        {showWorkspace && (
          <button
            type="button"
            onClick={() => {
              useArtifactStore.getState().closeArtifact();
              useArtifactStore.setState({ activeTabId: null });
            }}
            className={cn(
              'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors duration-150 whitespace-nowrap shrink-0',
              isShowingWorkspace ? railTabActive : railTabIdle,
            )}
          >
            <Layers className="w-3.5 h-3.5 shrink-0" />
            <span>{t('chat.workspace.title', { defaultValue: 'Workspace' })}</span>
          </button>
        )}

        {/* Artifact tabs */}
        {openTabIds.map((tabId) => {
          const artifact = artifacts[tabId];
          if (!artifact) return null;
          const isActive = tabId === activeTabId && !isShowingWorkspace;
          return (
            <div
              key={tabId}
              className={cn(
                'flex min-w-0 max-w-[min(100%,240px)] items-center rounded-lg transition-colors duration-150 shrink-0',
                isActive
                  ? railTabActive
                  : 'text-muted-foreground hover:bg-surface-sunken/70 dark:hover:bg-surface-elevated/50',
              )}
            >
              <button
                type="button"
                onClick={() => setActiveTab(tabId)}
                className={cn(
                  'flex min-w-0 flex-1 items-center gap-1.5 rounded-lg py-1.5 pl-2.5 pr-0.5 text-left text-xs font-medium transition-colors',
                  isActive
                    ? 'text-primary-700 dark:text-primary-300'
                    : 'text-muted-foreground hover:text-foreground',
                )}
                title={artifact.title}
              >
                <span className="flex-shrink-0">{getArtifactIcon(artifact.type)}</span>
                <span className="min-w-0 truncate">{artifact.title}</span>
              </button>
              <button
                type="button"
                onClick={() => closeTab(tabId)}
                className={cn(
                  'mr-1 shrink-0 rounded-md p-1 transition-colors',
                  'text-muted-foreground-tertiary hover:text-foreground hover:bg-surface-sunken/80 dark:hover:bg-surface-elevated/60',
                )}
                aria-label={t('common.close', { defaultValue: 'Close' })}
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          );
        })}

        {/* Close panel */}
        <div className="ml-auto flex shrink-0 items-center pl-1">
          <button
            type="button"
            onClick={handleCloseAll}
            className="rounded-lg p-1.5 text-muted-foreground-tertiary transition-colors hover:bg-surface-sunken hover:text-foreground dark:hover:bg-surface-elevated"
            aria-label={t('common.closeAll', { defaultValue: 'Close panel' })}
            title={t('common.closeAll', { defaultValue: 'Close panel' })}
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Content — column flex so ArtifactViewer / workspace fill remaining height */}
      <div className="flex min-h-0 flex-1 basis-0 flex-col overflow-hidden px-2 pb-2">
        {isShowingWorkspace && showWorkspace ? (
          <ChatWorkspacePanel />
        ) : activeTabId && artifacts[activeTabId] ? (
          <ArtifactViewer />
        ) : (
          <div className="flex min-h-0 flex-1 items-center justify-center text-sm text-muted-foreground-tertiary">
            {t('chat.selectTab', { defaultValue: 'Select a tab to view' })}
          </div>
        )}
      </div>
    </div>
  );
}
