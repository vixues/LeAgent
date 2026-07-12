import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import type { TFunction } from 'i18next';
import { runChatStream } from '@/lib/runChatStream';
import { useChatStore } from '@/stores/chat';

const t = ((key: string) => key) as TFunction;

describe('runChatStream project folder_id', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    useChatStore.setState({
      lastTerminalReason: null,
      lastCheckpointId: null,
      messages: { 'sess-1': [] },
    });
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('appends folder_id to FormData when provided', async () => {
    let captured: FormData | null = null;
    globalThis.fetch = vi.fn(async (_url, init) => {
      captured = init?.body as FormData;
      return new Response('data: {"type":"complete","data":{"text":"done"}}\n\n', {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
      });
    }) as typeof fetch;

    const controller = new AbortController();
    await runChatStream({
      sessionId: 'sess-1',
      userMessageId: 'u1',
      assistantMsgId: 'a1',
      content: 'hello',
      projectId: 'proj-1',
      folderId: 'folder-shared-99',
      signal: controller.signal,
      t,
    });

    expect(captured).not.toBeNull();
    expect(captured!.get('folder_id')).toBe('folder-shared-99');
    expect(captured!.get('project_id')).toBe('proj-1');
  });
});
