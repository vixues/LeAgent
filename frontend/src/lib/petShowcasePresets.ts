import { isPetBuiltinAppearance, type PetBuiltinAppearance } from '@/lib/builtinPets';
import { isPetRenderableImageRow } from '@/lib/petAppearanceMime';
import type { PetBehaviorSettings, PetNestSettings, PetSettings } from '@/lib/petSettings';
import { resolvedBehavior, resolvedNest } from '@/lib/petSettings';

/**
 * Built-in showcase presets — replace or extend this list for your product.
 * `appearanceImageIndex` / `backgroundImageIndex`: 0-based index into project **image** files when applying / previewing.
 */
export interface PetShowcasePreset {
  id: string;
  nest: Partial<PetNestSettings>;
  behavior: Partial<PetBehaviorSettings>;
  /** Shipped SVG mascot (`public/pet-presets/`); wins over `appearanceImageIndex` when both exist. */
  appearanceBuiltin?: PetBuiltinAppearance;
  /** Use project image #N as appearance in preview / apply */
  appearanceImageIndex?: number;
  /** Use project image #N as nest background in preview / apply */
  backgroundImageIndex?: number;
}

function imageFiles(imageRows: { file_id: string; mime_type: string | null; original_name: string }[]) {
  return imageRows.filter((r) => isPetRenderableImageRow(r));
}

/**
 * Merge saved settings with a preset for preview. When `imageRows` is passed,
 * `appearanceImageIndex` / `backgroundImageIndex` resolve to concrete `file_id`s.
 */
export function mergeShowcasePreviewSettings(
  base: PetSettings,
  preset: PetShowcasePreset | null,
  imageRows?: { file_id: string; mime_type: string | null; original_name: string }[],
): PetSettings {
  if (!preset) return base;
  let nest: PetNestSettings = { ...resolvedNest(base), ...preset.nest };
  if (imageRows && preset.backgroundImageIndex != null) {
    const imgs = imageFiles(imageRows);
    const row = imgs[preset.backgroundImageIndex];
    if (row) {
      nest = { ...nest, backgroundFileId: row.file_id };
    }
  }

  let appearance_builtin = base.appearance_builtin;
  let appearance_file_id = base.appearance_file_id;
  if (preset.appearanceBuiltin && isPetBuiltinAppearance(preset.appearanceBuiltin)) {
    appearance_builtin = preset.appearanceBuiltin;
    appearance_file_id = null;
  } else if (imageRows && preset.appearanceImageIndex != null) {
    const imgs = imageFiles(imageRows);
    const row = imgs[preset.appearanceImageIndex];
    if (row) {
      appearance_file_id = row.file_id;
      appearance_builtin = null;
    }
  }

  return {
    ...base,
    nest,
    behavior: { ...resolvedBehavior(base), ...preset.behavior },
    appearance_file_id,
    appearance_builtin,
  };
}

export function pickPreviewAppearanceFileId(
  base: PetSettings,
  imageRows: { file_id: string; mime_type: string | null; original_name: string }[],
  preset: PetShowcasePreset | null,
): string | null {
  const images = imageFiles(imageRows);
  if (preset?.appearanceImageIndex != null && images[preset.appearanceImageIndex]) {
    return images[preset.appearanceImageIndex]!.file_id;
  }
  const cur = typeof base.appearance_file_id === 'string' ? base.appearance_file_id : null;
  if (cur && images.some((r) => r.file_id === cur)) return cur;
  return images[0]?.file_id ?? null;
}

export const PET_SHOWCASE_PRESETS: readonly PetShowcasePreset[] = [
  {
    id: 'preset_sparrow',
    nest: {
      themeId: 'grass',
      accent: '#0d9488',
      backgroundOpacity: 0.26,
      backgroundPattern: 'dots',
    },
    behavior: {
      mode: 'auto',
      manualMode: 'jump',
      autoReactivity: 'expressive',
      motionStyle: 'playful',
      motionSpeed: 1.25,
      idleAnimation: 'float',
    },
    appearanceBuiltin: 'bird',
  },
  {
    id: 'preset_rabbit',
    nest: {
      themeId: 'wood',
      accent: '#c084fc',
      backgroundOpacity: 0.22,
      backgroundPattern: 'grid',
    },
    behavior: {
      mode: 'auto',
      manualMode: 'jump',
      autoReactivity: 'normal',
      motionStyle: 'bouncy',
      motionSpeed: 1.1,
      idleAnimation: 'hop',
    },
    appearanceBuiltin: 'rabbit',
  },
  {
    id: 'preset_puppy',
    nest: {
      themeId: 'grass',
      accent: '#ea580c',
      backgroundOpacity: 0.3,
      backgroundPattern: 'noise',
    },
    behavior: {
      mode: 'auto',
      manualMode: 'shake',
      autoReactivity: 'expressive',
      motionStyle: 'playful',
      motionSpeed: 1.35,
      idleAnimation: 'tailWag',
    },
    appearanceBuiltin: 'dog',
  },
  {
    id: 'preset_cat',
    nest: {
      themeId: 'night',
      accent: '#94a3b8',
      backgroundOpacity: 0.2,
      backgroundPattern: 'none',
    },
    behavior: {
      mode: 'manual',
      manualMode: 'sleep',
      autoReactivity: 'subtle',
      motionStyle: 'focused',
      motionSpeed: 0.8,
      idleAnimation: 'blink',
    },
    appearanceBuiltin: 'cat',
  },
  {
    id: 'line_art_default',
    nest: {
      themeId: 'grass',
      accent: '#0284c7',
      backgroundFileId: null,
      backgroundOpacity: 0.22,
      backgroundPattern: 'dots',
    },
    behavior: { mode: 'auto', manualMode: 'calm', autoReactivity: 'normal' },
  },
  {
    id: 'wood_studio',
    nest: {
      themeId: 'wood',
      accent: '#c2410c',
      backgroundOpacity: 0.3,
      backgroundPattern: 'grid',
    },
    behavior: { mode: 'auto', manualMode: 'calm', autoReactivity: 'subtle' },
    appearanceImageIndex: 0,
    backgroundImageIndex: 0,
  },
  {
    id: 'night_coder',
    nest: {
      themeId: 'night',
      accent: '#818cf8',
      backgroundOpacity: 0.35,
      backgroundPattern: 'noise',
    },
    behavior: { mode: 'auto', manualMode: 'calm', autoReactivity: 'expressive' },
    backgroundImageIndex: 0,
  },
  {
    id: 'focus_companion',
    nest: {
      themeId: 'night',
      accent: '#64748b',
      backgroundOpacity: 0.18,
      backgroundPattern: 'none',
    },
    behavior: { mode: 'manual', manualMode: 'focus', autoReactivity: 'subtle' },
  },
  {
    id: 'excited_helper',
    nest: {
      themeId: 'grass',
      accent: '#16a34a',
      backgroundOpacity: 0.28,
      backgroundPattern: 'dots',
    },
    behavior: { mode: 'manual', manualMode: 'excited', autoReactivity: 'expressive' },
    appearanceImageIndex: 1,
    backgroundImageIndex: 0,
  },
  {
    id: 'rest_cafe',
    nest: {
      themeId: 'wood',
      accent: '#a16207',
      backgroundOpacity: 0.2,
      backgroundPattern: 'grid',
    },
    behavior: { mode: 'manual', manualMode: 'sleep', autoReactivity: 'normal' },
  },
] as const;
