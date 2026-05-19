import { describe, expect, it } from 'vitest';
import { collectAgentTerminalLogs } from './agentTerminalLogs';
import type { Message } from '@/types/chat';

describe('collectAgentTerminalLogs', () => {
  it('collects project_shell stdout/stderr', () => {
    const messages: Message[] = [
      {
        id: 'a1',
        role: 'assistant',
        content: '',
        createdAt: '',
        toolCalls: [
          {
            id: 'tc1',
            name: 'project_shell',
            arguments: {},
            status: 'success',
            result: {
              stdout: 'hello\n',
              stderr: '',
              returncode: 0,
            },
          },
        ],
      },
    ];
    const logs = collectAgentTerminalLogs(messages);
    expect(logs).toHaveLength(1);
    expect(logs[0]?.stdout).toBe('hello\n');
  });

  it('skips tools without stdout/stderr keys', () => {
    const messages: Message[] = [
      {
        id: 'a1',
        role: 'assistant',
        content: '',
        createdAt: '',
        toolCalls: [
          {
            id: 'tc1',
            name: 'project_read',
            arguments: {},
            status: 'success',
            result: { path: '/x', content: 'z' },
          },
        ],
      },
    ];
    expect(collectAgentTerminalLogs(messages)).toHaveLength(0);
  });
});
