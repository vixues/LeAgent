import { render, screen } from '@testing-library/react';
import { ReactFlowProvider, type NodeProps } from '@xyflow/react';
import { beforeEach, describe, expect, it } from 'vitest';
import type { FlowNode } from '@/stores/flow';
import { useExecutionOverlay } from '@/features/workflow/store/executionOverlay';
import { ChatWorkflowMiniNode } from './ChatWorkflowMiniNode';
import { ChatWorkflowRunPromptContext } from './chatWorkflowRunContext';

const PROMPT_ID = 'chat-embed-test';

function renderNode(nodeId: string, promptId: string | null) {
  const props = {
    id: nodeId,
    data: { label: 'Generate', category: 'image' },
  } as unknown as NodeProps<FlowNode>;
  return render(
    <ReactFlowProvider>
      <ChatWorkflowRunPromptContext.Provider value={promptId}>
        <ChatWorkflowMiniNode {...props} />
      </ChatWorkflowRunPromptContext.Provider>
    </ReactFlowProvider>,
  );
}

describe('ChatWorkflowMiniNode live status', () => {
  beforeEach(() => {
    useExecutionOverlay.getState().reset();
  });

  it('renders no status data attribute without an active run', () => {
    renderNode('n1', null);
    expect(screen.getByText('Generate')).toBeTruthy();
    expect(document.querySelector('[data-run-status]')).toBeNull();
  });

  it('reflects the running status from the execution overlay', () => {
    useExecutionOverlay.getState().start(PROMPT_ID, 'chat');
    useExecutionOverlay.getState().setNode(PROMPT_ID, 'n1', { status: 'running' });
    renderNode('n1', PROMPT_ID);
    expect(document.querySelector('[data-run-status="running"]')).not.toBeNull();
  });

  it('reflects the success status from the execution overlay', () => {
    useExecutionOverlay.getState().start(PROMPT_ID, 'chat');
    useExecutionOverlay.getState().setNode(PROMPT_ID, 'n2', { status: 'success' });
    renderNode('n2', PROMPT_ID);
    expect(document.querySelector('[data-run-status="success"]')).not.toBeNull();
  });
});
