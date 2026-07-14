import type { LogoBackdropPreset } from '@/stores/branding';
import type { CSSProperties } from 'react';

/** Resolved app theme — drives Logo stage gradients for contrast with white mark + title. */
export type LogoBackdropTheme = 'light' | 'dark';

/** Shared blue gradient for minimal-mode mark + title — matches `favicon.svg` (`fileLogoPrimary`). */
export const MINIMAL_BRAND_GRADIENT =
  'linear-gradient(to top right, #7DD3FC 0%, #5CB8FA 42%, #3D94EB 100%)';

/** Default mark for minimal mode — same asset / stops as the browser favicon. */
export const MINIMAL_BRAND_MARK_SRC = '/favicon.svg';

export function isMinimalBackdrop(preset: LogoBackdropPreset): boolean {
  return preset === 'minimal';
}

/** Title / wordmark fill for minimal backdrop (CSS background-clip text). */
export function getMinimalBrandTitleStyle(): CSSProperties {
  return {
    backgroundImage: MINIMAL_BRAND_GRADIENT,
    WebkitBackgroundClip: 'text',
    backgroundClip: 'text',
    color: 'transparent',
  };
}

/**
 * Recolor the brand mark via CSS mask + the same blue gradient.
 * Works for the default white SVG and most uploaded icons.
 */
export function getMinimalBrandMarkStyle(maskUrl: string): CSSProperties {
  return {
    backgroundImage: MINIMAL_BRAND_GRADIENT,
    WebkitMaskImage: `url("${maskUrl}")`,
    maskImage: `url("${maskUrl}")`,
    WebkitMaskSize: 'contain',
    maskSize: 'contain',
    WebkitMaskRepeat: 'no-repeat',
    maskRepeat: 'no-repeat',
    WebkitMaskPosition: 'center',
    maskPosition: 'center',
  };
}

/** Hour-based mood when preset is `auto`. */
function autoTimeBand(hour: number): 'night' | 'dawn' | 'day' | 'noon' | 'dusk' {
  if (hour >= 22 || hour < 5) return 'night';
  if (hour < 9) return 'dawn';
  if (hour < 12) return 'day';
  if (hour < 15) return 'noon';
  if (hour < 18) return 'day';
  if (hour < 22) return 'dusk';
  return 'night';
}

/**
 * Very light left vignette so the white mark stays legible without killing the fresh palette.
 */
function logoZoneReadability(theme: LogoBackdropTheme): string {
  if (theme === 'dark') {
    return 'radial-gradient(ellipse 100% 115% at 10% 45%, hsl(230 35% 14% / 0.18), transparent 65%)';
  }
  return 'radial-gradient(ellipse 100% 115% at 10% 45%, hsl(220 45% 38% / 0.07), transparent 65%)';
}

function layersForBand(
  band: ReturnType<typeof autoTimeBand>,
  theme: LogoBackdropTheme,
): string {
  const read = logoZoneReadability(theme);

  if (theme === 'dark') {
    switch (band) {
      case 'night':
        return [
          'linear-gradient(138deg, hsl(225 48% 44%) 0%, hsl(258 46% 46%) 45%, hsl(195 44% 42%) 100%)',
          'radial-gradient(ellipse 90% 72% at 20% 10%, hsl(188 72% 62% / 0.42), transparent 58%)',
          'radial-gradient(ellipse 78% 58% at 98% 88%, hsl(285 58% 62% / 0.32), transparent 52%)',
          read,
        ].join(', ');
      case 'dawn':
        return [
          'linear-gradient(122deg, hsl(28 52% 46%) 0%, hsl(335 48% 48%) 40%, hsl(205 46% 44%) 100%)',
          'radial-gradient(ellipse 95% 75% at 12% 24%, hsl(48 78% 62% / 0.44), transparent 54%)',
          'radial-gradient(ellipse 70% 56% at 90% 84%, hsl(190 55% 54% / 0.32), transparent 50%)',
          read,
        ].join(', ');
      case 'day':
        return [
          'linear-gradient(140deg, hsl(202 46% 46%) 0%, hsl(175 42% 44%) 52%, hsl(232 44% 48%) 100%)',
          'radial-gradient(ellipse 105% 85% at 50% -8%, hsl(52 88% 68% / 0.28), transparent 56%)',
          'radial-gradient(ellipse 62% 50% at 94% 52%, hsl(268 52% 62% / 0.26), transparent 46%)',
          read,
        ].join(', ');
      case 'noon':
        return [
          'linear-gradient(158deg, hsl(198 50% 48%) 0%, hsl(168 46% 46%) 45%, hsl(212 48% 50%) 100%)',
          'radial-gradient(circle at 30% 24%, hsl(52 92% 66% / 0.34), transparent 42%)',
          'radial-gradient(ellipse 88% 65% at 84% 94%, hsl(225 55% 58% / 0.28), transparent 54%)',
          read,
        ].join(', ');
      case 'dusk':
        return [
          'linear-gradient(132deg, hsl(280 46% 46%) 0%, hsl(20 50% 48%) 38%, hsl(210 46% 46%) 100%)',
          'radial-gradient(ellipse 94% 65% at 6% 94%, hsl(38 78% 58% / 0.36), transparent 54%)',
          'radial-gradient(ellipse 74% 54% at 94% 8%, hsl(310 58% 58% / 0.28), transparent 48%)',
          read,
        ].join(', ');
      default:
        return layersForBand('day', theme);
    }
  }

  /* Light: airy, fresh, gallery-like — mint / sky / soft violet tech */
  switch (band) {
    case 'night':
      return [
        'linear-gradient(138deg, hsl(220 52% 78%) 0%, hsl(255 48% 82%) 45%, hsl(195 50% 76%) 100%)',
        'radial-gradient(ellipse 90% 72% at 20% 10%, hsl(188 65% 88% / 0.55), transparent 58%)',
        'radial-gradient(ellipse 78% 58% at 98% 88%, hsl(285 45% 86% / 0.38), transparent 52%)',
        read,
      ].join(', ');
    case 'dawn':
      return [
        'linear-gradient(122deg, hsl(32 58% 82%) 0%, hsl(340 52% 84%) 40%, hsl(205 48% 80%) 100%)',
        'radial-gradient(ellipse 95% 75% at 12% 24%, hsl(48 88% 86% / 0.55), transparent 54%)',
        'radial-gradient(ellipse 70% 56% at 90% 84%, hsl(190 55% 78% / 0.36), transparent 50%)',
        read,
      ].join(', ');
    case 'day':
      return [
        'linear-gradient(140deg, hsl(200 55% 82%) 0%, hsl(172 48% 80%) 52%, hsl(230 52% 84%) 100%)',
        'radial-gradient(ellipse 105% 85% at 50% -8%, hsl(52 95% 88% / 0.38), transparent 56%)',
        'radial-gradient(ellipse 62% 50% at 94% 52%, hsl(268 48% 86% / 0.28), transparent 46%)',
        read,
      ].join(', ');
    case 'noon':
      return [
        'linear-gradient(158deg, hsl(196 58% 82%) 0%, hsl(168 52% 80%) 45%, hsl(214 56% 84%) 100%)',
        'radial-gradient(circle at 30% 24%, hsl(52 98% 88% / 0.42), transparent 42%)',
        'radial-gradient(ellipse 88% 65% at 84% 94%, hsl(225 55% 84% / 0.32), transparent 54%)',
        read,
      ].join(', ');
    case 'dusk':
      return [
        'linear-gradient(132deg, hsl(278 50% 82%) 0%, hsl(24 58% 84%) 38%, hsl(212 50% 82%) 100%)',
        'radial-gradient(ellipse 94% 65% at 6% 94%, hsl(38 85% 84% / 0.42), transparent 54%)',
        'radial-gradient(ellipse 74% 54% at 94% 8%, hsl(312 48% 86% / 0.32), transparent 48%)',
        read,
      ].join(', ');
    default:
      return layersForBand('day', theme);
  }
}

type ScenicBackdropPreset = Exclude<LogoBackdropPreset, 'auto' | 'minimal'>;

function presetLayers(preset: ScenicBackdropPreset, theme: LogoBackdropTheme): string {
  const read = logoZoneReadability(theme);

  if (theme === 'dark') {
    switch (preset) {
      case 'aurora':
        return [
          'linear-gradient(148deg, hsl(186 52% 42%) 0%, hsl(238 48% 46%) 48%, hsl(158 46% 40%) 100%)',
          'radial-gradient(ellipse 105% 75% at 18% 26%, hsl(175 70% 58% / 0.48), transparent 54%)',
          'radial-gradient(ellipse 84% 64% at 88% 74%, hsl(290 55% 58% / 0.34), transparent 48%)',
          'radial-gradient(circle at 52% 100%, hsl(320 58% 58% / 0.22), transparent 44%)',
          read,
        ].join(', ');
      case 'circuit':
        return [
          'linear-gradient(185deg, hsl(198 48% 42%) 0%, hsl(215 46% 46%) 100%)',
          'repeating-linear-gradient(90deg, hsl(190 75% 72% / 0.12) 0 1px, transparent 1px 20px)',
          'repeating-linear-gradient(0deg, hsl(190 75% 72% / 0.1) 0 1px, transparent 1px 20px)',
          'radial-gradient(ellipse 125% 88% at 50% -5%, hsl(175 62% 58% / 0.38), transparent 60%)',
          'radial-gradient(circle at 100% 100%, hsl(265 50% 58% / 0.26), transparent 40%)',
          read,
        ].join(', ');
      case 'ember':
        return [
          'linear-gradient(136deg, hsl(22 55% 46%) 0%, hsl(40 52% 48%) 44%, hsl(348 48% 46%) 100%)',
          'radial-gradient(ellipse 88% 66% at 10% 84%, hsl(32 78% 62% / 0.4), transparent 54%)',
          'radial-gradient(ellipse 68% 56% at 92% 16%, hsl(345 62% 58% / 0.28), transparent 48%)',
          read,
        ].join(', ');
      case 'void':
        return [
          'linear-gradient(162deg, hsl(230 46% 44%) 0%, hsl(208 48% 46%) 50%, hsl(278 44% 46%) 100%)',
          'radial-gradient(ellipse 80% 58% at 50% 115%, hsl(195 62% 58% / 0.34), transparent 54%)',
          'radial-gradient(circle at 6% 6%, hsl(275 55% 62% / 0.28), transparent 44%)',
          read,
        ].join(', ');
      default:
        return presetLayers('aurora', theme);
    }
  }

  switch (preset) {
    case 'aurora':
      return [
        'linear-gradient(148deg, hsl(186 58% 76%) 0%, hsl(238 52% 82%) 48%, hsl(158 48% 74%) 100%)',
        'radial-gradient(ellipse 105% 75% at 18% 26%, hsl(172 68% 88% / 0.58), transparent 54%)',
        'radial-gradient(ellipse 84% 64% at 88% 74%, hsl(290 48% 88% / 0.42), transparent 48%)',
        'radial-gradient(circle at 52% 100%, hsl(320 45% 88% / 0.28), transparent 44%)',
        read,
      ].join(', ');
    case 'circuit':
      return [
        'linear-gradient(185deg, hsl(198 55% 78%) 0%, hsl(215 48% 82%) 100%)',
        'repeating-linear-gradient(90deg, hsl(200 55% 42% / 0.09) 0 1px, transparent 1px 20px)',
        'repeating-linear-gradient(0deg, hsl(200 55% 42% / 0.07) 0 1px, transparent 1px 20px)',
        'radial-gradient(ellipse 125% 88% at 50% -5%, hsl(175 58% 86% / 0.45), transparent 60%)',
        'radial-gradient(circle at 100% 100%, hsl(265 48% 84% / 0.32), transparent 40%)',
        read,
      ].join(', ');
    case 'ember':
      return [
        'linear-gradient(136deg, hsl(22 62% 78%) 0%, hsl(40 58% 82%) 44%, hsl(348 52% 80%) 100%)',
        'radial-gradient(ellipse 88% 66% at 10% 84%, hsl(32 85% 86% / 0.48), transparent 54%)',
        'radial-gradient(ellipse 68% 56% at 92% 16%, hsl(345 58% 86% / 0.34), transparent 48%)',
        read,
      ].join(', ');
    case 'void':
      return [
        'linear-gradient(162deg, hsl(230 52% 80%) 0%, hsl(208 54% 82%) 50%, hsl(278 48% 84%) 100%)',
        'radial-gradient(ellipse 80% 58% at 50% 115%, hsl(195 58% 86% / 0.42), transparent 54%)',
        'radial-gradient(circle at 6% 6%, hsl(275 52% 88% / 0.34), transparent 44%)',
        read,
      ].join(', ');
    default:
      return presetLayers('aurora', theme);
  }
}

export function getLogoBackdropStyle(
  hour: number,
  preset: LogoBackdropPreset,
  theme: LogoBackdropTheme = 'light',
): Pick<CSSProperties, 'backgroundImage' | 'backgroundColor'> {
  if (preset === 'minimal') {
    return {
      backgroundColor: 'transparent',
      backgroundImage: 'none',
    };
  }

  const band = preset === 'auto' ? autoTimeBand(hour) : null;
  const layers =
    preset === 'auto' ? layersForBand(band!, theme) : presetLayers(preset, theme);

  return {
    backgroundColor: theme === 'dark' ? 'hsl(222 42% 38%)' : 'hsl(205 48% 84%)',
    backgroundImage: layers,
  };
}
