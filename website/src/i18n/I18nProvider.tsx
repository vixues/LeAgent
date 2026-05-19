import {
  createContext,
  useContext,
  useState,
  useCallback,
  useMemo,
  type ReactNode,
} from "react";
import { translations, type Lang } from "./translations";

const STORAGE_KEY = "leagent-site-language";
const DEFAULT_LANG: Lang = "zh-CN";

function getInitialLang(): Lang {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "zh-CN" || stored === "en-US") return stored;
  } catch {}
  return DEFAULT_LANG;
}

type Translations = (typeof translations)["zh-CN"];

interface I18nContextValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  toggleLang: () => void;
  t: Translations;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(getInitialLang);

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {}
    document.documentElement.lang = next === "zh-CN" ? "zh-CN" : "en";
  }, []);

  const toggleLang = useCallback(() => {
    setLang(lang === "zh-CN" ? "en-US" : "zh-CN");
  }, [lang, setLang]);

  const t = useMemo(() => translations[lang], [lang]);

  const value = useMemo(
    () => ({ lang, setLang, toggleLang, t }),
    [lang, setLang, toggleLang, t],
  );

  return <I18nContext value={value}>{children}</I18nContext>;
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}
