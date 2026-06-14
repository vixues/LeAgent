import { describe, expect, it } from 'vitest';

import { useExecutionSessionStore } from './executionSession';

describe('executionSession store', () => {
  it('records execution_started entries', () => {
    useExecutionSessionStore.getState().clearSession('sess-1');
    useExecutionSessionStore.getState().upsertFromStarted('sess-1', {
      runId: 'run-a',
      scope: 'chat_turn',
    });
    const entry = useExecutionSessionStore.getState().bySession['sess-1'];
    expect(entry?.runId).toBe('run-a');
    expect(entry?.scope).toBe('chat_turn');
    expect(entry?.status).toBe('running');
  });

  it('tracks workflow promptId on session entry', () => {
    useExecutionSessionStore.getState().clearSession('sess-2');
    useExecutionSessionStore.getState().upsertFromStarted('sess-2', {
      runId: 'run-w',
      scope: 'workflow',
      parentRunId: 'run-a',
    });
    useExecutionSessionStore.getState().setPromptId('sess-2', 'prompt-123');
    const entry = useExecutionSessionStore.getState().bySession['sess-2'];
    expect(entry?.promptId).toBe('prompt-123');
    expect(entry?.parentRunId).toBe('run-a');
  });

  it('appends capability log entries', () => {
    useExecutionSessionStore.getState().clearSession('sess-3');
    useExecutionSessionStore.getState().upsertFromStarted('sess-3', {
      runId: 'run-c',
      scope: 'chat_turn',
    });
    useExecutionSessionStore.getState().appendCapability('sess-3', {
      id: 'cap-1',
      toolCallId: 'tc-1',
      name: 'todo_write',
      status: 'success',
      timestamp: new Date().toISOString(),
    });
    const log = useExecutionSessionStore.getState().bySession['sess-3']?.capabilityLog;
    expect(log).toHaveLength(1);
    expect(log?.[0]?.name).toBe('todo_write');
  });

  it('remaps session ids preserving execution state', () => {
    useExecutionSessionStore.getState().clearSession('temp-1');
    useExecutionSessionStore.getState().clearSession('real-1');
    useExecutionSessionStore.getState().upsertFromStarted('temp-1', {
      runId: 'run-temp',
      scope: 'chat_turn',
    });
    useExecutionSessionStore.getState().remapSession('temp-1', 'real-1');
    expect(useExecutionSessionStore.getState().bySession['temp-1']).toBeUndefined();
    expect(useExecutionSessionStore.getState().bySession['real-1']?.runId).toBe('run-temp');
  });

  it('setPauseToken marks execution blocked', () => {
    useExecutionSessionStore.getState().clearSession('sess-block');
    useExecutionSessionStore.getState().upsertFromStarted('sess-block', {
      runId: 'run-block',
      scope: 'chat_turn',
    });
    useExecutionSessionStore.getState().setPauseToken('sess-block', {
      scope: 'chat_turn',
      checkpoint_id: 'cp-1',
    });
    const entry = useExecutionSessionStore.getState().bySession['sess-block'];
    expect(entry?.status).toBe('blocked');
    expect(entry?.pauseToken).toEqual({ scope: 'chat_turn', checkpoint_id: 'cp-1' });
  });
});
