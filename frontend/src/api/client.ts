import { getMachineFingerprint } from '@/lib/machineFingerprint';

import { formatHttpErrorDetail } from './formatApiError';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

export interface ApiError {
  message: string;
  code?: string;
  status?: number;
  details?: Record<string, unknown>;
}

/** Thrown by {@link ApiClient} on non-OK HTTP responses (includes `status` for callers). */
export class HttpError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'HttpError';
    this.status = status;
  }
}

export interface StreamEvent {
  type: 'content' | 'tool_call' | 'tool_result' | 'error' | 'done' | 'metadata';
  data: unknown;
}

export type StreamEventHandler = (event: StreamEvent) => void;

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

interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined>;
  timeoutMs?: number;
  /** Omit credentials for unauthenticated endpoints (e.g. ``GET /meta``). */
  skipAuth?: boolean;
}

function createTimeoutSignal(ms: number): AbortSignal {
  if (typeof AbortSignal !== 'undefined' && typeof AbortSignal.timeout === 'function') {
    return AbortSignal.timeout(ms);
  }
  const c = new AbortController();
  window.setTimeout(() => c.abort(), ms);
  return c.signal;
}

function combineAbortSignals(a?: AbortSignal, b?: AbortSignal): AbortSignal | undefined {
  if (!a && !b) return undefined;
  if (!a) return b;
  if (!b) return a;
  const c = new AbortController();
  if (a.aborted || b.aborted) {
    c.abort();
    return c.signal;
  }
  const forward = () => {
    c.abort();
  };
  a.addEventListener('abort', forward);
  b.addEventListener('abort', forward);
  return c.signal;
}

function parseSSEBuffer(buffer: string, onEvent: StreamEventHandler) {
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
      onEvent({ type: eventType as StreamEvent['type'], data: parsedData });
    } catch {
      onEvent({ type: eventType as StreamEvent['type'], data });
    }
  }
}

function appendFingerprint(headers: Record<string, string>) {
  try {
    const fp = getMachineFingerprint();
    if (fp.length >= 8) {
      headers['x-leagent-machine-fingerprint'] = fp;
    }
  } catch {
    /* ignore */
  }
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private buildUrl(endpoint: string, params?: Record<string, string | number | boolean | undefined>): string {
    const url = new URL(`${this.baseUrl}${endpoint}`, window.location.origin);
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined) {
          url.searchParams.append(key, String(value));
        }
      });
    }
    return url.toString();
  }

  private async request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const { params, timeoutMs, skipAuth, ...fetchOptions } = options;
    const url = this.buildUrl(endpoint, params);

    const timeoutSignal = timeoutMs != null ? createTimeoutSignal(timeoutMs) : undefined;
    const userSignal = fetchOptions.signal ?? undefined;
    const signal = combineAbortSignals(userSignal, timeoutSignal);

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string>),
    };

    appendFingerprint(headers);
    applyAuthHeader(headers, skipAuth);

    const response = await fetch(url, {
      ...fetchOptions,
      signal,
      headers,
      credentials:
        skipAuth ? 'omit' : ((fetchOptions.credentials as RequestCredentials) ?? 'include'),
    });

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      const message = formatHttpErrorDetail(
        body.detail,
        response.status,
        typeof body.message === 'string' ? body.message : undefined,
      );
      throw new HttpError(message, response.status);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return response.json();
  }

  async get<T>(
    endpoint: string,
    params?: Record<string, string | number | boolean | undefined>,
    requestOptions?: Omit<RequestOptions, 'params' | 'method'>
  ): Promise<T> {
    return this.request<T>(endpoint, { method: 'GET', params, ...requestOptions });
  }

  async post<T>(endpoint: string, data?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
      ...options,
    });
  }

  async put<T>(endpoint: string, data?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PUT',
      body: data ? JSON.stringify(data) : undefined,
      ...options,
    });
  }

  async patch<T>(endpoint: string, data?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PATCH',
      body: data ? JSON.stringify(data) : undefined,
      ...options,
    });
  }

  async delete<T>(endpoint: string, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, { method: 'DELETE', ...options });
  }

  /** Authenticated GET that returns raw response text (JSONL, CSV, …). */
  async getText(
    endpoint: string,
    params?: Record<string, string | number | boolean | undefined>,
    requestOptions?: Omit<RequestOptions, 'params' | 'method' | 'body'>,
  ): Promise<string> {
    const { timeoutMs, skipAuth, ...fetchOptions } = requestOptions ?? {};
    const url = this.buildUrl(endpoint, params);

    const timeoutSignal = timeoutMs != null ? createTimeoutSignal(timeoutMs) : undefined;
    const userSignal = fetchOptions.signal ?? undefined;
    const signal = combineAbortSignals(userSignal, timeoutSignal);

    const headers: Record<string, string> = {
      ...(requestOptions?.headers as Record<string, string>),
    };

    appendFingerprint(headers);
    applyAuthHeader(headers, skipAuth);

    const response = await fetch(url, {
      method: 'GET',
      ...fetchOptions,
      signal,
      headers,
      credentials:
        skipAuth ? 'omit' : ((fetchOptions.credentials as RequestCredentials) ?? 'include'),
    });

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      const message = formatHttpErrorDetail(
        body.detail,
        response.status,
        typeof body.message === 'string' ? body.message : undefined,
      );
      throw new HttpError(message, response.status);
    }

    return response.text();
  }

  async postBlob(
    endpoint: string,
    data?: unknown,
    requestOptions?: Omit<RequestOptions, 'body'>,
  ): Promise<Blob> {
    const { params, timeoutMs, ...fetchOptions } = requestOptions ?? {};
    const url = this.buildUrl(endpoint, params);

    const timeoutSignal = timeoutMs != null ? createTimeoutSignal(timeoutMs) : undefined;
    const userSignal = fetchOptions.signal ?? undefined;
    const signal = combineAbortSignals(userSignal, timeoutSignal);

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(requestOptions?.headers as Record<string, string>),
    };

    appendFingerprint(headers);
    applyAuthHeader(headers);

    const response = await fetch(url, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
      signal,
      headers,
      credentials: (fetchOptions.credentials as RequestCredentials) ?? 'include',
    });

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      const message = formatHttpErrorDetail(
        body.detail,
        response.status,
        typeof body.message === 'string' ? body.message : undefined,
      );
      throw new HttpError(message, response.status);
    }

    return response.blob();
  }

  async upload<T>(endpoint: string, formData: FormData): Promise<T> {
    const url = this.buildUrl(endpoint);
    const headers: Record<string, string> = {};
    appendFingerprint(headers);
    applyAuthHeader(headers);

    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: formData,
      credentials: 'include',
    });

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      const message = formatHttpErrorDetail(
        body.detail,
        response.status,
        typeof body.message === 'string' ? body.message : undefined,
      );
      throw new HttpError(message, response.status);
    }

    return response.json();
  }

  async stream(options: StreamingRequestOptions): Promise<void> {
    const { url, method = 'POST', body, params, onEvent, onError, onComplete, signal } = options;
    const fullUrl = this.buildUrl(url, params as Record<string, string | number | boolean | undefined>);

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    };
    applyAuthHeader(headers);

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
        onError?.({
          message: errorData.message || `HTTP error ${response.status}`,
          status: response.status,
          code: errorData.code,
          details: errorData.details,
        });
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
          if (buffer.trim()) parseSSEBuffer(buffer, onEvent);
          break;
        }
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (line.trim()) parseSSEBuffer(line, onEvent);
        }
      }

      onComplete?.();
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') return;
      onError?.({
        message: error instanceof Error ? error.message : 'Streaming request failed',
      });
    }
  }
}

export const apiClient = new ApiClient(API_BASE_URL);

let _accessToken: string | null = null;

export function setAuthTokens(accessToken: string, refreshToken?: string) {
  _accessToken = accessToken;
  if (refreshToken) {
    try {
      localStorage.setItem('leagent_refresh_token', refreshToken);
    } catch {
      /* ignore */
    }
  }
  try {
    if (accessToken) localStorage.setItem('leagent_access_token', accessToken);
  } catch {
    /* ignore */
  }
}

export function clearAuthTokens() {
  _accessToken = null;
  try {
    localStorage.removeItem('leagent_access_token');
    localStorage.removeItem('leagent_refresh_token');
  } catch {
    /* ignore */
  }
}

export function getAccessToken(): string | null {
  if (_accessToken) return _accessToken;
  try {
    _accessToken = localStorage.getItem('leagent_access_token');
  } catch {
    _accessToken = null;
  }
  return _accessToken;
}

function applyAuthHeader(headers: Record<string, string>, skipAuth?: boolean) {
  if (skipAuth) return;
  const token = getAccessToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
}
