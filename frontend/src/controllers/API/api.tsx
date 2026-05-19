import axios, {
  AxiosError,
  AxiosInstance,
  AxiosRequestConfig,
  AxiosResponse,
  InternalAxiosRequestConfig,
} from 'axios';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

export interface ApiError {
  message: string;
  code?: string;
  status?: number;
  details?: Record<string, unknown>;
}

export interface StreamEvent {
  type: 'content' | 'tool_call' | 'tool_result' | 'error' | 'done' | 'metadata';
  data: unknown;
}

export type StreamEventHandler = (event: StreamEvent) => void;

const createAxiosInstance = (): AxiosInstance => {
  const instance = axios.create({
    baseURL: BASE_URL,
    timeout: 30000,
    headers: {
      'Content-Type': 'application/json',
    },
    withCredentials: true,
  });

  instance.interceptors.request.use(
    (config: InternalAxiosRequestConfig) => config,
    (error: AxiosError) => Promise.reject(error)
  );

  instance.interceptors.response.use(
    (response: AxiosResponse) => response,
    (error: AxiosError<ApiError>) => {
      const apiError: ApiError = {
        message: error.response?.data?.message || error.message || 'An unexpected error occurred',
        code: error.response?.data?.code || error.code,
        status: error.response?.status,
        details: error.response?.data?.details,
      };
      return Promise.reject(apiError);
    }
  );

  return instance;
};

export const api = createAxiosInstance();

export function setAuthTokens(_accessToken: string, _refreshToken?: string) {}
export function clearAuthTokens() {}
export function getAccessToken(): string | null {
  return null;
}

export interface StreamingRequestOptions {
  url: string;
  method?: 'GET' | 'POST';
  body?: Record<string, unknown>;
  params?: Record<string, string | number | boolean>;
  onEvent: StreamEventHandler;
  onError?: (error: ApiError) => void;
  onComplete?: () => void;
  signal?: AbortSignal;
}

export const performStreamingRequest = async ({
  url,
  method = 'POST',
  body,
  params,
  onEvent,
  onError,
  onComplete,
  signal,
}: StreamingRequestOptions): Promise<void> => {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
  };

  let fullUrl = `${BASE_URL}${url}`;
  if (params) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        searchParams.append(key, String(value));
      }
    });
    const queryString = searchParams.toString();
    if (queryString) {
      fullUrl += `?${queryString}`;
    }
  }

  try {
    const response = await fetch(fullUrl, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      signal,
      credentials: 'include',
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const apiError: ApiError = {
        message: errorData.message || `HTTP error ${response.status}`,
        status: response.status,
        code: errorData.code,
        details: errorData.details,
      };
      onError?.(apiError);
      return;
    }

    if (!response.body) {
      onError?.({ message: 'Response body is empty' });
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();

      if (done) {
        if (buffer.trim()) {
          parseSSEBuffer(buffer, onEvent);
        }
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.trim()) {
          parseSSEBuffer(line, onEvent);
        }
      }
    }

    onComplete?.();
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      return;
    }
    const apiError: ApiError = {
      message: error instanceof Error ? error.message : 'Streaming request failed',
    };
    onError?.(apiError);
  }
};

const parseSSEBuffer = (buffer: string, onEvent: StreamEventHandler) => {
  const lines = buffer.split('\n');
  let eventType = 'message';
  let data = '';

  for (const line of lines) {
    if (line.startsWith('event:')) {
      eventType = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      data += line.slice(5).trim();
    }
  }

  if (data) {
    try {
      const parsedData = JSON.parse(data);
      onEvent({
        type: eventType as StreamEvent['type'],
        data: parsedData,
      });
    } catch {
      onEvent({
        type: eventType as StreamEvent['type'],
        data,
      });
    }
  }
};

export type { AxiosInstance, AxiosRequestConfig, AxiosResponse, AxiosError };
