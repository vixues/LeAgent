import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { usePetBehaviorMode } from './usePetBehaviorMode';

const streamingRef = { current: false };
const reduceMotionRef = { current: false };
vi.mock('@/stores/chat', () => ({
  useChatStore: (sel: (s: { isStreaming: boolean }) => boolean) => sel({ isStreaming: streamingRef.current }),
}));

vi.mock('@/hooks/useMobile', () => ({
  usePrefersReducedMotion: () => reduceMotionRef.current,
}));

describe('usePetBehaviorMode', () => {
  beforeEach(() => {
    streamingRef.current = false;
    reduceMotionRef.current = false;
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('maps streaming to working', () => {
    const { result, rerender } = renderHook(() => usePetBehaviorMode({}));
    expect(result.current.visual).toBe('idle');
    streamingRef.current = true;
    rerender();
    expect(result.current.visual).toBe('working');
  });

  it('shows happy briefly after stream ends', () => {
    streamingRef.current = true;
    const { result, rerender } = renderHook(() => usePetBehaviorMode({}));
    expect(result.current.visual).toBe('working');
    streamingRef.current = false;
    rerender();
    expect(result.current.visual).toBe('happy');
    act(() => {
      vi.advanceTimersByTime(2100);
    });
    rerender();
    expect(result.current.visual).toBe('idle');
  });

  it('respects manual sleep over streaming', () => {
    streamingRef.current = true;
    const { result, rerender } = renderHook(() =>
      usePetBehaviorMode({ behavior: { mode: 'manual', manualMode: 'sleep' } }),
    );
    expect(result.current.visual).toBe('sleep');
    streamingRef.current = false;
    rerender();
    expect(result.current.visual).toBe('sleep');
  });

  it('manual focus skips happy flash after stream ends', () => {
    streamingRef.current = true;
    const { result, rerender } = renderHook(() =>
      usePetBehaviorMode({ behavior: { mode: 'manual', manualMode: 'focus' } }),
    );
    expect(result.current.visual).toBe('working');
    streamingRef.current = false;
    rerender();
    expect(result.current.visual).toBe('focus');
    act(() => {
      vi.advanceTimersByTime(2100);
    });
    rerender();
    expect(result.current.visual).toBe('focus');
  });

  it('supports rich manual action modes', () => {
    const { result } = renderHook(() =>
      usePetBehaviorMode({
        behavior: {
          mode: 'manual',
          manualMode: 'dance',
          motionStyle: 'playful',
          motionSpeed: 1.4,
          idleAnimation: 'tailWag',
        },
      }),
    );
    expect(result.current.visual).toBe('dance');
    expect(result.current.behavior.motionStyle).toBe('playful');
    expect(result.current.behavior.motionSpeed).toBe(1.4);
  });

  it('reduced motion collapses active manual modes to idle, except sleep', () => {
    reduceMotionRef.current = true;
    const { result } = renderHook(() =>
      usePetBehaviorMode({ behavior: { mode: 'manual', manualMode: 'jump' } }),
    );
    expect(result.current.visual).toBe('idle');
  });
});
