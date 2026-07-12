import { act, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { apiClient } from '@/api/client';
import { useGenUiFormsStore } from '@/stores/genUiForms';

import { useWorkflowInputRun } from './useWorkflowInputRun';

vi.mock('@/api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

vi.mock('@/components/chat/workflow/chatWorkflowRunActions', () => ({
  startChatWorkflowEmbedRun: vi.fn().mockResolvedValue(undefined),
  runChatWorkflowStep: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('@/lib/genUiActionBus', () => ({
  dispatchGenUiAction: vi.fn(),
}));

import { dispatchGenUiAction } from '@/lib/genUiActionBus';
import {
  runChatWorkflowStep,
  startChatWorkflowEmbedRun,
} from '@/components/chat/workflow/chatWorkflowRunActions';

function RunProbe(props: Parameters<typeof useWorkflowInputRun>[0]) {
  const { run } = useWorkflowInputRun(props);
  return (
    <button type="button" onClick={() => void run()}>
      trigger-run
    </button>
  );
}

describe('useWorkflowInputRun', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useGenUiFormsStore.setState({ values: {} });
  });

  it('dispatches chat_embed run with coerced inputs', async () => {
    const formKey = 's::m::embed-form';
    useGenUiFormsStore.getState().setField(formKey, 'q', 'hello');
    render(
      <RunProbe
        formKey={formKey}
        inputs={[{ name: 'q', type: 'string', required: true }]}
        flowId=""
        runTarget={{
          kind: 'chat_embed',
          sessionId: 's',
          messageId: 'm',
          digest: 'd'.repeat(64),
        }}
      />,
    );
    await act(async () => {
      screen.getByText('trigger-run').click();
    });
    expect(startChatWorkflowEmbedRun).toHaveBeenCalledWith(
      expect.objectContaining({
        sessionId: 's',
        messageId: 'm',
        inputs: { q: 'hello' },
      }),
    );
  });

  it('dispatches flow run through genUi action bus', async () => {
    const formKey = 'scope::root::workflow-inputs-f1';
    useGenUiFormsStore.getState().setField(formKey, 'n', '3');
    render(
      <RunProbe
        formKey={formKey}
        inputs={[{ name: 'n', type: 'integer' }]}
        flowId="f1"
        runTarget={{ kind: 'flow' }}
      />,
    );
    await act(async () => {
      screen.getByText('trigger-run').click();
    });
    expect(dispatchGenUiAction).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'run_workflow',
        payload: expect.objectContaining({
          flowId: 'f1',
          values: { n: 3 },
        }),
      }),
      expect.any(Object),
    );
  });

  it('reports missing required inputs', async () => {
    const onRunError = vi.fn();
    render(
      <RunProbe
        formKey="k"
        inputs={[{ name: 'req', type: 'string', required: true }]}
        flowId="f1"
        onRunError={onRunError}
      />,
    );
    await act(async () => {
      screen.getByText('trigger-run').click();
    });
    expect(onRunError).toHaveBeenCalled();
    expect(apiClient.post).not.toHaveBeenCalled();
    expect(startChatWorkflowEmbedRun).not.toHaveBeenCalled();
    expect(runChatWorkflowStep).not.toHaveBeenCalled();
  });
});
