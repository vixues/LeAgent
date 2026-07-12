import { act, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useExecutionOverlay } from '../store/executionOverlay';
import { WorkflowOperationPanel } from './WorkflowOperationPanel';

vi.mock('@/components/canvas/GenUiRegistry', () => ({
  GenUiTreeView: ({ tree }: { tree: { root?: { kind?: string } } }) => (
    <div data-testid="genui-tree" data-rootkind={tree?.root?.kind ?? ''} />
  ),
}));

const PROMPT_ID = 'chat-embed-panel-test';

describe('WorkflowOperationPanel', () => {
  beforeEach(() => {
    useExecutionOverlay.getState().reset();
  });

  it('renders WorkflowInputPanel for declared inputs', () => {
    render(
      <WorkflowOperationPanel
        flowId={null}
        inputs={[{ name: 'q', type: 'string', label: 'Question' }]}
        overlaySource={PROMPT_ID}
        runTarget={{ kind: 'chat_embed', sessionId: 's1', messageId: 'm1', digest: 'd1' }}
        formId="chat-workflow-embed-m1"
      />,
    );
    expect(screen.getByTestId('workflow-input-panel')).toBeTruthy();
    expect(screen.getByLabelText('Question')).toBeTruthy();
    expect(screen.getByRole('button', { name: /run|运行/i })).toBeTruthy();
  });

  it('reads live overlay state and renders results on completion', () => {
    render(
      <WorkflowOperationPanel
        flowId={null}
        inputs={[{ name: 'q', type: 'string' }]}
        overlaySource={PROMPT_ID}
        runTarget={{ kind: 'chat_embed', sessionId: 's1', messageId: 'm1', digest: 'd1' }}
        formId="chat-workflow-embed-m1"
      />,
    );

    act(() => {
      useExecutionOverlay.getState().start(PROMPT_ID, 'chat');
    });
    expect(screen.queryAllByTestId('genui-tree').some((n) => n.getAttribute('data-rootkind') === 'Stack')).toBe(
      false,
    );

    act(() => {
      useExecutionOverlay.getState().finish(PROMPT_ID, { outputs: { answer: 'hi' } });
    });
    expect(screen.queryAllByTestId('genui-tree').some((n) => n.getAttribute('data-rootkind') === 'Stack')).toBe(
      true,
    );
  });

  it('surfaces an external error message', () => {
    render(
      <WorkflowOperationPanel
        flowId={null}
        inputs={[{ name: 'q', type: 'string' }]}
        overlaySource={PROMPT_ID}
        error="quality gate failed"
      />,
    );
    expect(screen.getByText('quality gate failed')).toBeTruthy();
  });
});
