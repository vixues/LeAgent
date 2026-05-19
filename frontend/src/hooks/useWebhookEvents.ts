import { useCallback, useEffect, useRef, useState } from 'react';
import { useUtilityStore } from '@/stores/utilityStore';
import { useAlertStore } from '@/stores/alertStore';

export type WebhookEventType =
  | 'flow.started'
  | 'flow.completed'
  | 'flow.failed'
  | 'flow.progress'
  | 'node.started'
  | 'node.completed'
  | 'node.failed'
  | 'message.received'
  | 'message.sent'
  | 'system.notification'
  | 'ping'
  | 'error';

export interface WebhookEvent<T = unknown> {
  id: string;
  type: WebhookEventType;
  data: T;
  timestamp: string;
  flowId?: string;
  nodeId?: string;
  sessionId?: string;
}

export interface WebhookEventsOptions {
  url?: string;
  autoConnect?: boolean;
  reconnect?: boolean;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Error) => void;
  eventFilters?: WebhookEventType[];
}

export interface WebhookEventsState {
  isConnected: boolean;
  isConnecting: boolean;
  lastEventAt: Date | null;
  reconnectAttempts: number;
  error: Error | null;
  eventCount: number;
}

type EventHandler<T = unknown> = (event: WebhookEvent<T>) => void;

export function useWebhookEvents(options: WebhookEventsOptions = {}) {
  const {
    url = '/api/v1/events',
    autoConnect = true,
    reconnect = true,
    reconnectInterval = 5000,
    maxReconnectAttempts = 10,
    onConnect,
    onDisconnect,
    onError,
    eventFilters,
  } = options;

  const { clientId, isOnline } = useUtilityStore();
  const { error: showError, warning } = useAlertStore();

  const [state, setState] = useState<WebhookEventsState>({
    isConnected: false,
    isConnecting: false,
    lastEventAt: null,
    reconnectAttempts: 0,
    error: null,
    eventCount: 0,
  });

  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handlersRef = useRef<Map<WebhookEventType | '*', Set<EventHandler>>>(new Map());
  const mountedRef = useRef(true);

  const addHandler = useCallback(<T>(eventType: WebhookEventType | '*', handler: EventHandler<T>) => {
    if (!handlersRef.current.has(eventType)) {
      handlersRef.current.set(eventType, new Set());
    }
    handlersRef.current.get(eventType)!.add(handler as EventHandler);

    return () => {
      handlersRef.current.get(eventType)?.delete(handler as EventHandler);
    };
  }, []);

  const removeHandler = useCallback(<T>(eventType: WebhookEventType | '*', handler: EventHandler<T>) => {
    handlersRef.current.get(eventType)?.delete(handler as EventHandler);
  }, []);

  const emit = useCallback((event: WebhookEvent) => {
    if (eventFilters && !eventFilters.includes(event.type)) {
      return;
    }

    const wildcardHandlers = handlersRef.current.get('*') || new Set();
    const typeHandlers = handlersRef.current.get(event.type) || new Set();

    wildcardHandlers.forEach((handler) => handler(event));
    typeHandlers.forEach((handler) => handler(event));

    setState((prev) => ({
      ...prev,
      lastEventAt: new Date(),
      eventCount: prev.eventCount + 1,
    }));
  }, [eventFilters]);

  const connect = useCallback(() => {
    if (eventSourceRef.current?.readyState === EventSource.OPEN) {
      return;
    }

    if (!isOnline) {
      setState((prev) => ({ ...prev, error: new Error('No network connection') }));
      return;
    }

    setState((prev) => ({ ...prev, isConnecting: true, error: null }));

    try {
      const eventUrl = `${url}?clientId=${clientId}`;
      const eventSource = new EventSource(eventUrl);
      eventSourceRef.current = eventSource;

      eventSource.onopen = () => {
        if (!mountedRef.current) return;
        setState((prev) => ({
          ...prev,
          isConnected: true,
          isConnecting: false,
          reconnectAttempts: 0,
          error: null,
        }));
        onConnect?.();
      };

      eventSource.onmessage = (event) => {
        if (!mountedRef.current) return;
        try {
          const webhookEvent = JSON.parse(event.data) as WebhookEvent;
          emit(webhookEvent);
        } catch (err) {
          console.error('Failed to parse webhook event:', err);
        }
      };

      eventSource.onerror = () => {
        if (!mountedRef.current) return;
        eventSource.close();
        eventSourceRef.current = null;

        setState((prev) => ({
          ...prev,
          isConnected: false,
          isConnecting: false,
        }));

        onDisconnect?.();

        if (reconnect && state.reconnectAttempts < maxReconnectAttempts) {
          setState((prev) => ({
            ...prev,
            reconnectAttempts: prev.reconnectAttempts + 1,
          }));

          reconnectTimeoutRef.current = setTimeout(() => {
            if (mountedRef.current) {
              connect();
            }
          }, reconnectInterval);
        } else if (state.reconnectAttempts >= maxReconnectAttempts) {
          const error = new Error('Max reconnect attempts reached');
          setState((prev) => ({ ...prev, error }));
          onError?.(error);
          showError('Connection lost. Please refresh the page.');
        }
      };
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Failed to connect');
      setState((prev) => ({
        ...prev,
        isConnecting: false,
        error,
      }));
      onError?.(error);
    }
  }, [url, clientId, isOnline, reconnect, reconnectInterval, maxReconnectAttempts, state.reconnectAttempts, emit, onConnect, onDisconnect, onError, showError]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    setState((prev) => ({
      ...prev,
      isConnected: false,
      isConnecting: false,
      reconnectAttempts: 0,
    }));

    onDisconnect?.();
  }, [onDisconnect]);

  const reconnectNow = useCallback(() => {
    disconnect();
    setState((prev) => ({ ...prev, reconnectAttempts: 0 }));
    connect();
  }, [connect, disconnect]);

  useEffect(() => {
    if (autoConnect) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [autoConnect]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (isOnline && autoConnect && !state.isConnected && !state.isConnecting) {
      connect();
    } else if (!isOnline && state.isConnected) {
      disconnect();
      warning('Connection lost. Will reconnect when online.');
    }
  }, [isOnline]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const on = useCallback(<T>(eventType: WebhookEventType | '*', handler: EventHandler<T>) => {
    return addHandler(eventType, handler);
  }, [addHandler]);

  const off = useCallback(<T>(eventType: WebhookEventType | '*', handler: EventHandler<T>) => {
    removeHandler(eventType, handler);
  }, [removeHandler]);

  const once = useCallback(<T>(eventType: WebhookEventType, handler: EventHandler<T>) => {
    const onceHandler: EventHandler<T> = (event) => {
      handler(event);
      removeHandler(eventType, onceHandler);
    };
    return addHandler(eventType, onceHandler);
  }, [addHandler, removeHandler]);

  return {
    ...state,
    connect,
    disconnect,
    reconnectNow,
    on,
    off,
    once,
  };
}

export default useWebhookEvents;
