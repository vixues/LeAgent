/** Base URL for files under `public/pet-presets/` (Vite `BASE_URL` aware). */
export function petPresetPublicUrl(relativePath: string): string {
  const base = import.meta.env.BASE_URL || '/';
  const normalized = base.endsWith('/') ? base : `${base}/`;
  const trimmed = relativePath.replace(/^\//, '');
  return `${normalized}${trimmed}`;
}

/** Shipped static samples for library preview / download / upload testing (not API rows). */
export const PET_PRESET_SAMPLE_FILES = [
  'pet-presets/bird.svg',
  'pet-presets/bird-motion.svg',
  'pet-presets/rabbit.svg',
  'pet-presets/rabbit-motion.svg',
  'pet-presets/dog.svg',
  'pet-presets/dog-motion.svg',
  'pet-presets/cat.svg',
  'pet-presets/cat-motion.svg',
] as const;
