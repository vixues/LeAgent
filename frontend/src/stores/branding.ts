import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type LogoBackdropPreset = 'auto' | 'aurora' | 'circuit' | 'ember' | 'void';
export type BrandFontPreset = 'modern' | 'rounded' | 'handwritten' | 'mono';

export const LOGO_BACKDROP_PRESETS: LogoBackdropPreset[] = [
  'auto',
  'aurora',
  'circuit',
  'ember',
  'void',
];

export const BRAND_FONT_PRESETS: BrandFontPreset[] = [
  'modern',
  'rounded',
  'handwritten',
  'mono',
];

const MAX_DISPLAY_NAME = 32;

export const DEFAULT_BRAND_DISPLAY_NAME = 'LeAgent';

export function clampDisplayName(raw: string): string {
  return raw.trim().slice(0, MAX_DISPLAY_NAME);
}

export function resolveDisplayName(stored: string): string {
  const t = stored.trim();
  return t.length > 0 ? t : DEFAULT_BRAND_DISPLAY_NAME;
}

interface BrandingState {
  displayName: string;
  customIconDataUrl: string | null;
  logoBackdropPreset: LogoBackdropPreset;
  brandFontPreset: BrandFontPreset;
  setDisplayName: (name: string) => void;
  setCustomIconDataUrl: (dataUrl: string | null) => void;
  setLogoBackdropPreset: (preset: LogoBackdropPreset) => void;
  setBrandFontPreset: (preset: BrandFontPreset) => void;
  resetBranding: () => void;
}

const defaults = {
  displayName: '',
  customIconDataUrl: null as string | null,
  logoBackdropPreset: 'auto' as LogoBackdropPreset,
  brandFontPreset: 'modern' as BrandFontPreset,
};

export const useBrandingStore = create<BrandingState>()(
  persist(
    (set) => ({
      ...defaults,
      setDisplayName: (name) => set({ displayName: clampDisplayName(name) }),
      setCustomIconDataUrl: (dataUrl) => set({ customIconDataUrl: dataUrl }),
      setLogoBackdropPreset: (preset) => set({ logoBackdropPreset: preset }),
      setBrandFontPreset: (preset) => set({ brandFontPreset: preset }),
      resetBranding: () => set({ ...defaults }),
    }),
    { name: 'leagent-branding' }
  )
);
