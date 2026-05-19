import { describe, it, expect, beforeEach, beforeAll, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { usePetSceneController } from './usePetSceneController';
import { defaultBehaviorSettings, mergePetSettings, parsePetSettings, roamRangeFraction } from '@/lib/petSettings';

const streamingRef = { current: false };
const reduceRef = { current: false };
vi.mock('@/stores/chat', () => ({
  useChatStore: (sel: (s: { isStreaming: boolean }) => boolean) => sel({ isStreaming: streamingRef.current }),
}));
vi.mock('@/hooks/useMobile', () => ({
  usePrefersReducedMotion: () => reduceRef.current,
}));

beforeAll(() => {
  global.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
});

describe('usePetSceneController', () => {
  beforeEach(() => {
    streamingRef.current = false;
    reduceRef.current = false;
  });

  it('keeps x and y at 0 when prefers reduced motion', () => {
    reduceRef.current = true;
    const r: React.MutableRefObject<HTMLDivElement | null> = { current: null };
    const { result } = renderHook(() => usePetSceneController({ settings: {}, stageRef: r, surface: 'chatEmpty' }));
    expect(result.current.x).toBe(0);
    expect(result.current.y).toBe(0);
  });

  it('exposes no override while streaming (working takes UI elsewhere)', () => {
    streamingRef.current = true;
    const settings = parsePetSettings(mergePetSettings('{}', { behavior: { ...defaultBehaviorSettings() } }));
    const r: React.MutableRefObject<HTMLDivElement | null> = { current: null };
    const { result } = renderHook(() => usePetSceneController({ settings, stageRef: r, surface: 'chatEmpty' }));
    expect(result.current.overrideVisual).toBeNull();
  });

  it('roamRangeFraction matches plan defaults', () => {
    expect(roamRangeFraction('tight')).toBeCloseTo(0.4);
    expect(roamRangeFraction('normal')).toBeCloseTo(0.7);
    expect(roamRangeFraction('wide')).toBeCloseTo(0.95);
  });
});
