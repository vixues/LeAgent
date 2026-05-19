import { describe, it, expect } from 'vitest';
import { defaultBehaviorSettings } from '@/lib/petSettings';
import { pickPetClipAppearanceClass, resolvePetVisual } from './petBehaviorVisual';

describe('resolvePetVisual', () => {
  it('prioritizes manual sleep over streaming', () => {
    expect(
      resolvePetVisual({
        behavior: { ...defaultBehaviorSettings(), mode: 'manual', manualMode: 'sleep' },
        reduceMotion: false,
        isStreaming: true,
        happyFlash: false,
      }),
    ).toBe('sleep');
  });

  it('manual focus maps to working while streaming', () => {
    expect(
      resolvePetVisual({
        behavior: { ...defaultBehaviorSettings(), mode: 'manual', manualMode: 'focus' },
        reduceMotion: false,
        isStreaming: true,
        happyFlash: false,
      }),
    ).toBe('working');
  });

  it('manual focus maps to focus when idle', () => {
    expect(
      resolvePetVisual({
        behavior: { ...defaultBehaviorSettings(), mode: 'manual', manualMode: 'focus' },
        reduceMotion: false,
        isStreaming: false,
        happyFlash: true,
      }),
    ).toBe('focus');
  });

  it('shows happy when happyFlash and not focus', () => {
    expect(
      resolvePetVisual({
        behavior: { ...defaultBehaviorSettings(), mode: 'auto', manualMode: 'calm' },
        reduceMotion: false,
        isStreaming: false,
        happyFlash: true,
      }),
    ).toBe('happy');
  });
});

describe('pickPetClipAppearanceClass', () => {
  const b = defaultBehaviorSettings();

  it('uses only motion style tier when clip is active and override is on', () => {
    const c = pickPetClipAppearanceClass('wave', b, false, {
      clipActive: true,
      clipOverride: true,
      gifBindForDisplayedAsset: true,
    });
    expect(c).toBe('pet-motion-style--gentle');
  });

  it('returns empty when reduce motion and clip override', () => {
    expect(
      pickPetClipAppearanceClass('wave', b, true, {
        clipActive: true,
        clipOverride: true,
        gifBindForDisplayedAsset: false,
      }),
    ).toBe('');
  });

  it('uses full motion when clip active but override off', () => {
    const c = pickPetClipAppearanceClass('wave', b, false, {
      clipActive: true,
      clipOverride: false,
      gifBindForDisplayedAsset: false,
    });
    expect(c).toContain('pet-motion--wave');
    expect(c).toContain('pet-motion-style--gentle');
  });

  it('applies gif bind classes when clip inactive and gif bind on', () => {
    const c = pickPetClipAppearanceClass('happy', b, false, {
      clipActive: false,
      clipOverride: false,
      gifBindForDisplayedAsset: true,
    });
    expect(c).toContain('pet-motion--happy');
    expect(c).toContain('pet-appearance-gif');
    expect(c).toContain('pet-gif-bind--happy');
  });
});
