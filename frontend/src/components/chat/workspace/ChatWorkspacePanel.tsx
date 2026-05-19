import { useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { EMPTY_MESSAGE_LIST } from '@/lib/emptyChatMessages';
import { countProjectFamilyToolCalls } from '@/lib/projectToolEnvelope';
import { isWorkspaceTab, useLayoutStore } from '@/stores/layout';
import { useSnippetsStore } from '@/stores/snippets';
import { useChatStore } from '@/stores/chat';
import { useAgentMemorySnapshot } from '@/hooks/useAgentMemorySnapshot';
import { WorkspaceTabBar } from './WorkspaceTabBar';
import { FilesTab } from './FilesTab';
import { AgentWorkspaceTab } from './AgentWorkspaceTab';
import { CodingProjectPreviewTab } from './CodingProjectPreviewTab';
import { SnippetsTab } from './SnippetsTab';
import { ContextMemoryTab } from './ContextMemoryTab';

interface ChatWorkspacePanelProps {
  className?: string;
}

/**
 * Right-side workspace panel shown in the chat view. Houses Files, agent code,
 * Prompt Snippets, and agent context memory tabs. The outer `RightPanel` already provides the
 * tab-bar chrome + close control, so this component is deliberately chromeless.
 */
export function ChatWorkspacePanel({ className }: ChatWorkspacePanelProps) {
  const { t } = useTranslation();

  const workspaceTab = useLayoutStore((s) => s.workspaceTab);
  const setWorkspaceTab = useLayoutStore((s) => s.setWorkspaceTab);
  const workspaceOpen = useLayoutStore((s) => s.workspaceOpen);

  const currentSessionId = useChatStore((s) => s.currentSessionId);
  const sessionMessages = useChatStore((s) =>
    currentSessionId ? s.messages[currentSessionId] ?? EMPTY_MESSAGE_LIST : EMPTY_MESSAGE_LIST,
  );
  const memoryQuery = useAgentMemorySnapshot({
    sessionId: currentSessionId,
    enabled: Boolean(currentSessionId && workspaceOpen),
  });

  useEffect(() => {
    const raw = workspaceTab as string;
    if (raw === 'folders') {
      setWorkspaceTab('agent');
      return;
    }
    if (!isWorkspaceTab(workspaceTab)) {
      setWorkspaceTab('files');
    }
  }, [workspaceTab, setWorkspaceTab]);

  const snippetsCount = useSnippetsStore((s) => s.snippets.length);

  const agentToolCount = useMemo(
    () => countProjectFamilyToolCalls(sessionMessages),
    [sessionMessages],
  );

  const memoryTotal =
    memoryQuery.data === undefined
      ? undefined
      : memoryQuery.data.episodes.length +
        memoryQuery.data.facts.length +
        memoryQuery.data.procedures.length;

  const counts = useMemo(
    () => ({
      agent: agentToolCount,
      snippets: snippetsCount,
      memory: memoryTotal,
    }),
    [agentToolCount, snippetsCount, memoryTotal],
  );

  return (
    <div
      className={cn('flex min-h-0 h-full min-w-0 flex-1 basis-0 flex-col bg-transparent', className)}
      role="complementary"
      aria-label={t('chat.workspace.title', { defaultValue: 'Workspace' })}
    >
      {/* Tab bar */}
      <div className="flex-shrink-0 px-0 pt-1 pb-2">
        <WorkspaceTabBar
          activeTab={workspaceTab}
          onChange={setWorkspaceTab}
          counts={counts}
        />
      </div>

      {/* Tab body */}
      <div className="flex min-h-0 flex-1 basis-0 flex-col overflow-hidden">
        {workspaceTab === 'files' && <FilesTab />}
        {workspaceTab === 'agent' && <AgentWorkspaceTab />}
        {workspaceTab === 'preview' && <CodingProjectPreviewTab />}
        {workspaceTab === 'snippets' && <SnippetsTab />}
        {workspaceTab === 'memory' && (
          <div className="flex h-full min-h-0 min-w-0 flex-1 basis-0 flex-col overflow-hidden">
            <ContextMemoryTab />
          </div>
        )}
      </div>
    </div>
  );
}
