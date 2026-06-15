import { describe, expect, it } from 'vitest';
import type { ChatWorkflowStepModel, ChatWorkflowStepRunRecord, TaskProgressStep } from '@/types/chat';
import { mergeWorkflowIntoTodos, resolveWorkflowRunTodoStatus } from './workflowTodoSync';

const steps: ChatWorkflowStepModel[] = [
  { id: 'fetch', label: 'Fetch page', action: { kind: 'tool', tool_id: 'web_fetch', arguments: {} } },
  { id: 'analyze', label: 'Analyze', action: { kind: 'tool', tool_id: 'analyze', arguments: {} } },
];

const todos: TaskProgressStep[] = [
  { taskId: 't1', label: 'Fetch page', status: 'in_progress', order: 0 },
  { taskId: 't2', label: 'Analyze', status: 'pending', order: 1 },
];

describe('resolveWorkflowRunTodoStatus', () => {
  it('maps terminal HTTP statuses', () => {
    expect(resolveWorkflowRunTodoStatus({ status: 'success' })).toBe('completed');
    expect(resolveWorkflowRunTodoStatus({ status: 'error', error: 'boom' })).toBe('failed');
    expect(resolveWorkflowRunTodoStatus({ status: 'running' })).toBe('in_progress');
  });

  it('treats finished overlay as completed while step run is still running', () => {
    const run: ChatWorkflowStepRunRecord = {
      status: 'running',
      prompt_id: 'prompt-1',
    };
    const getOverlay = () => ({ running: false, blocked: null, errors: [] });
    expect(resolveWorkflowRunTodoStatus(run, getOverlay)).toBe('completed');
  });

  it('treats overlay errors as failed', () => {
    const run: ChatWorkflowStepRunRecord = {
      status: 'running',
      prompt_id: 'prompt-1',
    };
    const getOverlay = () => ({ running: false, blocked: null, errors: ['node failed'] });
    expect(resolveWorkflowRunTodoStatus(run, getOverlay)).toBe('failed');
  });
});

describe('mergeWorkflowIntoTodos', () => {
  it('maps workflow runs onto todos by step index when ids differ', () => {
    const stepRuns: Record<string, ChatWorkflowStepRunRecord> = {
      fetch: { status: 'success' },
      analyze: { status: 'running' },
    };
    const merged = mergeWorkflowIntoTodos(steps, stepRuns, todos);
    expect(merged[0]?.status).toBe('completed');
    expect(merged[1]?.status).toBe('in_progress');
  });

  it('does not downgrade todo status', () => {
    const completedTodos: TaskProgressStep[] = [
      { taskId: 'fetch', label: 'Fetch page', status: 'completed', order: 0 },
    ];
    const stepRuns: Record<string, ChatWorkflowStepRunRecord> = {
      fetch: { status: 'running' },
    };
    const merged = mergeWorkflowIntoTodos(steps.slice(0, 1), stepRuns, completedTodos);
    expect(merged[0]?.status).toBe('completed');
  });
});
