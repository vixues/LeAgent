import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useChatStore } from '@/stores/chat';
import { useLayoutStore } from '@/stores/layout';
import { useSnippetsStore } from '@/stores/snippets';
import { ChatWorkspacePanel } from './ChatWorkspacePanel';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? _key,
  }),
}));

vi.mock('@/hooks/useAgentMemorySnapshot', () => ({
  useAgentMemorySnapshot: () => ({
    data: { episodes: [{}], facts: [{}], procedures: [{}] },
  }),
}));

vi.mock('./WorkspaceTabBar', () => ({
  WorkspaceTabBar: ({ counts }: { counts: Record<string, number | undefined> }) => (
    <div data-testid="tabbar">
      agent:{counts.agent} snippets:{counts.snippets} memory:{counts.memory}
    </div>
  ),
}));
vi.mock('./FilesTab', () => ({ FilesTab: () => <div>Files tab</div> }));
vi.mock('./AgentWorkspaceTab', () => ({
  AgentWorkspaceTab: () => <div>Agent tab</div>,
}));
vi.mock('./SnippetsTab', () => ({ SnippetsTab: () => <div>Snippets tab</div> }));
vi.mock('./ContextMemoryTab', () => ({ ContextMemoryTab: () => <div>Memory tab</div> }));

describe('ChatWorkspacePanel', () => {
  beforeEach(() => {
    useLayoutStore.setState({
      workspaceOpen: true,
      workspaceTab: 'agent',
    });
    useChatStore.setState({
      currentSessionId: 's1',
      messages: {
        s1: [
          {
            id: 'm1',
            role: 'assistant',
            content: '',
            createdAt: new Date(0).toISOString(),
            toolCalls: [
              {
                id: 'tc1',
                name: 'project_read',
                arguments: { path: 'README.md' },
                status: 'success',
              },
            ],
          },
        ],
      },
    });
    useSnippetsStore.setState({
      snippets: [
        {
          id: 'snip',
          title: 'Snippet',
          body: 'x',
          createdAt: new Date(0).toISOString(),
          updatedAt: new Date(0).toISOString(),
        },
      ],
    });
  });

  it('renders complementary workspace with tab counts', () => {
    render(<ChatWorkspacePanel />);

    expect(screen.getByRole('complementary', { name: 'Workspace' })).toBeInTheDocument();
    expect(screen.getByTestId('tabbar')).toHaveTextContent('agent:1');
    expect(screen.getByTestId('tabbar')).toHaveTextContent('snippets:1');
    expect(screen.getByTestId('tabbar')).toHaveTextContent('memory:3');
    expect(screen.getByText('Agent tab')).toBeInTheDocument();
  });
});
