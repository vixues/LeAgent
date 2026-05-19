import { previewInputForVisual } from '@/lib/petActionCatalog';
import type { PetClipState } from '@/lib/petSettings';
import type { PetBehaviorSettings, PetIdleAnimation } from '@/lib/petSettings';
import type { PetBehaviorVisual } from '@/lib/petBehaviorVisual';
import { PET_ACTION_VISUALS } from '@/lib/petActionCatalog';
import { STUDIO_IDLE_SUBS } from './studioStateGroups';

/**
 * Drives a synthetic runtime snapshot for a chosen clip slot, like the Pet Space action preview table.
 */
export function studioStateToVisualInput(
  s: PetClipState,
  base: PetBehaviorSettings,
): { behavior: PetBehaviorSettings; isStreaming: boolean; happyFlash: boolean } {
  if (s === 'working') {
    return { behavior: { ...base, mode: 'auto' }, isStreaming: true, happyFlash: false };
  }
  if (s === 'happy') {
    return { behavior: { ...base, mode: 'auto' }, isStreaming: false, happyFlash: true };
  }
  if (STUDIO_IDLE_SUBS.includes(s as PetIdleAnimation) && s !== 'idle') {
    return {
      behavior: { ...base, mode: 'manual', manualMode: 'calm', idleAnimation: s as PetIdleAnimation },
      isStreaming: false,
      happyFlash: false,
    };
  }
  if ((PET_ACTION_VISUALS as readonly string[]).includes(s)) {
    return previewInputForVisual(s as PetBehaviorVisual, base);
  }
  return { behavior: { ...base, mode: 'manual', manualMode: 'calm' }, isStreaming: false, happyFlash: false };
}
