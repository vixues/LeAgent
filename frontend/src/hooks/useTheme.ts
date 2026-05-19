import { useCallback, useEffect, useState } from 'react';
import { useThemeStore, resolveTheme, applyThemeToDocument } from '@/stores/theme';
import { useSettingsStore } from '@/stores/settingsStore';

export type Theme = 'light' | 'dark' | 'system';

/** Maps ThemeColors keys to CSS variable names in globals.css */
const THEME_COLOR_CSS_VARS: Record<keyof ThemeColors, string> = {
  primary: '--color-primary',
  secondary: '--color-text-secondary',
  background: '--color-background',
  foreground: '--color-text',
  muted: '--color-text-secondary',
  accent: '--color-primary',
  destructive: '--color-text',
  border: '--color-border',
  ring: '--color-primary',
};

export interface ThemeColors {
  primary: string;
  secondary: string;
  background: string;
  foreground: string;
  muted: string;
  accent: string;
  destructive: string;
  border: string;
  ring: string;
}

export interface ThemeState {
  theme: Theme;
  resolvedTheme: 'light' | 'dark';
  systemTheme: 'light' | 'dark';
  isSystemPreference: boolean;
}

export interface UseThemeReturn extends ThemeState {
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
  setLightTheme: () => void;
  setDarkTheme: () => void;
  setSystemTheme: () => void;
  applyTheme: (theme: 'light' | 'dark') => void;
}

function getSystemTheme(): 'light' | 'dark' {
  if (typeof window === 'undefined') return 'light';
  return resolveTheme('system');
}

export function useTheme(): UseThemeReturn {
  const { theme, setTheme: setStoreTheme } = useThemeStore();
  useSettingsStore();

  const [systemTheme, setSystemTheme] = useState<'light' | 'dark'>(getSystemTheme);

  const resolvedTheme = theme === 'system' ? systemTheme : theme;
  const isSystemPreference = theme === 'system';

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

    const handleChange = (event: MediaQueryListEvent) => {
      setSystemTheme(event.matches ? 'dark' : 'light');
    };

    setSystemTheme(mediaQuery.matches ? 'dark' : 'light');

    if (mediaQuery.addEventListener) {
      mediaQuery.addEventListener('change', handleChange);
      return () => mediaQuery.removeEventListener('change', handleChange);
    } else {
      mediaQuery.addListener(handleChange);
      return () => mediaQuery.removeListener(handleChange);
    }
  }, []);

  const setTheme = useCallback(
    (newTheme: Theme) => {
      setStoreTheme(newTheme);
    },
    [setStoreTheme]
  );

  const toggleTheme = useCallback(() => {
    if (theme === 'system') {
      setTheme(systemTheme === 'dark' ? 'light' : 'dark');
    } else {
      setTheme(theme === 'dark' ? 'light' : 'dark');
    }
  }, [theme, systemTheme, setTheme]);

  const setLightTheme = useCallback(() => setTheme('light'), [setTheme]);
  const setDarkTheme = useCallback(() => setTheme('dark'), [setTheme]);
  const setSystemThemePreference = useCallback(() => setTheme('system'), [setTheme]);

  const applyTheme = useCallback((newTheme: 'light' | 'dark') => {
    applyThemeToDocument(newTheme);
  }, []);

  return {
    theme,
    resolvedTheme,
    systemTheme,
    isSystemPreference,
    setTheme,
    toggleTheme,
    setLightTheme,
    setDarkTheme,
    setSystemTheme: setSystemThemePreference,
    applyTheme,
  };
}

export function useThemeColor(colorKey: keyof ThemeColors): string {
  const { resolvedTheme } = useTheme();
  const [color, setColor] = useState<string>('');

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const cssVarName = THEME_COLOR_CSS_VARS[colorKey];
    const computedStyle = getComputedStyle(document.documentElement);
    const value = computedStyle.getPropertyValue(cssVarName).trim();
    setColor(value || '');
  }, [colorKey, resolvedTheme]);

  return color;
}

export function useThemeTransition(duration: number = 200): {
  isTransitioning: boolean;
  startTransition: () => void;
} {
  const [isTransitioning, setIsTransitioning] = useState(false);

  const startTransition = useCallback(() => {
    if (typeof document === 'undefined') return;

    setIsTransitioning(true);
    document.documentElement.classList.add('theme-transitioning');

    setTimeout(() => {
      setIsTransitioning(false);
      document.documentElement.classList.remove('theme-transitioning');
    }, duration);
  }, [duration]);

  return { isTransitioning, startTransition };
}

export default useTheme;
