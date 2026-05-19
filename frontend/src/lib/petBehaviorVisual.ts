import type { CSSProperties } from 'react';
import { cn } from '@/lib/utils';
import type { PetAutoReactivity, PetBehaviorSettings, PetIdleAnimation } from '@/lib/petSettings';

export type PetBehaviorVisual =
  | 'idle'
  | 'working'
  | 'happy'
  | 'sleep'
  | 'focus'
  | 'excited'
  | 'walk'
  | 'wave'
  | 'jump'
  | 'shake'
  | 'lookAround'
  | 'dance';

/**
 * Pure resolver for sidebar / chat chip / 展示台 preview.
 * Manual `focus` suppresses celebratory happy flash; `excited` keeps a lively idle when not streaming.
 */
export function resolvePetVisual(input: {
  behavior: PetBehaviorSettings;
  reduceMotion: boolean;
  isStreaming: boolean;
  happyFlash: boolean;
}): PetBehaviorVisual {
  const { behavior, reduceMotion, isStreaming, happyFlash } = input;

  if (behavior.mode === 'manual' && behavior.manualMode === 'sleep') {
    return 'sleep';
  }
  if (reduceMotion) {
    return 'idle';
  }
  if (behavior.mode === 'manual' && behavior.manualMode === 'focus') {
    return isStreaming ? 'working' : 'focus';
  }
  if (happyFlash) {
    return 'happy';
  }
  if (isStreaming) {
    return 'working';
  }
  if (behavior.mode === 'manual' && behavior.manualMode === 'excited') {
    return 'excited';
  }
  if (behavior.mode === 'manual' && behavior.manualMode !== 'calm') {
    return behavior.manualMode;
  }
  return 'idle';
}

export function pickPetWorkingMotionClass(reactivity: PetAutoReactivity, reduceMotion: boolean): string {
  if (reduceMotion) return '';
  if (reactivity === 'subtle') {
    return 'motion-safe:animate-[pet-nod_2s_ease-in-out_infinite]';
  }
  if (reactivity === 'expressive') {
    return 'motion-safe:animate-[pet-nod_0.75s_ease-in-out_infinite]';
  }
  return 'motion-safe:animate-[pet-nod_1.2s_ease-in-out_infinite]';
}

function idleMotionClass(idleAnimation: PetIdleAnimation | undefined): string {
  switch (idleAnimation) {
    case 'blink':
      return 'pet-motion pet-motion--blink';
    case 'float':
      return 'pet-motion pet-motion--float';
    case 'tailWag':
      return 'pet-motion pet-motion--wag';
    case 'hop':
      return 'pet-motion pet-motion--hop';
    case 'none':
      return '';
    default:
      return 'pet-motion pet-motion--breath';
  }
}

export function pickPetMotionClass(
  visual: PetBehaviorVisual,
  behavior: PetBehaviorSettings,
  reduceMotion: boolean,
): string {
  if (reduceMotion) return '';
  const styleClass = `pet-motion-style--${behavior.motionStyle ?? 'gentle'}`;
  switch (visual) {
    case 'working':
      return `pet-motion pet-motion--working pet-motion--working-${behavior.autoReactivity ?? 'normal'} ${styleClass}`;
    case 'happy':
      return `pet-motion pet-motion--happy ${styleClass}`;
    case 'sleep':
      return 'pet-motion pet-motion--sleep';
    case 'focus':
      return 'pet-motion pet-motion--focus';
    case 'excited':
      return `pet-motion pet-motion--excited ${styleClass}`;
    case 'walk':
      return `pet-motion pet-motion--walk ${styleClass}`;
    case 'wave':
      return `pet-motion pet-motion--wave ${styleClass}`;
    case 'jump':
      return `pet-motion pet-motion--jump ${styleClass}`;
    case 'shake':
      return `pet-motion pet-motion--shake ${styleClass}`;
    case 'lookAround':
      return `pet-motion pet-motion--look-around ${styleClass}`;
    case 'dance':
      return `pet-motion pet-motion--dance ${styleClass}`;
    case 'idle':
    default:
      return `${idleMotionClass(behavior.idleAnimation)} ${styleClass}`.trim();
  }
}

export function petMotionStyleVars(behavior: Pick<PetBehaviorSettings, 'motionSpeed'>): CSSProperties {
  const speed = Math.min(2, Math.max(0.5, Number(behavior.motionSpeed) || 1));
  return { '--pet-motion-speed': String(speed) } as CSSProperties;
}

/** Scales global motion when a per-clip `speed` is set (faster clip → higher multiplier on CSS var). */
export function petClipMotionStyleVars(
  behavior: Pick<PetBehaviorSettings, 'motionSpeed'>,
  clipActive: boolean,
  clipSpeed: number | undefined,
): CSSProperties {
  const base = Math.min(2, Math.max(0.5, Number(behavior.motionSpeed) || 1));
  if (!clipActive) {
    return { '--pet-motion-speed': String(base) } as CSSProperties;
  }
  const c = Math.min(4, Math.max(0.25, Number(clipSpeed) || 1));
  return { '--pet-motion-speed': String(base * c) } as CSSProperties;
}

/** State-specific filter tint on GIF appearances (does not swap GIF frames; complements `pickPetMotionClass`). */
export function pickPetGifBindClass(visual: PetBehaviorVisual): string {
  return cn('pet-gif-bind', `pet-gif-bind--${visual}`);
}

export function pickPetAppearanceMotionClass(
  visual: PetBehaviorVisual,
  behavior: PetBehaviorSettings,
  reduceMotion: boolean,
  gifBindEnabled: boolean,
): string {
  return pickPetClipAppearanceClass(visual, behavior, reduceMotion, {
    clipActive: false,
    clipOverride: false,
    gifBindForDisplayedAsset: gifBindEnabled,
  });
}

/**
 * When a state clip is active: if `clipOverride` is true, only the motion style tier + optional GIF tint
 * (no per-state keyframes on top of a bound sheet/GIF). If false, full `pickPetMotionClass` for that state.
 */
export function pickPetClipAppearanceClass(
  visual: PetBehaviorVisual,
  behavior: PetBehaviorSettings,
  reduceMotion: boolean,
  o: { clipActive: boolean; clipOverride: boolean; gifBindForDisplayedAsset: boolean },
): string {
  const { clipActive, clipOverride, gifBindForDisplayedAsset: gifBindEnabled } = o;
  if (clipActive && clipOverride) {
    if (reduceMotion) return '';
    return `pet-motion-style--${behavior.motionStyle ?? 'gentle'}`;
  }
  if (clipActive && !clipOverride) {
    return pickPetAppearanceMotionClass(visual, behavior, reduceMotion, gifBindEnabled);
  }
  return cn(
    pickPetMotionClass(visual, behavior, reduceMotion),
    !reduceMotion && gifBindEnabled && 'pet-appearance-gif',
    !reduceMotion && gifBindEnabled && pickPetGifBindClass(visual),
  ).trim();
}
