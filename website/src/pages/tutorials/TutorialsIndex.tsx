import { Link } from "react-router-dom";
import { useI18n } from "@/i18n/I18nProvider";
import { useDocumentMeta } from "@/hooks/useDocumentMeta";
import { SITE_ORIGIN } from "@/lib/content";
import { TUTORIAL_SECTIONS } from "@/lib/tutorials";

export default function TutorialsIndex() {
  const { lang, t } = useI18n();

  useDocumentMeta({
    title: `${t.tutorials.indexTitle} · LeAgent`,
    description: t.tutorials.indexLede,
    path: "/tutorials",
    jsonLd: {
      "@context": "https://schema.org",
      "@type": "CollectionPage",
      name: t.tutorials.indexTitle,
      description: t.tutorials.indexLede,
      url: `${SITE_ORIGIN}/tutorials`,
      isPartOf: {
        "@type": "WebSite",
        name: "LeAgent",
        url: SITE_ORIGIN,
      },
      hasPart: TUTORIAL_SECTIONS.map((s) => ({
        "@type": "CollectionPage",
        name: s.title[lang],
        description: s.description[lang],
        url: `${SITE_ORIGIN}${s.path}`,
      })),
    },
  });

  return (
    <div>
      <p className="eyebrow mb-3">{t.tutorials.eyebrow}</p>
      <h1 className="font-display text-3xl font-semibold tracking-tight text-text-primary md:text-4xl">
        {t.tutorials.indexTitle}
      </h1>
      <p className="mt-4 max-w-2xl text-base leading-relaxed text-text-secondary">
        {t.tutorials.indexLede}
      </p>

      <div className="mt-10 grid gap-4 md:grid-cols-2">
        {TUTORIAL_SECTIONS.map((section) => (
          <Link
            key={section.id}
            to={section.path}
            className="docs-hub-card"
          >
            <span className="docs-hub-card__eyebrow">
              {section.articles.length}{" "}
              {lang === "zh-CN" ? "篇" : "pages"}
            </span>
            <h2 className="docs-hub-card__title">{section.title[lang]}</h2>
            <p className="docs-hub-card__body">{section.description[lang]}</p>
            <span className="docs-hub-card__cta">{t.tutorials.readSection}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
