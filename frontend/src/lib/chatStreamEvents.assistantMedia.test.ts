import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { TFunction } from 'i18next';
import type { ChatSession, Message } from '@/types/chat';
import { useChatStore } from '@/stores/chat';
import { applyChatStreamEvent } from '@/lib/chatStreamEvents';

vi.mock('@/api/client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  HttpError: class HttpError extends Error {},
}));

const SESSION_ID = '00000000-0000-4000-8000-000000000abc';
const ASSISTANT_ID = 'assistant-1';

const t = ((k: string) => k) as unknown as TFunction;

const session: ChatSession = {
  id: SESSION_ID,
  title: 'S',
  createdAt: new Date(0).toISOString(),
  updatedAt: new Date(0).toISOString(),
  messageCount: 0,
  pinnedMessageIds: [],
};

const assistant: Message = {
  id: ASSISTANT_ID,
  role: 'assistant',
  content: 'here is your image',
  createdAt: new Date(0).toISOString(),
};

describe('applyChatStreamEvent assistant_media', () => {
  beforeEach(() => {
    useChatStore.setState({
      sessions: [session],
      currentSessionId: SESSION_ID,
      messages: { [SESSION_ID]: [assistant] },
    });
  });

  it('populates inlineMedia and the native flag on the assistant message', () => {
    applyChatStreamEvent(
      {
        type: 'assistant_media',
        data: {
          native: true,
          attachments: [
            { id: 'img-1', filename: 'out.png', kind: 'image', preview_url: '/api/v1/files/img-1/preview' },
          ],
        },
      },
      { sessionId: SESSION_ID, assistantMsgId: ASSISTANT_ID, userMessageId: 'u1', t },
    );

    const msg = useChatStore.getState().messages[SESSION_ID]?.find((m) => m.id === ASSISTANT_ID);
    expect(msg?.inlineMedia).toHaveLength(1);
    expect(msg?.inlineMedia?.[0]?.id).toBe('img-1');
    expect(msg?.nativeMedia).toBe(true);
  });

  it('dedupes inline media by id across multiple events', () => {
    const evt = {
      type: 'assistant_media',
      data: {
        attachments: [{ id: 'img-1', filename: 'out.png', kind: 'image' }],
      },
    };
    const params = { sessionId: SESSION_ID, assistantMsgId: ASSISTANT_ID, userMessageId: 'u1', t };
    applyChatStreamEvent(evt, params);
    applyChatStreamEvent(evt, params);

    const msg = useChatStore.getState().messages[SESSION_ID]?.find((m) => m.id === ASSISTANT_ID);
    expect(msg?.inlineMedia).toHaveLength(1);
  });

  it('ignores events with no renderable attachments', () => {
    applyChatStreamEvent(
      { type: 'assistant_media', data: { attachments: [] } },
      { sessionId: SESSION_ID, assistantMsgId: ASSISTANT_ID, userMessageId: 'u1', t },
    );
    const msg = useChatStore.getState().messages[SESSION_ID]?.find((m) => m.id === ASSISTANT_ID);
    expect(msg?.inlineMedia).toBeUndefined();
  });
});
