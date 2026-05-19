/**
 * Built-in desk pet appearances: static SVGs shipped under `public/pet-presets/`.
 * Art is original to this repo (CC0); safe to redistribute.
 */
export const PET_BUILTIN_APPEARANCES = ['bird', 'rabbit', 'dog', 'cat'] as const;
export type PetBuiltinAppearance = (typeof PET_BUILTIN_APPEARANCES)[number];

export function isPetBuiltinAppearance(v: unknown): v is PetBuiltinAppearance {
  return typeof v === 'string' && (PET_BUILTIN_APPEARANCES as readonly string[]).includes(v);
}

export function builtinPetSvgUrl(id: PetBuiltinAppearance): string {
  const base = import.meta.env.BASE_URL || '/';
  const prefix = base.endsWith('/') ? base : `${base}/`;
  return `${prefix}pet-presets/${id}.svg`;
}

export function builtinPetMotionSvgUrl(id: PetBuiltinAppearance): string {
  const base = import.meta.env.BASE_URL || '/';
  const prefix = base.endsWith('/') ? base : `${base}/`;
  return `${prefix}pet-presets/${id}-motion.svg`;
}

export function builtinPetManifestUrl(): string {
  const base = import.meta.env.BASE_URL || '/';
  const prefix = base.endsWith('/') ? base : `${base}/`;
  return `${prefix}pet-presets/manifest.json`;
}
