import { act, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useExecutionOverlay } from '../store/executionOverlay';
import { WorkflowOperationPanel } from './WorkflowOperationPanel';

// The real GenUI registry pulls in heavy media/chart renderers; stub it so the
// test focuses on the panel's overlay-driven section logic.
vi.mock('@/components/canvas/GenUiRegistry', () => ({
  GenUiTreeView: ({ tree }: { tree: { root?: { kind?: string; props?: { formId?: string } } } }) => (
    <div
      data-testid="genui-tree"
      data-rootkind={tree?.root?.kind ?? ''}
      data-formid={tree?.root?.props?.formId ?? ''}
    />
  ),
}));

const PROMPT_ID = 'chat-embed-panel-test';

function trees() {
  return screen.queryAllByTestId('genui-tree');
}

describe('WorkflowOperationPanel', () => {
  beforeEach(() => {
    useExecutionOverlay.getState().reset();
  });

  it('renders the generated input form scoped to the run target', () => {
    render(
      <WorkflowOperationPanel
        flowId={null}
        inputs={[{ name: 'q', type: 'string' }]}
        overlaySource={PROMPT_ID}
        runTarget={{ kind: 'chat_embed', sessionId: 's1', messageId: 'm1', digest: 'd1' }}
        formId="chat-workflow-embed-m1"
      />,
    );
    const form = trees().find((n) => n.getAttribute('data-rootkind') === 'Form');
    expect(form).toBeTruthy();
    expect(form!.getAttribute('data-formid')).toBe('chat-workflow-embed-m1');
    // No results while the run has not produced outputs.
    expect(trees().some((n) => n.getAttribute('data-rootkind') === 'Stack')).toBe(false);
  });

  it('reads live overlay state for its promptId and renders results on completion', () => {
    render(
      <WorkflowOperationPanel
        flowId={null}
        inputs={[{ name: 'q', type: 'string' }]}
        overlaySource={PROMPT_ID}
        runTarget={{ kind: 'chat_embed', sessionId: 's1', messageId: 'm1', digest: 'd1' }}
        formId="chat-workflow-embed-m1"
      />,
    );

    // Running: no structured results yet.
    act(() => {
      useExecutionOverlay.getState().start(PROMPT_ID, 'chat');
    });
    expect(trees().some((n) => n.getAttribute('data-rootkind') === 'Stack')).toBe(false);

    // Completed with outputs: a results tree appears.
    act(() => {
      useExecutionOverlay.getState().finish(PROMPT_ID, { outputs: { answer: 'hi' } });
    });
    expect(trees().some((n) => n.getAttribute('data-rootkind') === 'Stack')).toBe(true);
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
