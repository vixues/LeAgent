import { useQuery, useMutation, useQueryClient, UseQueryOptions } from '@tanstack/react-query';
import { apiClient, ApiError, StreamEventHandler } from '@/api/client';
import { URL_KEYS, QUERY_KEYS, CACHE_TIME } from '../../helpers/constants';
import type { Message, Attachment } from '@/types/chat';

export interface MessageListParams {
  sessionId: string;
  page?: number;
  pageSize?: number;
  before?: string;
  after?: string;
}

export interface MessageListResponse {
  data: Message[];
  total: number;
  hasMore: boolean;
  nextCursor?: string;
  prevCursor?: string;
}

export interface SendMessageInput {
  sessionId: string;
  content: string;
  attachments?: File[];
}

export interface UpdateMessageInput {
  id: string;
  content?: string;
}

export interface StreamMessageInput {
  sessionId: string;
  content: string;
  attachments?: string[];
  onEvent: StreamEventHandler;
  onError?: (error: ApiError) => void;
  onComplete?: () => void;
  signal?: AbortSignal;
}

export const useGetMessagesQuery = (
  params: MessageListParams,
  options?: Omit<UseQueryOptions<MessageListResponse, ApiError>, 'queryKey' | 'queryFn'>
) => {
  return useQuery<MessageListResponse, ApiError>({
    queryKey: [...QUERY_KEYS.SESSION_MESSAGES(params.sessionId), params],
    queryFn: async () => {
      const { sessionId, ...queryParams } = params;
      return apiClient.get<MessageListResponse>(
        URL_KEYS.MESSAGES_BY_SESSION(sessionId),
        queryParams as Record<string, string | number | boolean | undefined>,
      );
    },
    staleTime: CACHE_TIME.STALE_TIME_SHORT,
    enabled: !!params.sessionId,
    ...options,
  });
};

export const useGetMessage = (
  messageId: string,
  options?: Omit<UseQueryOptions<Message, ApiError>, 'queryKey' | 'queryFn'>
) => {
  return useQuery<Message, ApiError>({
    queryKey: QUERY_KEYS.MESSAGE(messageId),
    queryFn: async () => {
      return apiClient.get<Message>(URL_KEYS.MESSAGE_BY_ID(messageId));
    },
    enabled: !!messageId,
    ...options,
  });
};

export const useSendMessage = () => {
  const queryClient = useQueryClient();

  return useMutation<Message, ApiError, SendMessageInput>({
    mutationFn: async ({ sessionId, content, attachments }) => {
      if (attachments && attachments.length > 0) {
        const formData = new FormData();
        formData.append('sessionId', sessionId);
        formData.append('content', content);
        attachments.forEach((file) => {
          formData.append('attachments', file);
        });
        return apiClient.upload<Message>(URL_KEYS.MESSAGES, formData);
      }
      return apiClient.post<Message>(URL_KEYS.MESSAGES, { sessionId, content });
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.SESSION_MESSAGES(variables.sessionId) });
    },
  });
};

export const useUpdateMessage = () => {
  const queryClient = useQueryClient();

  return useMutation<Message, ApiError, UpdateMessageInput>({
    mutationFn: async ({ id, ...data }) => {
      return apiClient.patch<Message>(URL_KEYS.MESSAGE_BY_ID(id), data);
    },
    onSuccess: (data) => {
      queryClient.setQueryData(QUERY_KEYS.MESSAGE(data.id), data);
    },
  });
};

export const useDeleteMessage = () => {
  const queryClient = useQueryClient();

  return useMutation<void, ApiError, { id: string; sessionId: string }>({
    mutationFn: async ({ id }) => {
      await apiClient.delete(URL_KEYS.MESSAGE_BY_ID(id));
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEYS.SESSION_MESSAGES(variables.sessionId) });
      queryClient.removeQueries({ queryKey: QUERY_KEYS.MESSAGE(variables.id) });
    },
  });
};

export const useStreamMessage = () => {
  const queryClient = useQueryClient();

  const streamMessage = async ({
    sessionId,
    content,
    attachments,
    onEvent,
    onError,
    onComplete,
    signal,
  }: StreamMessageInput) => {
    return apiClient.stream({
      url: URL_KEYS.MESSAGE_STREAM,
      method: 'POST',
      body: { sessionId, content, attachments },
      onEvent: (event) => {
        onEvent(event);
        if (event.type === 'done') {
          queryClient.invalidateQueries({ queryKey: QUERY_KEYS.SESSION_MESSAGES(sessionId) });
        }
      },
      onError,
      onComplete,
      signal,
    });
  };

  return { streamMessage };
};

export const addMessageToCache = (
  queryClient: ReturnType<typeof useQueryClient>,
  sessionId: string,
  message: Message
) => {
  queryClient.setQueryData<MessageListResponse>(
    QUERY_KEYS.SESSION_MESSAGES(sessionId),
    (old) => {
      if (!old) {
        return {
          data: [message],
          total: 1,
          hasMore: false,
        };
      }
      return {
        ...old,
        data: [...old.data, message],
        total: old.total + 1,
      };
    }
  );
};

export const updateMessageInCache = (
  queryClient: ReturnType<typeof useQueryClient>,
  sessionId: string,
  messageId: string,
  updates: Partial<Message>
) => {
  queryClient.setQueryData<MessageListResponse>(
    QUERY_KEYS.SESSION_MESSAGES(sessionId),
    (old) => {
      if (!old) return old;
      return {
        ...old,
        data: old.data.map((msg) =>
          msg.id === messageId ? { ...msg, ...updates } : msg
        ),
      };
    }
  );
};

export type { Message, Attachment };
