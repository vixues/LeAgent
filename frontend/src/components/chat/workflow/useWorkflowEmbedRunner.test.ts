import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Message } from '@/types/chat';
import { apiClient } from '@/api/client';
import { useChatStore } from '@/stores/chat';
import { useExecutionOverlay } from '@/features/workflow/store/executionOverlay';
import { useWorkflowEmbedRunner } from './useWorkflowEmbedRunner';

vi.mock('@/api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

const SESSION_ID = '00000000-0000-4000-8000-000000000001';
const MESSAGE_ID = 'msg-1';
const DIGEST = 'a'.repeat(64);

function seedEmbedMessage(): void {
  const msg: Message = {
    id: MESSAGE_ID,
    role: 'assistant',
    content: '',
    createdAt: new Date(0).toISOString(),
    workflowEmbed: { data: { nodes: {} }, digest: DIGEST },
  };
  useChatStore.setState({ messages: { [SESSION_ID]: [msg] } });
}

describe('useWorkflowEmbedRunner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useExecutionOverlay.getState().reset();
    seedEmbedMessage();
  });

  it('starts the run, sets running status, and starts a chat overlay', async () => {
    (apiClient.post as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      status: 'running',
      prompt_id: 'chat-embed-xyz',
      run_id: 'run-1',
    });
    const startSpy = vi.spyOn(useExecutionOverlay.getState(), 'start');

    const { result } = renderHook(() => useWorkflowEmbedRunner(SESSION_ID));
    await act(async () => {
      await result.current.runEmbed(MESSAGE_ID, DIGEST, '');
    });

    expect(apiClient.post).toHaveBeenCalledWith(
      `/chat/sessions/${SESSION_ID}/workflow-embeds/${MESSAGE_ID}/run`,
      expect.objectContaining({ message_id: MESSAGE_ID, workflow_digest: DIGEST }),
    );
    expect(startSpy).toHaveBeenCalledWith('chat-embed-xyz', 'chat');

    const run = useChatStore.getState().messages[SESSION_ID]?.[0]?.workflowEmbed?.run;
    expect(run?.status).toBe('running');
    expect(run?.promptId).toBe('chat-embed-xyz');
  });

  it('marks the run as error when the endpoint fails', async () => {
    (apiClient.post as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: false,
      error: 'nope',
    });

    const { result } = renderHook(() => useWorkflowEmbedRunner(SESSION_ID));
    await act(async () => {
      await result.current.runEmbed(MESSAGE_ID, DIGEST, '');
    });

    const run = useChatStore.getState().messages[SESSION_ID]?.[0]?.workflowEmbed?.run;
    expect(run?.status).toBe('error');
    expect(run?.error).toBe('nope');
  });
});
