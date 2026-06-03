import { useEffect, useMemo, useState } from 'react';

/** Light-mode chart hues — aligned with StatCard accents (sky / violet / emerald / amber). */
const PALETTE_LIGHT = [
  'rgb(2, 132, 199)', // sky-600 — primary / requests
  'rgb(139, 92, 246)', // violet-500 — latency
  'rgb(16, 185, 129)', // emerald-500 — cost
  'rgb(245, 158, 11)', // amber-500 — tokens / accent
  'rgb(236, 72, 153)', // pink-500
  'rgb(6, 182, 212)', // cyan-500
  'rgb(249, 115, 22)', // orange-500
  'rgb(100, 116, 139)', // slate-500 — other
] as const;

/** Dark-mode chart hues — lighter for contrast on ink surfaces. */
const PALETTE_DARK = [
  'rgb(56, 189, 248)', // sky-400
  'rgb(167, 139, 250)', // violet-400
  'rgb(52, 211, 153)', // emerald-400
  'rgb(251, 191, 36)', // amber-400
  'rgb(244, 114, 182)', // pink-400
  'rgb(34, 211, 238)', // cyan-400
  'rgb(251, 146, 60)', // orange-400
  'rgb(148, 163, 184)', // slate-400
] as const;

function toRgbTriplet(raw: string): string | undefined {
  const parts = raw.trim().split(/\s+/).filter(Boolean);
  if (parts.length < 3) return undefined;
  return `rgb(${parts[0]}, ${parts[1]}, ${parts[2]})`;
}

function isDarkMode(): boolean {
  return document.documentElement.classList.contains('dark');
}

export function useChartTheme() {
  const [ver, setVer] = useState(0);
  useEffect(() => {
    const el = document.documentElement;
    const obs = new MutationObserver(() => setVer((v) => v + 1));
    obs.observe(el, { attributes: true, attributeFilter: ['class'] });
    return () => obs.disconnect();
  }, []);

  return useMemo(() => {
    const cs = getComputedStyle(document.documentElement);
    const raw = (name: string) => cs.getPropertyValue(name).trim();
    const rgb = (name: string, fallback: string) => toRgbTriplet(raw(name)) ?? fallback;

    const dark = isDarkMode();
    const palette: string[] = dark ? [...PALETTE_DARK] : [...PALETTE_LIGHT];
    const primaryFromCss = rgb('--color-primary', palette[0]!);

    palette[0] = primaryFromCss;

    return {
      text: rgb('--color-text', dark ? 'rgb(244, 244, 246)' : 'rgb(23, 23, 23)'),
      textMuted: rgb('--color-text-secondary', dark ? 'rgb(161, 161, 170)' : 'rgb(91, 91, 97)'),
      textTertiary: rgb('--color-text-tertiary', dark ? 'rgb(110, 110, 120)' : 'rgb(140, 140, 150)'),
      border: rgb('--color-border', dark ? 'rgb(50, 50, 52)' : 'rgb(232, 230, 226)'),
      borderSubtle: rgb('--color-border-subtle', dark ? 'rgb(30, 30, 32)' : 'rgb(244, 242, 238)'),
      surface: rgb('--color-surface', dark ? 'rgb(22, 22, 24)' : 'rgb(255, 255, 255)'),
      background: rgb('--color-background', dark ? 'rgb(9, 9, 10)' : 'rgb(252, 251, 249)'),
      primary: primaryFromCss,
      /** Semantic series — maps to KPI card color language. */
      semantic: {
        requests: palette[0]!,
        latency: palette[1]!,
        cost: palette[2]!,
        tokens: palette[3]!,
      },
      series: palette,
      tooltip: {
        backgroundColor: rgb('--color-surface-elevated', dark ? 'rgb(30, 30, 33)' : 'rgb(255, 255, 255)'),
        border: `1px solid ${rgb('--color-border', dark ? 'rgb(50, 50, 52)' : 'rgb(232, 230, 226)')}`,
        borderRadius: 8,
        fontSize: 12,
        color: rgb('--color-text', dark ? 'rgb(244, 244, 246)' : 'rgb(23, 23, 23)'),
      },
    };
  }, [ver]);
}

export function chartLegendStyle(theme: ReturnType<typeof useChartTheme>) {
  return {
    fontSize: 11,
    color: theme.textMuted,
    lineHeight: '18px',
  };
}

export function seriesColor(theme: ReturnType<typeof useChartTheme>, index: number): string {
  return theme.series[index % theme.series.length] ?? theme.primary;
}
