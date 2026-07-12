import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiClient } from '@/api/client';
import { useChatStore } from '@/stores/chat';
import { useGenUiFormsStore } from '@/stores/genUiForms';
import type { Message } from '@/types/chat';

import { ChatWorkflowCard } from './ChatWorkflowCard';

vi.mock('@/api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

vi.mock('@/features/workflow/api/useExecutionStream', () => ({
  useExecutionStream: vi.fn(),
}));

vi.mock('./useWorkflowStepOverlaySync', () => ({
  useWorkflowStepOverlaySync: vi.fn(),
}));

vi.mock('./useWorkflowEmbedOverlaySync', () => ({
  useWorkflowEmbedOverlaySync: vi.fn(),
}));

vi.mock('./ChatWorkflowMiniGraph', () => ({
  ChatWorkflowMiniGraph: () => <div data-testid="mini-graph" />,
}));

vi.mock('./ChatWorkflowStepRail', () => ({
  ChatWorkflowStepRail: ({
    onRunStep,
  }: {
    onRunStep: (stepId: string) => void;
  }) => (
    <button type="button" onClick={() => onRunStep('step-1')}>
      run-step
    </button>
  ),
}));

const SESSION_ID = '00000000-0000-4000-8000-000000000001';
const MESSAGE_ID = 'msg-embed-1';
const DIGEST = 'a'.repeat(64);

function seedEmbedMessage(): void {
  const msg: Message = {
    id: MESSAGE_ID,
    role: 'assistant',
    content: '',
    createdAt: new Date(0).toISOString(),
    workflowEmbed: {
      data: { name: 'Demo', inputs: [{ name: 'source', type: 'file', label: 'Source' }] },
      digest: DIGEST,
    },
    attachments: [
      {
        id: 'att-1',
        name: 'data.csv',
        type: 'text/csv',
        localPath: '/uploads/data.csv',
      },
    ],
  };
  useChatStore.setState({
    messages: { [SESSION_ID]: [msg] },
  });
}

describe('ChatWorkflowCard workflow inputs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useGenUiFormsStore.setState({ values: {} });
    seedEmbedMessage();
  });

  it('runs embed workflow from native input panel', async () => {
    (apiClient.post as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      prompt_id: 'chat-embed-1',
      run_id: 'run-1',
    });

    render(<ChatWorkflowCard message={useChatStore.getState().messages[SESSION_ID]![0]!} sessionId={SESSION_ID} />);

    expect(screen.getByTestId('workflow-input-panel')).toBeTruthy();
    expect(screen.getByText(/session attachments|会话附件/i)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /data\.csv/i }));
    fireEvent.click(screen.getByRole('button', { name: /运行|run/i }));

    await waitFor(() => {
      expect(apiClient.post).toHaveBeenCalledWith(
        `/chat/sessions/${SESSION_ID}/workflow-embeds/${encodeURIComponent(MESSAGE_ID)}/run`,
        expect.objectContaining({
          workflow_digest: DIGEST,
          inputs: { source: '/uploads/data.csv' },
        }),
      );
    });
  });
});
