import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { usePetBehaviorMode } from '@/hooks/usePetBehaviorMode';
import { defaultBehaviorSettings } from '@/lib/petSettings';

describe('usePetBehaviorMode', () => {
  it('returns override visual when provided', () => {
    const settings = { behavior: defaultBehaviorSettings() };
    const { result } = renderHook(() =>
      usePetBehaviorMode(settings, { overrideVisual: 'dance' }),
    );
    expect(result.current.visual).toBe('dance');
  });

  it('ignores override when null', () => {
    const settings = { behavior: { ...defaultBehaviorSettings(), mode: 'manual', manualMode: 'sleep' } };
    const { result } = renderHook(() => usePetBehaviorMode(settings, { overrideVisual: null }));
    expect(result.current.visual).toBe('sleep');
  });
});
