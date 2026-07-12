import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import type { TFunction } from 'i18next';
import { runChatStream } from '@/lib/runChatStream';
import { useChatStore } from '@/stores/chat';

const t = ((key: string) => key) as TFunction;

describe('runChatStream checkpoint_id', () => {
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

  it('appends checkpoint_id to FormData when resuming', async () => {
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
      content: 'Continue',
      checkpointId: 'cp-resume-99',
      signal: controller.signal,
      t,
    });

    expect(captured).not.toBeNull();
    expect(captured!.get('checkpoint_id')).toBe('cp-resume-99');
    expect(captured!.get('message')).toBe('Continue');
  });
});
