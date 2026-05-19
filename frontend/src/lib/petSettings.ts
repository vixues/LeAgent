import type { PetBuiltinAppearance } from '@/lib/builtinPets';

export type NestThemeId = 'grass' | 'wood' | 'night';

/** CSS-only overlay on the nest (no extra files). */
export type NestBackgroundPattern = 'none' | 'dots' | 'grid' | 'noise';
export type NestBackgroundFit = 'cover' | 'contain' | 'repeat';
export type NestBackgroundPosition = 'center' | 'top' | 'bottom' | 'left' | 'right';

export interface PetNestSettings {
  themeId: NestThemeId;
  /** Optional full-bleed nest background from project files */
  backgroundFileId: string | null;
  accent: string;
  /** 0–1 opacity for the file background layer (preset wash stays separate). */
  backgroundOpacity: number;
  /** Decorative pattern over the nest card. */
  backgroundPattern: NestBackgroundPattern;
  backgroundFit: NestBackgroundFit;
  backgroundPosition: NestBackgroundPosition;
  /**
   * Sidebar dock: distance in px from the pet **scene** bottom to the activity plane (img flex-end baseline, roam/jump, floor line).
   * Matches the gap from the graphic’s bottom to the dock preview box bottom when the sprite fills the slot; may be **negative** to push the plane lower (e.g. extra padding in the asset).
   */
  dockFloorYPx: number;
  /**
   * Sidebar dock only: extra vertical offset in px for the **shadow** ellipse (positive ≈ shadow lower on screen).
   * Use when feet in the image are not at the bitmap bottom so the shadow can sit under the character.
   */
  dockShadowOffsetYPx: number;
}

/** Default `dockFloorYPx` for new nests and the Customize reset control. */
export const DEFAULT_DOCK_FLOOR_Y_PX = 5;
/** Default `dockShadowOffsetYPx` (shadow follows floor plane unless adjusted). */
export const DEFAULT_DOCK_SHADOW_OFFSET_Y_PX = 0;

export const DOCK_FLOOR_Y_MIN = -20;
export const DOCK_FLOOR_Y_MAX = 48;
export const DOCK_SHADOW_OFFSET_Y_MIN = -28;
export const DOCK_SHADOW_OFFSET_Y_MAX = 28;

/** Manual Agent–pet posture when not following stream auto rules */
export type PetManualMode =
  | 'calm'
  | 'sleep'
  | 'focus'
  | 'excited'
  | 'walk'
  | 'wave'
  | 'jump'
  | 'shake'
  | 'lookAround'
  | 'dance';

/** Auto mode: how strongly working / motion reacts to streaming */
export type PetAutoReactivity = 'subtle' | 'normal' | 'expressive';
export type PetMotionStyle = 'gentle' | 'bouncy' | 'playful' | 'focused';
export type PetIdleAnimation = 'none' | 'breath' | 'blink' | 'float' | 'tailWag' | 'hop';

/** Horizontal wander bound in the pet scene (fraction of half-stage width, ~%). */
export type PetRoamRange = 'tight' | 'normal' | 'wide';

/** Weights for autopilot action sampling (0–5; higher = more often). Omitted keys use merge defaults. */
export const PET_SCENE_ACTION_KEYS = [
  'idle',
  'walk',
  'lookAround',
  'jump',
  'wave',
  'dance',
  'shake',
] as const;

export type PetSceneActionKey = (typeof PET_SCENE_ACTION_KEYS)[number];

export type PetSceneActionWeights = Partial<Record<PetSceneActionKey, number>>;

export interface PetBehaviorSettings {
  mode: 'auto' | 'manual';
  /** When mode is manual: calm / sleep / focus (no庆祝闪烁) / excited idle */
  manualMode: PetManualMode;
  /** When mode is auto: subtle = calmer motion; expressive = stronger feedback */
  autoReactivity?: PetAutoReactivity;
  motionStyle: PetMotionStyle;
  /** Motion multiplier: 0.5 = slow, 2 = fast. */
  motionSpeed: number;
  idleAnimation: PetIdleAnimation;
  /**
   * Pet scene: autonomous roaming / action cycling. Off still allows click / double-tap interactions.
   * @default true
   */
  autopilot?: boolean;
  /** @default 'normal' */
  roamRange?: PetRoamRange;
  actionWeights?: PetSceneActionWeights;
}

/**
 * All behavior visuals that can have per-state clip bindings (kept in sync with PetBehaviorVisual).
 * Avoids importing petBehaviorVisual here (circular dependency).
 */
export const PET_CLIP_BEHAVIOR_KEYS = [
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
] as const;

export type PetClipBehaviorKey = (typeof PET_CLIP_BEHAVIOR_KEYS)[number];

/** Per-state or idle-substate animation asset binding (project file, optional builtin). */
export type PetClipState = PetClipBehaviorKey | PetIdleAnimation;

export interface PetClipBinding {
  fileId: string | null;
  /** Optional: use a built-in shipped SVG for this clip instead of a project file. */
  builtin?: PetBuiltinAppearance | null;
  /** Default loop; once = play one cycle then parent can fall back (dock/preview). */
  loop?: 'loop' | 'once';
  /** 0.25 – 4; used for CSS motion duration scaling when not overriding. */
  speed?: number;
  mirror?: boolean;
  fit?: 'cover' | 'contain';
  /**
   * When true, strip state keyframe classes for this state so bound GIF/IMG is not doubled with CSS pet-motion.
   * Default true for new bindings.
   */
  overrideCssMotion?: boolean;
}

const DEFAULT_CLIP_BINDING: Pick<
  PetClipBinding,
  'loop' | 'speed' | 'mirror' | 'fit' | 'overrideCssMotion'
> = {
  loop: 'loop',
  speed: 1,
  mirror: false,
  fit: 'contain',
  overrideCssMotion: true,
};

export function defaultClipBinding(partial: Partial<PetClipBinding> & { fileId: string | null }): PetClipBinding {
  return { ...DEFAULT_CLIP_BINDING, ...partial };
}

export function isClipBindingRenderable(binding: PetClipBinding | undefined | null): boolean {
  if (!binding) return false;
  if (binding.fileId) return true;
  if (binding.builtin) return true;
  return false;
}

export function normalizeClipBinding(partial: Partial<PetClipBinding> | null | undefined): PetClipBinding | null {
  if (partial == null) return null;
  const b: PetClipBinding = {
    fileId: partial.fileId ?? null,
    builtin: partial.builtin ?? null,
    ...DEFAULT_CLIP_BINDING,
    ...partial,
  };
  return isClipBindingRenderable(b) ? b : null;
}

/**
 * Returns the effective clip for current visual: clips[visual] first; if visual is idle, clips[idleAnimation] as fallback.
 */
export function resolvePetClip(
  visual: PetClipBehaviorKey,
  idleAnimation: PetIdleAnimation,
  settings: PetSettings,
): { key: PetClipState; binding: PetClipBinding } | null {
  const clips = settings.clips;
  if (!clips) return null;

  const fromKey = (key: PetClipState): { key: PetClipState; binding: PetClipBinding } | null => {
    const raw = clips[key];
    if (!raw) return null;
    const b = normalizeClipBinding(raw);
    if (!b) return null;
    return { key, binding: b };
  };

  const primary = fromKey(visual);
  if (primary) return primary;
  if (visual === 'idle') return fromKey(idleAnimation);
  return null;
}

/** Shallow per-state updates for `mergePetSettings` (not required to include `fileId` on every key). */
export type PetSettingsClipPatch = Partial<Record<PetClipState, Partial<PetClipBinding> | null>>;

export function mergeClips(
  current: PetSettings['clips'] | undefined,
  patch: PetSettingsClipPatch,
): PetSettings['clips'] {
  const out: NonNullable<PetSettings['clips']> = { ...(current ?? {}) };
  for (const k of Object.keys(patch) as PetClipState[]) {
    const p = patch[k];
    if (p === undefined) continue;
    if (p === null) {
      delete out[k];
      continue;
    }
    const prev = out[k];
    const merged: PetClipBinding = {
      ...DEFAULT_CLIP_BINDING,
      ...prev,
      ...p,
      fileId: p.fileId !== undefined ? p.fileId! : (prev?.fileId ?? null),
      builtin: p.builtin !== undefined ? p.builtin : prev?.builtin,
    };
    if (!isClipBindingRenderable(merged)) {
      delete out[k];
    } else {
      out[k] = merged;
    }
  }
  return Object.keys(out).length ? out : undefined;
}

/** Free-form character document threaded into pet bubble greetings and the agent system prompt. */
export interface PetPersonalitySettings {
  /** User-authored personality / character description (e.g. "Miku, a playful cat girlfriend..."). */
  document: string;
}

/** Hard cap matches the backend (see ``services/chat/pet_personality.py``). */
export const PET_PERSONALITY_MAX_CHARS = 2000;

export interface PetSettings {
  appearance_file_id?: string | null;
  /** Shipped SVG under `public/pet-presets/`; exclusive with a set `appearance_file_id`. */
  appearance_builtin?: PetBuiltinAppearance | null;
  /**
   * When the appearance asset is `image/gif`: apply subtle per-state filters on top of native GIF playback (dock / chat chip).
   * Omitted or `true` = enabled for GIF; `false` = only generic CSS motion, no state tint.
   */
  appearance_gif_bind_motion?: boolean;
  nest?: Partial<PetNestSettings>;
  behavior?: Partial<PetBehaviorSettings>;
  /** Per-state (and idle sub-state) optional animation clip bindings. */
  clips?: Partial<Record<PetClipState, PetClipBinding>>;
  /** Optional pet personality/character description used by LLM-generated pet bubble lines. */
  personality?: PetPersonalitySettings | null;
}

export function defaultNestSettings(): PetNestSettings {
  return {
    themeId: 'grass',
    backgroundFileId: null,
    accent: '#0284c7',
    backgroundOpacity: 0.25,
    backgroundPattern: 'none',
    backgroundFit: 'cover',
    backgroundPosition: 'center',
    dockFloorYPx: DEFAULT_DOCK_FLOOR_Y_PX,
    dockShadowOffsetYPx: DEFAULT_DOCK_SHADOW_OFFSET_Y_PX,
  };
}

const DEFAULT_ACTION_WEIGHTS: PetSceneActionWeights = {
  idle: 3,
  walk: 4,
  lookAround: 2,
  jump: 1,
  wave: 1,
  dance: 1,
  shake: 0,
};

export function defaultActionWeights(): PetSceneActionWeights {
  return { ...DEFAULT_ACTION_WEIGHTS };
}

/**
 * Merge user partial weights with defaults.
 */
export function resolveActionWeights(
  partial: PetSceneActionWeights | undefined,
): Record<PetSceneActionKey, number> {
  const out = {} as Record<PetSceneActionKey, number>;
  for (const k of PET_SCENE_ACTION_KEYS) {
    const v = partial?.[k] !== undefined ? partial[k]! : DEFAULT_ACTION_WEIGHTS[k];
    out[k] = Math.min(5, Math.max(0, Math.round(Number(v) || 0)));
  }
  return out;
}

/** Max |x| as a fraction of half the stage width (0–1). */
export function roamRangeFraction(r: PetRoamRange | undefined): number {
  switch (r ?? 'normal') {
    case 'tight':
      return 0.4;
    case 'wide':
      return 0.95;
    case 'normal':
    default:
      return 0.7;
  }
}

export function defaultBehaviorSettings(): PetBehaviorSettings {
  return {
    mode: 'auto',
    manualMode: 'calm',
    autoReactivity: 'normal',
    motionStyle: 'gentle',
    motionSpeed: 1,
    idleAnimation: 'breath',
    autopilot: true,
    roamRange: 'normal',
    actionWeights: undefined,
  };
}

export function parsePetSettings(raw: string | null | undefined): PetSettings {
  if (!raw) return {};
  try {
    const o = JSON.parse(raw) as unknown;
    if (!o || typeof o !== 'object') return {};
    return o as PetSettings;
  } catch {
    return {};
  }
}

export function resolvedNest(settings: PetSettings): PetNestSettings {
  return { ...defaultNestSettings(), ...settings.nest };
}

export function resolvedBehavior(settings: PetSettings): PetBehaviorSettings {
  return { ...defaultBehaviorSettings(), ...settings.behavior };
}

/** GIF state tint is on when the dock appearance is a GIF and the user has not turned binding off. */
export function appearanceGifBindMotionActive(
  settings: PetSettings,
  mimeType: string | null | undefined,
  hasBuiltinAppearance: boolean,
): boolean {
  if (hasBuiltinAppearance) return false;
  const m = (mimeType ?? '').toLowerCase();
  if (!m.includes('gif')) return false;
  return settings.appearance_gif_bind_motion !== false;
}

/**
 * Deep-merge settings JSON so PATCH updates (e.g. only appearance) do not wipe nest/behavior.
 */
export function mergePetSettings(
  existing: string | null | undefined,
  patch: Partial<Omit<PetSettings, 'clips'>> & { clips?: PetSettingsClipPatch },
): string {
  const cur = parsePetSettings(existing);
  const next: PetSettings = { ...cur };

  if (patch.appearance_file_id !== undefined) {
    next.appearance_file_id = patch.appearance_file_id;
    if (patch.appearance_file_id) {
      next.appearance_builtin = null;
    }
  }
  if (patch.appearance_builtin !== undefined) {
    next.appearance_builtin = patch.appearance_builtin;
    if (patch.appearance_builtin) {
      next.appearance_file_id = null;
    }
  }
  if (patch.appearance_gif_bind_motion !== undefined) {
    next.appearance_gif_bind_motion = patch.appearance_gif_bind_motion;
  }
  if (patch.nest !== undefined) {
    next.nest = { ...resolvedNest(cur), ...patch.nest };
  }
  if (patch.behavior !== undefined) {
    next.behavior = { ...resolvedBehavior(cur), ...patch.behavior };
  }
  if (patch.clips !== undefined) {
    next.clips = mergeClips(cur.clips, patch.clips);
  }
  if (patch.personality !== undefined) {
    next.personality = patch.personality;
  }

  return JSON.stringify(next);
}

export function resolvedPersonalityDocument(settings: PetSettings): string {
  const doc = settings.personality?.document;
  return typeof doc === 'string' ? doc : '';
}
