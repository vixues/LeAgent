import { describe, it, expect, beforeEach } from 'vitest';
import { useThemeStore } from './theme';

describe('useThemeStore', () => {
  beforeEach(() => {
    useThemeStore.setState({ theme: 'light' });
    localStorage.clear();
    document.documentElement.classList.remove('dark', 'light');
  });

  it('should have light as default theme', () => {
    const { theme } = useThemeStore.getState();
    expect(theme).toBe('light');
  });

  it('should set theme to light', () => {
    const { setTheme } = useThemeStore.getState();
    setTheme('light');

    const { theme } = useThemeStore.getState();
    expect(theme).toBe('light');
  });

  it('should set theme to dark', () => {
    const { setTheme } = useThemeStore.getState();
    setTheme('dark');

    const { theme } = useThemeStore.getState();
    expect(theme).toBe('dark');
  });

  it('should set theme to system', () => {
    const { setTheme } = useThemeStore.getState();
    setTheme('dark');
    setTheme('system');

    const { theme } = useThemeStore.getState();
    expect(theme).toBe('system');
  });

  describe('initializeTheme', () => {
    it('should add dark class when theme is dark', () => {
      const { setTheme, initializeTheme } = useThemeStore.getState();
      setTheme('dark');
      initializeTheme();

      expect(document.documentElement.classList.contains('dark')).toBe(true);
    });

    it('should add light class when theme is light', () => {
      document.documentElement.classList.add('dark');

      const { setTheme, initializeTheme } = useThemeStore.getState();
      setTheme('light');
      initializeTheme();

      expect(document.documentElement.classList.contains('dark')).toBe(false);
      expect(document.documentElement.classList.contains('light')).toBe(true);
    });

    it('should respect system preference when theme is system', () => {
      Object.defineProperty(window, 'matchMedia', {
        writable: true,
        value: (query: string) => ({
          matches: query === '(prefers-color-scheme: dark)',
          media: query,
          onchange: null,
          addListener: () => {},
          removeListener: () => {},
          addEventListener: () => {},
          removeEventListener: () => {},
          dispatchEvent: () => false,
        }),
      });

      const { setTheme, initializeTheme } = useThemeStore.getState();
      setTheme('system');
      initializeTheme();

      expect(document.documentElement.classList.contains('dark')).toBe(true);
    });
  });
});
