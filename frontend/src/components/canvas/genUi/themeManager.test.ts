import { describe, expect, it } from 'vitest';

import {
  composeDesignSurfaceClassName,
  composeThemedCardClassName,
  getGenUiTheme,
  getGenUiThemeIds,
  normalizeGenUiThemeId,
  resolveDesignSurfacePadding,
} from '@/components/canvas/genUi/themeManager';

describe('GenUI theme manager', () => {
  it('normalizes known theme ids and falls back for unknown values', () => {
    expect(normalizeGenUiThemeId(' geek ')).toBe('geek');
    expect(normalizeGenUiThemeId('missing')).toBe('slide');
    expect(normalizeGenUiThemeId(null, 'minimal')).toBe('minimal');
  });

  it('exposes geek theme metadata and classes', () => {
    const geek = getGenUiTheme('geek');

    expect(geek.id).toBe('geek');
    expect(geek.tone).toBe('technical');
    expect(geek.surfaceClassName).toContain('font-mono');
    expect(getGenUiThemeIds()).toContain('geek');
  });

  it('composes surface and padding classes consistently', () => {
    expect(resolveDesignSurfacePadding('lg')).toBe('p-8');
    expect(resolveDesignSurfacePadding('bad')).toBe('p-5');

    const className = composeDesignSurfaceClassName('geek', 'sm');
    expect(className).toContain('min-w-0');
    expect(className).toContain('p-3');
    expect(className).toContain('font-mono');
  });

  it('uses geek nested card chrome when theme is active', () => {
    const geekCard = composeThemedCardClassName('geek', 'default');
    expect(geekCard).toContain('border-emerald-400/30');
    expect(geekCard).toContain('bg-slate-950/80');
    expect(geekCard).not.toContain('bg-surface-elevated');
  });
});
