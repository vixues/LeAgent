import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cn, sleep, debounce, throttle, generateId, parseApiDateTime } from './utils';

describe('cn (className utility)', () => {
  it('should merge class names', () => {
    expect(cn('foo', 'bar')).toBe('foo bar');
  });

  it('should handle conditional classes', () => {
    expect(cn('base', true && 'included', false && 'excluded')).toBe('base included');
  });

  it('should merge Tailwind classes correctly', () => {
    expect(cn('px-2 py-1', 'px-4')).toBe('py-1 px-4');
  });

  it('should handle arrays', () => {
    expect(cn(['foo', 'bar'], 'baz')).toBe('foo bar baz');
  });

  it('should handle undefined and null', () => {
    expect(cn('foo', undefined, null, 'bar')).toBe('foo bar');
  });
});

describe('sleep', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should resolve after specified time', async () => {
    const promise = sleep(100);
    vi.advanceTimersByTime(100);
    await expect(promise).resolves.toBeUndefined();
  });
});

describe('debounce', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should debounce function calls', () => {
    const fn = vi.fn();
    const debouncedFn = debounce(fn, 100);

    debouncedFn();
    debouncedFn();
    debouncedFn();

    expect(fn).not.toHaveBeenCalled();

    vi.advanceTimersByTime(100);

    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('should pass arguments to the debounced function', () => {
    const fn = vi.fn();
    const debouncedFn = debounce(fn, 100);

    debouncedFn('arg1', 'arg2');
    vi.advanceTimersByTime(100);

    expect(fn).toHaveBeenCalledWith('arg1', 'arg2');
  });
});

describe('throttle', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should throttle function calls', () => {
    const fn = vi.fn();
    const throttledFn = throttle(fn, 100);

    throttledFn();
    throttledFn();
    throttledFn();

    expect(fn).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(100);
    throttledFn();

    expect(fn).toHaveBeenCalledTimes(2);
  });
});

describe('parseApiDateTime', () => {
  it('treats naive ISO datetime as UTC (not local wall)', () => {
    const s = '2025-05-13T10:00:00';
    const d = parseApiDateTime(s);
    expect(d.toISOString()).toBe('2025-05-13T10:00:00.000Z');
  });

  it('passes through Z-suffixed UTC', () => {
    const d = parseApiDateTime('2025-05-13T10:00:00Z');
    expect(d.toISOString()).toBe('2025-05-13T10:00:00.000Z');
  });

  it('parses explicit offset', () => {
    const d = parseApiDateTime('2025-05-13T10:00:00+08:00');
    expect(d.toISOString()).toBe('2025-05-13T02:00:00.000Z');
  });

  it('normalizes space separator before T', () => {
    const d = parseApiDateTime('2025-05-13 10:00:00');
    expect(d.toISOString()).toBe('2025-05-13T10:00:00.000Z');
  });
});

describe('generateId', () => {
  it('should generate a string', () => {
    const id = generateId();
    expect(typeof id).toBe('string');
  });

  it('should generate non-empty string', () => {
    const id = generateId();
    expect(id.length).toBeGreaterThan(0);
  });

  it('should generate unique IDs', () => {
    const ids = new Set<string>();
    for (let i = 0; i < 100; i++) {
      ids.add(generateId());
    }
    expect(ids.size).toBe(100);
  });
});
