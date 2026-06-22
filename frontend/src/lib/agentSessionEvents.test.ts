import { describe, expect, it } from 'vitest';
import {
  collectAgentSessionEvents,
  collectTerminalEvents,
  collectTouchedFiles,
  summarizeSessionEvents,
} from './agentSessionEvents';
import type { Message } from '@/types/chat';

function assistant(toolCalls: Message['toolCalls']): Message {
  return {
    id: `m-${Math.random().toString(36).slice(2)}`,
    role: 'assistant',
    content: '',
    createdAt: '',
    toolCalls,
  };
}

describe('collectAgentSessionEvents', () => {
  it('maps project_read to a read event with code body', () => {
    const messages: Message[] = [
      assistant([
        {
          id: 'tc1',
          name: 'project_read',
          arguments: { path: 'src/app.py' },
          status: 'success',
          result: 'print("hi")',
        },
      ]),
    ];
    const events = collectAgentSessionEvents(messages);
    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({
      kind: 'read',
      path: 'src/app.py',
      language: 'python',
      code: 'print("hi")',
      status: 'success',
    });
  });

  it('maps project_edit to a diff event', () => {
    const messages: Message[] = [
      assistant([
        {
          id: 'tc1',
          name: 'project_edit',
          arguments: { path: 'a.ts', old_string: 'old', new_string: 'new' },
          status: 'success',
        },
      ]),
    ];
    const [event] = collectAgentSessionEvents(messages);
    expect(event?.kind).toBe('edit');
    expect(event?.diff).toEqual({ before: 'old', after: 'new' });
  });

  it('captures code_execution source, stdio, and images', () => {
    const messages: Message[] = [
      assistant([
        {
          id: 'tc1',
          name: 'code_execution',
          arguments: { source: 'x = 1' },
          status: 'success',
          result: {
            status: 'ok',
            stdout: 'done\n',
            stderr: '',
            artifact_id: 'abc12345',
            managed_artifacts: [
              {
                id: 'img1',
                content_type: 'image/png',
                preview_url: '/api/v1/files/img1/preview',
              },
            ],
          },
        },
      ]),
    ];
    const [event] = collectAgentSessionEvents(messages);
    expect(event?.kind).toBe('code_exec');
    expect(event?.code).toBe('x = 1');
    expect(event?.stdout).toBe('done\n');
    expect(event?.artifactId).toBe('abc12345');
    expect(event?.images).toHaveLength(1);
  });

  it('extracts streaming write content from argumentsRaw', () => {
    const messages: Message[] = [
      assistant([
        {
          id: 'tc1',
          name: 'project_write',
          arguments: {},
          argumentsRaw: '{"path":"b.txt","content":"hello',
          status: 'running',
        },
      ]),
    ];
    const [event] = collectAgentSessionEvents(messages);
    expect(event?.kind).toBe('write');
    expect(event?.streaming).toBe(true);
    expect(event?.code).toBe('hello');
  });

  it('appends a live nested-agent preview event last', () => {
    const messages: Message[] = [
      assistant([
        { id: 'tc1', name: 'project_read', arguments: { path: 'x' }, status: 'success' },
      ]),
    ];
    const events = collectAgentSessionEvents(messages, [], {
      parentToolCallId: 'p1',
      toolName: 'project_write',
      argumentsRaw: '{"content":"streamed',
      argumentsPartial: { path: 'nested.py' },
    });
    const last = events[events.length - 1];
    expect(last?.kind).toBe('nested_agent');
    expect(last?.streaming).toBe(true);
    expect(last?.code).toBe('streamed');
  });

  it('skips unmapped project tools', () => {
    const messages: Message[] = [
      assistant([
        { id: 'tc1', name: 'project_grep', arguments: { pattern: 'x' }, status: 'success' },
      ]),
    ];
    expect(collectAgentSessionEvents(messages)).toHaveLength(0);
  });
});

describe('summarizeSessionEvents', () => {
  it('counts files, reads, executions, and errors', () => {
    const messages: Message[] = [
      assistant([
        { id: 'r', name: 'project_read', arguments: { path: 'a.py' }, status: 'success' },
        {
          id: 'w',
          name: 'project_write',
          arguments: { path: 'b.py', content: 'x' },
          status: 'success',
        },
        {
          id: 'x',
          name: 'code_execution',
          arguments: { source: 'y' },
          status: 'error',
          result: { status: 'error', stderr: 'boom' },
        },
      ]),
    ];
    const summary = summarizeSessionEvents(collectAgentSessionEvents(messages));
    expect(summary.fileCount).toBe(1);
    expect(summary.readCount).toBe(1);
    expect(summary.execCount).toBe(1);
    expect(summary.errorCount).toBe(1);
  });
});

describe('collectTouchedFiles', () => {
  it('returns one entry per path with the latest operation', () => {
    const messages: Message[] = [
      assistant([
        { id: 'w', name: 'project_write', arguments: { path: 'a.py', content: '1' }, status: 'success' },
      ]),
      assistant([
        {
          id: 'e',
          name: 'project_edit',
          arguments: { path: 'a.py', old_string: '1', new_string: '2' },
          status: 'success',
        },
      ]),
    ];
    const touched = collectTouchedFiles(collectAgentSessionEvents(messages));
    expect(touched).toHaveLength(1);
    expect(touched[0]?.kind).toBe('edit');
  });
});

describe('collectTerminalEvents', () => {
  it('includes shell and code_exec events', () => {
    const messages: Message[] = [
      assistant([
        {
          id: 's',
          name: 'project_shell',
          arguments: { command: 'ls' },
          status: 'success',
          result: { stdout: 'a\nb\n', stderr: '' },
        },
        { id: 'r', name: 'project_read', arguments: { path: 'a' }, status: 'success' },
      ]),
    ];
    const terminal = collectTerminalEvents(collectAgentSessionEvents(messages));
    expect(terminal).toHaveLength(1);
    expect(terminal[0]?.kind).toBe('shell');
  });
});
