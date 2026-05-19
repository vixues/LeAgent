import { useI18n } from "@/i18n/I18nProvider";

export function LanguageToggle() {
  const { lang, toggleLang } = useI18n();

  return (
    <button
      type="button"
      onClick={toggleLang}
      className="rounded px-2 py-1 font-mono text-sm text-text-muted transition-colors duration-200 hover:text-text-secondary"
      aria-label={lang === "zh-CN" ? "Switch to English" : "切换为中文"}
    >
      {lang === "zh-CN" ? "中/En" : "En/中"}
    </button>
  );
}
