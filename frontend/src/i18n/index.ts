import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

export type SupportedLng = 'zh-CN' | 'en-US';

const COOKIE_NAME = 'leagent-lang';
const STORAGE_KEY = 'leagent-language';

/** Namespaced bundle files merged into the single `translation` namespace (matches legacy `t('settings.title')`). */
export const TRANSLATION_BUNDLE_FILES = [
  'common',
  'nav',
  'auth',
  'dashboard',
  'workflows',
  'knowledge',
  'integrations',
  'chat',
  'settings',
  'admin',
  'modals',
  'errors',
  'docs',
  'accounts',
  'notifications',
  'pet',
  'about',
  'codingProjects',
] as const;

export type TranslationBundleName = (typeof TRANSLATION_BUNDLE_FILES)[number];

const loadedLanguages = new Set<string>();

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name.replace(/([.$?*|{}()[\]\\/+^])/g, '\\$1')}=([^;]*)`));
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

function normalizeLanguageCode(raw: string | undefined | null): SupportedLng {
  if (!raw) return 'zh-CN';
  const lower = raw.toLowerCase();
  if (lower === 'en' || lower.startsWith('en-')) return 'en-US';
  if (lower.startsWith('zh')) return 'zh-CN';
  return 'zh-CN';
}

/** Migrate legacy storage values before detection runs. */
function migrateLegacyLanguage(): void {
  if (typeof localStorage === 'undefined') return;
  const ls = localStorage.getItem(STORAGE_KEY);
  if (ls === 'en') localStorage.setItem(STORAGE_KEY, 'en-US');

  const c = readCookie(COOKIE_NAME);
  if (c === 'en') {
    persistLanguageChoice('en-US');
  }
}

/**
 * Detection order (aligned with i18next-browser-languagedetector): cookie → localStorage → navigator → html lang.
 */
export function resolveInitialLanguage(): SupportedLng {
  migrateLegacyLanguage();
  const fromCookie = readCookie(COOKIE_NAME);
  const fromLs =
    typeof localStorage !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null;
  const raw = fromCookie || fromLs;
  if (raw === 'zh-CN' || raw === 'en-US') return raw;
  if (raw === 'en') return 'en-US';

  if (typeof navigator !== 'undefined') {
    const nav = navigator.language || navigator.languages?.[0];
    return normalizeLanguageCode(nav);
  }

  return 'zh-CN';
}

export function persistLanguageChoice(lng: string): void {
  const normalized = lng === 'en' ? 'en-US' : lng;
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem(STORAGE_KEY, normalized);
  }
  if (typeof document !== 'undefined') {
    document.cookie = `${COOKIE_NAME}=${encodeURIComponent(normalized)}; Path=/; Max-Age=31536000; SameSite=Lax`;
    document.documentElement.lang = normalized;
  }
}

function syncDocumentMeta(): void {
  if (typeof document === 'undefined') return;
  const title = i18n.t('common.meta.appTitle');
  const desc = i18n.t('common.meta.appDescription');
  document.title = title;
  const meta = document.querySelector('meta[name="description"]');
  if (meta) meta.setAttribute('content', desc);
}

async function mergeTranslationBundles(lng: SupportedLng): Promise<Record<string, unknown>> {
  const merged: Record<string, unknown> = {};
  await Promise.all(
    TRANSLATION_BUNDLE_FILES.map(async (name) => {
      const mod = await import(`./locales/${lng}/${name}.json`);
      Object.assign(merged, mod.default as object);
    })
  );
  return merged;
}

/** Ensures all bundle JSON for `lng` is merged into the `translation` namespace (idempotent). */
export async function ensureTranslationForLanguage(lng: SupportedLng): Promise<void> {
  if (loadedLanguages.has(lng)) return;
  const translation = await mergeTranslationBundles(lng);
  i18n.addResourceBundle(lng, 'translation', translation, true, true);
  loadedLanguages.add(lng);
}

/**
 * Loads resources for `lng` if needed, then switches language (use from Settings / Header instead of bare `changeLanguage`).
 */
export async function changeAppLanguage(rawLng: string): Promise<void> {
  const lng = normalizeLanguageCode(rawLng) as SupportedLng;
  await ensureTranslationForLanguage(lng);
  await i18n.changeLanguage(lng);
}

/** @deprecated Use changeAppLanguage */
export async function ensureLocaleLoaded(lng: string): Promise<void> {
  await ensureTranslationForLanguage(normalizeLanguageCode(lng) as SupportedLng);
}

let initPromise: Promise<void> | null = null;

/** Idempotent — safe for main entry and Vitest (same module instance). */
export function initI18n(): Promise<void> {
  if (initPromise) return initPromise;
  initPromise = (async () => {
    const initialLng = resolveInitialLanguage();
    const translation = await mergeTranslationBundles(initialLng);

    loadedLanguages.add(initialLng);

    await i18n.use(initReactI18next).init({
      lng: initialLng,
      fallbackLng: 'zh-CN',
      supportedLngs: ['zh-CN', 'en-US'],
      load: 'currentOnly',
      ns: ['translation'],
      defaultNS: 'translation',
      resources: {
        [initialLng]: { translation },
      },
      interpolation: {
        escapeValue: false,
      },
      react: {
        useSuspense: false,
      },
      debug: import.meta.env.DEV,
    });

    syncDocumentMeta();

    i18n.on('languageChanged', () => {
      persistLanguageChoice(i18n.language);
      syncDocumentMeta();
    });

    persistLanguageChoice(i18n.language);
  })();

  return initPromise;
}

/** Re-export so `i18next-browser-languagedetector` stays linked to the same detection contract as `resolveInitialLanguage`. */
export { default as browserLanguageDetector } from 'i18next-browser-languagedetector';

export default i18n;
