import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type ThemePreference = 'light' | 'dark' | 'system';

export function resolveTheme(theme: ThemePreference): 'light' | 'dark' {
  if (theme === 'system') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  return theme;
}

export function applyThemeToDocument(resolved: 'light' | 'dark'): void {
  const root = document.documentElement;
  root.classList.remove('light', 'dark');
  root.classList.add(resolved);
  root.style.colorScheme = resolved;

  const metaThemeColor = document.querySelector('meta[name="theme-color"]');
  if (metaThemeColor) {
    metaThemeColor.setAttribute(
      'content',
      resolved === 'dark' ? '#09090a' : '#fcfcf9'
    );
  }
}

let systemPreferenceListenerAttached = false;

function ensureSystemPreferenceListener(): void {
  if (typeof window === 'undefined' || systemPreferenceListenerAttached) return;
  systemPreferenceListenerAttached = true;

  const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

  const onSystemPreferenceChange = () => {
    const { theme } = useThemeStore.getState();
    if (theme === 'system') {
      applyThemeToDocument(resolveTheme('system'));
    }
  };

  if (mediaQuery.addEventListener) {
    mediaQuery.addEventListener('change', onSystemPreferenceChange);
  } else {
    mediaQuery.addListener(onSystemPreferenceChange);
  }
}

interface ThemeState {
  theme: ThemePreference;
  setTheme: (theme: ThemePreference) => void;
  initializeTheme: () => void;
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      theme: 'system',
      setTheme: (theme) => {
        set({ theme });
        applyThemeToDocument(resolveTheme(theme));
      },
      initializeTheme: () => {
        const { theme } = get();
        applyThemeToDocument(resolveTheme(theme));
        ensureSystemPreferenceListener();
      },
    }),
    {
      name: 'leagent-theme',
    }
  )
);
