import { beforeEach, describe, expect, it } from 'vitest';
import { parseWorkflowEmbedFromExtensions } from '@/types/chat';
import { useChatStore } from '@/stores/chat';

const SESSION_ID = '00000000-0000-4000-8000-000000000099';
const DIGEST = 'b'.repeat(64);

describe('parseWorkflowEmbedFromExtensions run state', () => {
  it('hydrates a terminal run record', () => {
    const ext = {
      workflow_embed: { data: { nodes: {} }, digest: DIGEST },
      workflow_embed_run: { status: 'success', prompt_id: 'p1', run_id: 'r1' },
    };
    const embed = parseWorkflowEmbedFromExtensions(ext);
    expect(embed?.run?.status).toBe('success');
    expect(embed?.run?.promptId).toBe('p1');
    expect(embed?.run?.runId).toBe('r1');
  });

  it('downgrades a stale running record to idle on reload', () => {
    const ext = {
      workflow_embed: { data: { nodes: {} }, digest: DIGEST },
      workflow_embed_run: { status: 'running', prompt_id: 'p1' },
    };
    const embed = parseWorkflowEmbedFromExtensions(ext);
    expect(embed?.run?.status).toBe('idle');
  });

  it('keeps a stale running record with an error as error', () => {
    const ext = {
      workflow_embed: { data: { nodes: {} }, digest: DIGEST },
      workflow_embed_run: { status: 'running', error: 'boom' },
    };
    const embed = parseWorkflowEmbedFromExtensions(ext);
    expect(embed?.run?.status).toBe('error');
    expect(embed?.run?.error).toBe('boom');
  });
});

describe('updateWorkflowEmbedRun store action', () => {
  beforeEach(() => {
    useChatStore.setState({
      messages: {
        [SESSION_ID]: [
          {
            id: 'm1',
            role: 'assistant',
            content: '',
            createdAt: new Date(0).toISOString(),
            workflowEmbed: { data: { nodes: {} }, digest: DIGEST },
          },
        ],
      },
    });
  });

  it('patches embed run state in place', () => {
    useChatStore.getState().updateWorkflowEmbedRun(SESSION_ID, 'm1', {
      status: 'running',
      promptId: 'p9',
    });
    const run = useChatStore.getState().messages[SESSION_ID]?.[0]?.workflowEmbed?.run;
    expect(run).toEqual({ status: 'running', promptId: 'p9' });
  });

  it('is a no-op when the message has no embed', () => {
    useChatStore.getState().updateWorkflowEmbedRun(SESSION_ID, 'missing', { status: 'success' });
    const run = useChatStore.getState().messages[SESSION_ID]?.[0]?.workflowEmbed?.run;
    expect(run).toBeUndefined();
  });
});
