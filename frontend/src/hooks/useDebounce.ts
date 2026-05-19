import { useCallback, useEffect, useRef, useState } from 'react';

export interface DebounceOptions {
  leading?: boolean;
  trailing?: boolean;
  maxWait?: number;
}

export function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(timer);
    };
  }, [value, delay]);

  return debouncedValue;
}

export function useDebouncedCallback<T extends (...args: Parameters<T>) => ReturnType<T>>(
  callback: T,
  delay: number,
  options: DebounceOptions = {}
): {
  debouncedFn: (...args: Parameters<T>) => void;
  cancel: () => void;
  flush: () => void;
  pending: () => boolean;
} {
  const { leading = false, trailing = true, maxWait } = options;

  const callbackRef = useRef(callback);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const maxWaitTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastArgsRef = useRef<Parameters<T> | null>(null);
  const lastCallTimeRef = useRef<number>(0);
  const lastInvokeTimeRef = useRef<number>(0);
  const pendingRef = useRef(false);

  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  const invokeFunc = useCallback((args: Parameters<T>) => {
    lastInvokeTimeRef.current = Date.now();
    pendingRef.current = false;
    callbackRef.current(...args);
  }, []);

  const cancel = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    if (maxWaitTimeoutRef.current) {
      clearTimeout(maxWaitTimeoutRef.current);
      maxWaitTimeoutRef.current = null;
    }
    lastArgsRef.current = null;
    pendingRef.current = false;
  }, []);

  const flush = useCallback(() => {
    if (pendingRef.current && lastArgsRef.current) {
      cancel();
      invokeFunc(lastArgsRef.current);
    }
  }, [cancel, invokeFunc]);

  const pending = useCallback(() => pendingRef.current, []);

  const debouncedFn = useCallback(
    (...args: Parameters<T>) => {
      const now = Date.now();
      const isInvoking = leading && !pendingRef.current;

      lastArgsRef.current = args;
      lastCallTimeRef.current = now;
      pendingRef.current = true;

      if (isInvoking) {
        invokeFunc(args);
      }

      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }

      if (trailing) {
        timeoutRef.current = setTimeout(() => {
          if (pendingRef.current && lastArgsRef.current) {
            invokeFunc(lastArgsRef.current);
          }
          timeoutRef.current = null;
        }, delay);
      }

      if (maxWait !== undefined && !maxWaitTimeoutRef.current) {
        maxWaitTimeoutRef.current = setTimeout(() => {
          if (pendingRef.current && lastArgsRef.current) {
            invokeFunc(lastArgsRef.current);
          }
          maxWaitTimeoutRef.current = null;
        }, maxWait);
      }
    },
    [delay, invokeFunc, leading, trailing, maxWait]
  );

  useEffect(() => {
    return () => {
      cancel();
    };
  }, [cancel]);

  return { debouncedFn, cancel, flush, pending };
}

export function useDebouncedState<T>(
  initialValue: T,
  delay: number
): [T, T, (value: T) => void] {
  const [value, setValue] = useState<T>(initialValue);
  const debouncedValue = useDebounce(value, delay);

  return [debouncedValue, value, setValue];
}

export function useDebouncedEffect(
  effect: () => void | (() => void),
  deps: React.DependencyList,
  delay: number
): void {
  const cleanupRef = useRef<(() => void) | undefined>(undefined);

  useEffect(() => {
    const timer = setTimeout(() => {
      const result = effect();
      cleanupRef.current = typeof result === 'function' ? result : undefined;
    }, delay);

    return () => {
      clearTimeout(timer);
      if (typeof cleanupRef.current === 'function') {
        cleanupRef.current();
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, delay]);
}

export default useDebounce;
