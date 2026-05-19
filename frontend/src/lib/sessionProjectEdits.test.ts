import { describe, expect, it } from 'vitest';
import { collectSessionEditPaths } from './sessionProjectEdits';
import type { Message } from '@/types/chat';

describe('collectSessionEditPaths', () => {
  it('dedupes paths from project_edit and project_apply_patch', () => {
    const messages: Message[] = [
      {
        id: 'm1',
        role: 'assistant',
        content: '',
        createdAt: new Date().toISOString(),
        toolCalls: [
          {
            id: '1',
            name: 'project_edit',
            arguments: { path: 'src/a.ts', old_string: 'x', new_string: 'y' },
            status: 'success',
          },
          {
            id: '2',
            name: 'project_apply_patch',
            arguments: { diff: '--- a/src/a.ts\n+++ b/src/a.ts\n' },
            status: 'success',
          },
        ],
      },
    ];
    const rows = collectSessionEditPaths(messages);
    expect(rows.map((r) => r.path)).toEqual(['src/a.ts']);
  });
});
