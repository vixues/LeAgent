import type { PetBehaviorVisual } from '@/lib/petBehaviorVisual';
import type { PetBehaviorSettings, PetIdleAnimation, PetManualMode } from '@/lib/petSettings';

export const PET_ACTION_VISUALS = [
  'idle',
  'working',
  'happy',
  'sleep',
  'focus',
  'excited',
  'walk',
  'wave',
  'jump',
  'shake',
  'lookAround',
  'dance',
] as const satisfies readonly PetBehaviorVisual[];

export type PetActionPreviewId = 'current' | PetBehaviorVisual;

const MANUAL_VISUALS = new Set<PetBehaviorVisual>([
  'sleep',
  'focus',
  'excited',
  'walk',
  'wave',
  'jump',
  'shake',
  'lookAround',
  'dance',
]);

export function previewInputForVisual(
  visual: PetBehaviorVisual,
  current: PetBehaviorSettings,
): { behavior: PetBehaviorSettings; isStreaming: boolean; happyFlash: boolean } {
  if (visual === 'working') {
    return { behavior: { ...current, mode: 'auto' }, isStreaming: true, happyFlash: false };
  }
  if (visual === 'happy') {
    return { behavior: { ...current, mode: 'auto' }, isStreaming: false, happyFlash: true };
  }
  if (visual === 'idle') {
    return {
      behavior: { ...current, mode: 'manual', manualMode: 'calm' },
      isStreaming: false,
      happyFlash: false,
    };
  }
  if (MANUAL_VISUALS.has(visual)) {
    return {
      behavior: { ...current, mode: 'manual', manualMode: visual as PetManualMode },
      isStreaming: false,
      happyFlash: false,
    };
  }
  return { behavior: current, isStreaming: false, happyFlash: false };
}

export function presetStateKind(
  state: string,
): { kind: 'visual'; visual: PetBehaviorVisual } | { kind: 'idle'; idle: PetIdleAnimation } | { kind: 'unknown' } {
  if ((PET_ACTION_VISUALS as readonly string[]).includes(state)) {
    return { kind: 'visual', visual: state as PetBehaviorVisual };
  }
  if (state === 'blink' || state === 'float' || state === 'tailWag' || state === 'hop') {
    return { kind: 'idle', idle: state };
  }
  return { kind: 'unknown' };
}
