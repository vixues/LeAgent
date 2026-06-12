import { describe, expect, it } from 'vitest';
import type { Message } from '@/types/chat';
import {
  findLatestTodoAnchorMessageId,
  messageHasTodoActivity,
} from './todoAnchorUtils';

const assistant = (id: string, extra: Partial<Message> = {}): Message => ({
  id,
  role: 'assistant',
  content: '',
  createdAt: '2026-01-01T00:00:00.000Z',
  ...extra,
});

describe('todoAnchorUtils', () => {
  it('detects todo_write tool calls and taskProgress snapshots', () => {
    expect(messageHasTodoActivity(assistant('a1'))).toBe(false);
    expect(
      messageHasTodoActivity(
        assistant('a2', {
          toolCalls: [{ id: 't1', name: 'todo_write', arguments: {}, status: 'success' }],
        }),
      ),
    ).toBe(true);
    expect(
      messageHasTodoActivity(
        assistant('a3', {
          taskProgress: [{ taskId: 'x', label: 'Step', status: 'pending' }],
        }),
      ),
    ).toBe(true);
  });

  it('returns only the latest assistant message with todo activity', () => {
    const messages: Message[] = [
      { id: 'u1', role: 'user', content: 'hi', createdAt: '2026-01-01T00:00:00.000Z' },
      assistant('a1', {
        taskProgress: [{ taskId: 'old', label: 'Old', status: 'completed' }],
      }),
      { id: 'u2', role: 'user', content: 'next', createdAt: '2026-01-01T00:00:01.000Z' },
      assistant('a2', { content: 'plain reply' }),
      { id: 'u3', role: 'user', content: 'plan', createdAt: '2026-01-01T00:00:02.000Z' },
      assistant('a3', {
        toolCalls: [{ id: 't2', name: 'todo_write', arguments: {}, status: 'running' }],
      }),
    ];

    expect(findLatestTodoAnchorMessageId(messages)).toBe('a3');
  });
});
