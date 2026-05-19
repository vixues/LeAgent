import { type PetClipState, type PetIdleAnimation } from '@/lib/petSettings';

export const STUDIO_IDLE_SUBS: PetIdleAnimation[] = ['none', 'breath', 'blink', 'float', 'tailWag', 'hop'];

export const STUDIO_STATE_GROUPS: { id: string; states: PetClipState[] }[] = [
  { id: 'idle', states: ['idle' as const, ...STUDIO_IDLE_SUBS] },
  { id: 'work', states: ['working' as const] },
  { id: 'reactions', states: ['happy' as const] },
  { id: 'life', states: ['sleep' as const, 'focus' as const, 'excited' as const] },
  { id: 'skills', states: ['walk' as const, 'wave' as const, 'jump' as const, 'shake' as const, 'lookAround' as const, 'dance' as const] },
];

export const STUDIO_STATE_SET = new Set<PetClipState>(STUDIO_STATE_GROUPS.flatMap((g) => g.states) as PetClipState[]);
