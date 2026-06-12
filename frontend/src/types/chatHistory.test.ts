import { describe, expect, it } from 'vitest';
import {
  ensureChronologicalMessages,
  normalizeMessageList,
  normalizeToolCallList,
  type MessageResponse,
} from './chatHistory';
import type { Message } from '@/types/chat';

describe('chat history normalization', () => {
  it('parses JSON-string tool calls', () => {
    const calls = normalizeToolCallList(
      JSON.stringify([
        {
          id: 'call-1',
          name: 'excel_generator',
          arguments: { sheet_name: 'contacts' },
          status: 'success',
        },
      ]),
    );

    expect(calls).toEqual([
      {
        id: 'call-1',
        name: 'excel_generator',
        arguments: { sheet_name: 'contacts' },
        result: undefined,
        status: 'success',
        error: undefined,
        duration_ms: undefined,
      },
    ]);
  });

  it('merges tool result rows into the previous assistant tool call', () => {
    const rows: MessageResponse[] = [
      {
        id: 'assistant-1',
        role: 'assistant',
        content: 'Done',
        created_at: '2026-04-28T00:00:00.000Z',
        tool_calls: [
          {
            id: 'call-1',
            name: 'excel_generator',
            arguments: {},
            status: 'running',
          },
        ],
      },
      {
        id: 'tool-1',
        role: 'tool',
        content: '{"success":true,"output_path":"/tmp/out.xlsx"}',
        tool_call_id: 'call-1',
        created_at: '2026-04-28T00:00:01.000Z',
      },
    ];

    const messages = normalizeMessageList(rows);

    expect(messages).toHaveLength(1);
    expect(messages[0]?.toolCalls?.[0]).toMatchObject({
      id: 'call-1',
      status: 'success',
      result: { success: true, output_path: '/tmp/out.xlsx' },
    });
  });

  it('does not render unmatched internal tool rows as chat prose', () => {
    const messages = normalizeMessageList([
      {
        id: 'tool-1',
        role: 'tool',
        content: '{"success":true}',
        tool_call_id: 'missing-call',
        created_at: '2026-04-28T00:00:00.000Z',
      },
    ]);

    expect(messages).toEqual([]);
  });

  it('loads chat_workflow_step_runs from extensions into workflow.stepRuns', () => {
    const digest = 'a'.repeat(40);
    const messages = normalizeMessageList([
      {
        id: 'wf-1',
        role: 'assistant',
        content: 'Run steps below',
        extensions: {
          chat_workflow: {
            version: 1 as const,
            title: 'Demo',
            steps: [
              {
                id: 'step-a',
                label: 'First',
                action: { kind: 'tool' as const, tool_id: 'noop', arguments: {} },
              },
            ],
          },
          chat_workflow_digest: digest,
          chat_workflow_step_runs: {
            'step-a': { status: 'success' },
          },
        },
        created_at: '2026-04-28T00:00:00.000Z',
      },
    ]);

    expect(messages[0]?.workflow?.stepRuns['step-a']?.status).toBe('success');
  });

  it('maps persisted extensions (thinking, task_progress, gen_ui) onto Message', () => {
    const ext = {
      thinking: 'Planning step…',
      task_progress: [
        { task_id: 't1', label: 'Fetch data', status: 'completed', order: 0 },
      ],
      gen_ui: {
        tree: { schemaVersion: '1' as const, root: { nodeId: 'r', kind: 'Stack', children: [] } },
        tool_call_id: 'tc-ui',
        canvas_id: 'cv-1',
      },
    };
    const messages = normalizeMessageList([
      {
        id: 'asst-1',
        role: 'assistant',
        content: 'Hello',
        extensions: ext,
        created_at: '2026-04-28T00:00:00.000Z',
      },
    ]);

    expect(messages[0]?.thinking).toBe('Planning step…');
    expect(messages[0]?.taskProgress?.[0]).toMatchObject({
      taskId: 't1',
      label: 'Fetch data',
      status: 'completed',
      order: 0,
    });
    expect(messages[0]?.genUiReplay?.tool_call_id).toBe('tc-ui');
    expect(messages[0]?.genUiReplay?.tree.schemaVersion).toBe('1');
  });

  it('maps input/output token columns onto assistant Message.usage', () => {
    const messages = normalizeMessageList([
      {
        id: 'asst-1',
        role: 'assistant',
        content: 'Hello',
        created_at: '2026-04-28T00:00:00.000Z',
        input_tokens: 1200,
        output_tokens: 80,
        total_tokens: 1280,
      },
    ]);

    expect(messages[0]?.usage).toEqual({
      prompt_tokens: 1200,
      completion_tokens: 80,
      total_tokens: 1280,
    });
  });

  it('sorts and correctly merges tool results when rows arrive out of order', () => {
    const rows: MessageResponse[] = [
      {
        id: 'tool-1',
        role: 'tool',
        content: '{"success":true}',
        tool_call_id: 'call-1',
        created_at: '2026-04-28T00:00:02.000Z',
      },
      {
        id: 'assistant-1',
        role: 'assistant',
        content: 'Working…',
        tool_calls: [{ id: 'call-1', name: 'search', arguments: {}, status: 'running' }],
        created_at: '2026-04-28T00:00:01.000Z',
      },
      {
        id: 'user-1',
        role: 'user',
        content: 'Hello',
        created_at: '2026-04-28T00:00:00.000Z',
      },
    ];

    const messages = normalizeMessageList(rows);

    expect(messages).toHaveLength(2);
    expect(messages[0]?.role).toBe('user');
    expect(messages[1]?.role).toBe('assistant');
    expect(messages[1]?.toolCalls?.[0]).toMatchObject({
      id: 'call-1',
      status: 'success',
      result: { success: true },
    });
  });

  it('produces stable order for out-of-order rows with same timestamps', () => {
    const ts = '2026-04-28T00:00:00.000Z';
    const rowsA: MessageResponse[] = [
      { id: 'user-1', role: 'user', content: 'Q', created_at: ts },
      { id: 'asst-1', role: 'assistant', content: 'Earlier', created_at: '2026-04-28T00:00:01.000Z' },
      { id: 'asst-2', role: 'assistant', content: 'Later', created_at: ts },
    ];
    const rowsB: MessageResponse[] = [
      { id: 'asst-2', role: 'assistant', content: 'Later', created_at: ts },
      { id: 'asst-1', role: 'assistant', content: 'Earlier', created_at: '2026-04-28T00:00:01.000Z' },
      { id: 'user-1', role: 'user', content: 'Q', created_at: ts },
    ];

    const m1 = normalizeMessageList(rowsA);
    const m2 = normalizeMessageList(rowsB);

    expect(m1.map((m) => m.id)).toEqual(m2.map((m) => m.id));
  });

  it('sorts Message rows by createdAt then id', () => {
    const ts = '2026-04-28T00:00:00.000Z';
    const rows: Message[] = [
      { id: 'b-asst', role: 'assistant', content: 'A', createdAt: ts },
      { id: 'a-user', role: 'user', content: 'Q', createdAt: ts },
      { id: 'c-asst', role: 'assistant', content: 'Later', createdAt: '2026-04-28T00:00:01.000Z' },
    ];
    expect(ensureChronologicalMessages(rows).map((m) => m.id)).toEqual([
      'a-user',
      'b-asst',
      'c-asst',
    ]);
  });

  it('parses attachment JSON strings on reopened user messages', () => {
    const messages = normalizeMessageList([
      {
        id: 'user-1',
        role: 'user',
        content: '介绍一下内容',
        attachments:
          '[{"id":"att-1","filename":"国家实验室联系人.pdf","content_type":"application/pdf","size":1234}]',
        created_at: '2026-04-28T00:00:00.000Z',
      },
    ]);

    expect(messages[0]?.attachments).toEqual([
      {
        id: 'att-1',
        name: '国家实验室联系人.pdf',
        type: 'application/pdf',
        size: 1234,
        kind: undefined,
        previewUrl: undefined,
        downloadUrl: undefined,
        url: undefined,
      },
    ]);
  });
});
