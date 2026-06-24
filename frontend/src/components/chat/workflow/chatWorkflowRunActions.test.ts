import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Message } from '@/types/chat';
import { apiClient } from '@/api/client';
import { useExecutionOverlay } from '@/features/workflow/store/executionOverlay';
import { useChatStore } from '@/stores/chat';

import { runChatWorkflowStep, startChatWorkflowEmbedRun } from './chatWorkflowRunActions';

vi.mock('@/api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

vi.mock('./workflowTodoSync', () => ({
  syncSessionTodosFromWorkflow: vi.fn(),
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

describe('startChatWorkflowEmbedRun', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useExecutionOverlay.getState().reset();
    seedEmbedMessage();
  });

  it('posts structured inputs and drives a chat overlay', async () => {
    (apiClient.post as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      prompt_id: 'chat-embed-1',
      run_id: 'run-1',
    });
    const startSpy = vi.spyOn(useExecutionOverlay.getState(), 'start');

    await startChatWorkflowEmbedRun({
      sessionId: SESSION_ID,
      messageId: MESSAGE_ID,
      digest: DIGEST,
      inputs: { prompt: 'a cat', steps: 8 },
    });

    expect(apiClient.post).toHaveBeenCalledWith(
      `/chat/sessions/${SESSION_ID}/workflow-embeds/${MESSAGE_ID}/run`,
      expect.objectContaining({
        message_id: MESSAGE_ID,
        workflow_digest: DIGEST,
        inputs: { prompt: 'a cat', steps: 8 },
      }),
    );
    expect(startSpy).toHaveBeenCalledWith('chat-embed-1', 'chat');
    const run = useChatStore.getState().messages[SESSION_ID]?.[0]?.workflowEmbed?.run;
    expect(run?.status).toBe('running');
    expect(run?.promptId).toBe('chat-embed-1');
  });

  it('omits the inputs key when there are no structured values', async () => {
    (apiClient.post as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      prompt_id: 'chat-embed-2',
    });

    await startChatWorkflowEmbedRun({
      sessionId: SESSION_ID,
      messageId: MESSAGE_ID,
      digest: DIGEST,
      inputs: {},
      userInput: 'plain.csv',
    });

    const body = (apiClient.post as ReturnType<typeof vi.fn>).mock.calls[0]![1] as Record<
      string,
      unknown
    >;
    expect(body.inputs).toBeUndefined();
    expect(body.user_input).toBe('plain.csv');
  });

  it('marks the run as error when the endpoint reports failure', async () => {
    (apiClient.post as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: false,
      error: 'nope',
    });

    await startChatWorkflowEmbedRun({
      sessionId: SESSION_ID,
      messageId: MESSAGE_ID,
      digest: DIGEST,
    });

    const run = useChatStore.getState().messages[SESSION_ID]?.[0]?.workflowEmbed?.run;
    expect(run?.status).toBe('error');
    expect(run?.error).toBe('nope');
  });
});

describe('runChatWorkflowStep', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useExecutionOverlay.getState().reset();
    const msg: Message = {
      id: MESSAGE_ID,
      role: 'assistant',
      content: '',
      createdAt: new Date(0).toISOString(),
      workflow: {
        spec: {
          version: 1,
          title: 'WF',
          steps: [
            { id: 'step-1', label: 'One', action: { kind: 'tool', tool_id: 'noop', arguments: {} } },
          ],
        },
        digest: DIGEST,
        stepRuns: {},
      },
    };
    useChatStore.setState({ messages: { [SESSION_ID]: [msg] } });
  });

  it('posts the step run with the collected user input', async () => {
    (apiClient.post as ReturnType<typeof vi.fn>).mockResolvedValue({
      success: true,
      prompt_id: 'step-prompt-1',
      run_id: 'run-9',
    });

    await runChatWorkflowStep({
      sessionId: SESSION_ID,
      messageId: MESSAGE_ID,
      stepId: 'step-1',
      digest: DIGEST,
      userInput: 'sales.csv',
    });

    expect(apiClient.post).toHaveBeenCalledWith(
      `/chat/sessions/${SESSION_ID}/workflow-steps/step-1/run`,
      expect.objectContaining({ message_id: MESSAGE_ID, user_input: 'sales.csv' }),
    );
    const stepRun =
      useChatStore.getState().messages[SESSION_ID]?.[0]?.workflow?.stepRuns?.['step-1'];
    expect(stepRun?.status).toBe('success');
  });
});
