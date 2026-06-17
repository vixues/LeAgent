/** Qwen multi-angle camera labels (ComfyUI-qwenmultiangle compatible). */

export const AZIMUTH_PRESETS: { label: string; degrees: number }[] = [
  { label: 'front view', degrees: 0 },
  { label: 'front-right quarter view', degrees: 45 },
  { label: 'right side view', degrees: 90 },
  { label: 'back-right quarter view', degrees: 135 },
  { label: 'back view', degrees: 180 },
  { label: 'back-left quarter view', degrees: 225 },
  { label: 'left side view', degrees: 270 },
  { label: 'front-left quarter view', degrees: 315 },
];

export const ELEVATION_PRESETS: { label: string; degrees: number }[] = [
  { label: 'low-angle shot', degrees: -30 },
  { label: 'eye-level shot', degrees: 0 },
  { label: 'elevated shot', degrees: 30 },
  { label: 'high-angle shot', degrees: 60 },
];

export const DISTANCE_PRESETS: { label: string; zoom: number }[] = [
  { label: 'wide shot', zoom: 2 },
  { label: 'medium shot', zoom: 5 },
  { label: 'close-up', zoom: 8 },
];

export function nearestAzimuthLabel(degrees: number): string {
  const d = ((degrees % 360) + 360) % 360;
  let best = AZIMUTH_PRESETS[0];
  let min = 360;
  for (const p of AZIMUTH_PRESETS) {
    const diff = Math.min(Math.abs(d - p.degrees), 360 - Math.abs(d - p.degrees));
    if (diff < min) {
      min = diff;
      best = p;
    }
  }
  return best!.label;
}

export function nearestElevationLabel(degrees: number): string {
  const clamped = Math.max(-30, Math.min(60, degrees));
  let best = ELEVATION_PRESETS[1]!;
  let min = 90;
  for (const p of ELEVATION_PRESETS) {
    const diff = Math.abs(clamped - p.degrees);
    if (diff < min) {
      min = diff;
      best = p;
    }
  }
  return best.label;
}

export function zoomToDistanceLabel(zoom: number): string {
  const z = Math.max(0, Math.min(10, zoom));
  if (z < 3.5) return 'wide shot';
  if (z < 7) return 'medium shot';
  return 'close-up';
}

/** `<sks> front view eye-level shot medium shot` */
export function buildQwenViewPrompt(azimuth: number, elevation: number, zoom: number): string {
  return `<sks> ${nearestAzimuthLabel(azimuth)} ${nearestElevationLabel(elevation)} ${zoomToDistanceLabel(zoom)}`;
}

export function zoomToDistance(zoom: number): number {
  return 1.5 + (Math.max(0, Math.min(10, zoom)) / 10) * 6.5;
}

export function distanceToZoom(distance: number): number {
  return Math.max(0, Math.min(10, ((distance - 1.5) / 6.5) * 10));
}
