import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { generateId } from '@/lib/utils';

export type MessageRole = 'user' | 'assistant' | 'system';
export type MessageStatus = 'pending' | 'streaming' | 'complete' | 'error';

export interface MessageAttachment {
  id: string;
  name: string;
  type: string;
  size: number;
  url?: string;
}

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
  result?: unknown;
  status: 'pending' | 'running' | 'success' | 'error';
  error?: string;
  startedAt?: string;
  completedAt?: string;
}

export interface Message {
  id: string;
  conversationId: string;
  role: MessageRole;
  content: string;
  status: MessageStatus;
  createdAt: string;
  updatedAt?: string;
  toolCalls?: ToolCall[];
  attachments?: MessageAttachment[];
  metadata?: Record<string, unknown>;
}

interface MessagesState {
  messages: Record<string, Message[]>;
  activeConversationId: string | null;

  setActiveConversationId: (id: string | null) => void;
  
  addMessage: (conversationId: string, message: Omit<Message, 'id' | 'createdAt' | 'conversationId'>) => Message;
  updateMessage: (conversationId: string, messageId: string, updates: Partial<Message>) => void;
  removeMessage: (conversationId: string, messageId: string) => void;
  clearMessages: (conversationId: string) => void;
  
  appendContent: (conversationId: string, messageId: string, content: string) => void;
  setMessageStatus: (conversationId: string, messageId: string, status: MessageStatus) => void;
  
  addToolCall: (conversationId: string, messageId: string, toolCall: Omit<ToolCall, 'id'>) => string;
  updateToolCall: (conversationId: string, messageId: string, toolCallId: string, updates: Partial<ToolCall>) => void;
  
  getMessages: (conversationId: string) => Message[];
  getActiveMessages: () => Message[];
  getMessage: (conversationId: string, messageId: string) => Message | undefined;
  getLastMessage: (conversationId: string) => Message | undefined;
  
  hasMessages: (conversationId: string) => boolean;
  getMessageCount: (conversationId: string) => number;
}

export const useMessagesStore = create<MessagesState>()(
  persist(
    (set, get) => ({
      messages: {},
      activeConversationId: null,

      setActiveConversationId: (id) => set({ activeConversationId: id }),

      addMessage: (conversationId, messageData) => {
        const message: Message = {
          ...messageData,
          id: generateId(),
          conversationId,
          createdAt: new Date().toISOString(),
          status: messageData.status || 'complete',
        };

        set((state) => ({
          messages: {
            ...state.messages,
            [conversationId]: [...(state.messages[conversationId] || []), message],
          },
        }));

        return message;
      },

      updateMessage: (conversationId, messageId, updates) => {
        set((state) => ({
          messages: {
            ...state.messages,
            [conversationId]: (state.messages[conversationId] || []).map((msg) =>
              msg.id === messageId
                ? { ...msg, ...updates, updatedAt: new Date().toISOString() }
                : msg
            ),
          },
        }));
      },

      removeMessage: (conversationId, messageId) => {
        set((state) => ({
          messages: {
            ...state.messages,
            [conversationId]: (state.messages[conversationId] || []).filter(
              (msg) => msg.id !== messageId
            ),
          },
        }));
      },

      clearMessages: (conversationId) => {
        set((state) => ({
          messages: {
            ...state.messages,
            [conversationId]: [],
          },
        }));
      },

      appendContent: (conversationId, messageId, content) => {
        set((state) => ({
          messages: {
            ...state.messages,
            [conversationId]: (state.messages[conversationId] || []).map((msg) =>
              msg.id === messageId
                ? { ...msg, content: msg.content + content, updatedAt: new Date().toISOString() }
                : msg
            ),
          },
        }));
      },

      setMessageStatus: (conversationId, messageId, status) => {
        get().updateMessage(conversationId, messageId, { status });
      },

      addToolCall: (conversationId, messageId, toolCallData) => {
        const toolCallId = generateId();
        const toolCall: ToolCall = {
          ...toolCallData,
          id: toolCallId,
          status: toolCallData.status || 'pending',
        };

        set((state) => ({
          messages: {
            ...state.messages,
            [conversationId]: (state.messages[conversationId] || []).map((msg) =>
              msg.id === messageId
                ? {
                    ...msg,
                    toolCalls: [...(msg.toolCalls || []), toolCall],
                    updatedAt: new Date().toISOString(),
                  }
                : msg
            ),
          },
        }));

        return toolCallId;
      },

      updateToolCall: (conversationId, messageId, toolCallId, updates) => {
        set((state) => ({
          messages: {
            ...state.messages,
            [conversationId]: (state.messages[conversationId] || []).map((msg) =>
              msg.id === messageId
                ? {
                    ...msg,
                    toolCalls: msg.toolCalls?.map((tc) =>
                      tc.id === toolCallId ? { ...tc, ...updates } : tc
                    ),
                    updatedAt: new Date().toISOString(),
                  }
                : msg
            ),
          },
        }));
      },

      getMessages: (conversationId) => get().messages[conversationId] || [],

      getActiveMessages: () => {
        const { activeConversationId, messages } = get();
        if (!activeConversationId) return [];
        return messages[activeConversationId] || [];
      },

      getMessage: (conversationId, messageId) =>
        get().messages[conversationId]?.find((msg) => msg.id === messageId),

      getLastMessage: (conversationId) => {
        const msgs = get().messages[conversationId];
        return msgs?.[msgs.length - 1];
      },

      hasMessages: (conversationId) => (get().messages[conversationId]?.length || 0) > 0,

      getMessageCount: (conversationId) => get().messages[conversationId]?.length || 0,
    }),
    {
      name: 'leagent-messages',
      partialize: (state) => ({
        messages: state.messages,
        activeConversationId: state.activeConversationId,
      }),
    }
  )
);
