import { Link, Navigate, useParams } from "react-router-dom";
import { useMemo } from "react";
import { useI18n } from "@/i18n/I18nProvider";
import { MarkdownDoc } from "@/components/MarkdownDoc";
import { useDocumentMeta } from "@/hooks/useDocumentMeta";
import { SITE_ORIGIN } from "@/lib/content";
import {
  articlePath,
  getArticle,
  getNeighbors,
  getSection,
  resolveTutorialMarkdown,
  type TutorialSectionId,
} from "@/lib/tutorials";

const VALID_SECTIONS = new Set<TutorialSectionId>([
  "intro",
  "interview",
  "agent",
  "technical",
]);

interface TutorialArticleProps {
  /** Fixed section when routed without :section param (intro). */
  fixedSection?: TutorialSectionId;
  /** Default slug when section index route has no :slug. */
  defaultSlug?: string;
}

function extractDescription(md: string): string {
  const withoutHeading = md.replace(/^#[^\n]*\n+/, "");
  const para = withoutHeading
    .split(/\n\n+/)
    .map((p) => p.replace(/^>\s?/gm, "").replace(/[#*_`[\]]/g, "").trim())
    .find((p) => p.length > 40);
  if (!para) return "";
  return para.length > 160 ? `${para.slice(0, 157)}…` : para;
}

export default function TutorialArticle({
  fixedSection,
  defaultSlug,
}: TutorialArticleProps) {
  const { section: sectionParam, slug: slugParam } = useParams<{
    section?: string;
    slug?: string;
  }>();
  const { lang, t } = useI18n();

  const sectionId = (fixedSection ?? sectionParam) as
    | TutorialSectionId
    | undefined;

  const section =
    sectionId && VALID_SECTIONS.has(sectionId)
      ? getSection(sectionId)
      : undefined;

  let slug = slugParam ?? defaultSlug ?? "index";
  if (
    section &&
    sectionId === "technical" &&
    (slug === "index" || !getArticle("technical", slug))
  ) {
    slug = section.articles[0]?.slug ?? slug;
  }

  const article =
    sectionId === "intro"
      ? section?.articles[0]
      : sectionId
        ? getArticle(sectionId, slug)
        : undefined;

  const resolved =
    sectionId && article
      ? resolveTutorialMarkdown(sectionId, article.slug, lang)
      : null;

  const neighbors =
    sectionId && article
      ? getNeighbors(sectionId, article.slug)
      : { prev: null, next: null };

  const path =
    sectionId && article ? articlePath(sectionId, article.slug) : "/tutorials";
  const title = article?.title[lang] ?? "";
  const sectionTitle = section?.title[lang] ?? "";
  const pageTitle = article
    ? `${title} · ${sectionTitle} · LeAgent`
    : "LeAgent";
  const description =
    (resolved ? extractDescription(resolved.markdown) : "") ||
    section?.description[lang] ||
    "";

  const jsonLd = useMemo(() => {
    if (!section || !article || !resolved) return undefined;
    return [
      {
        "@context": "https://schema.org",
        "@type": "TechArticle",
        headline: title,
        description,
        inLanguage: resolved.zhOnlyShown ? "zh-CN" : lang,
        url: `${SITE_ORIGIN}${path}`,
        author: {
          "@type": "Organization",
          name: "LeAgent contributors",
        },
        isPartOf: {
          "@type": "CollectionPage",
          name: sectionTitle,
          url: `${SITE_ORIGIN}${section.path}`,
        },
      },
      {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        itemListElement: [
          {
            "@type": "ListItem",
            position: 1,
            name: t.nav.tutorials,
            item: `${SITE_ORIGIN}/tutorials`,
          },
          {
            "@type": "ListItem",
            position: 2,
            name: sectionTitle,
            item: `${SITE_ORIGIN}${section.path}`,
          },
          {
            "@type": "ListItem",
            position: 3,
            name: title,
            item: `${SITE_ORIGIN}${path}`,
          },
        ],
      },
    ];
  }, [
    article,
    description,
    lang,
    path,
    resolved,
    section,
    sectionTitle,
    t.nav.tutorials,
    title,
  ]);

  useDocumentMeta({
    title: pageTitle,
    description: description || "LeAgent tutorials",
    path,
    type: "article",
    jsonLd,
  });

  // Redirect technical section root to first article path for clean URLs
  if (
    sectionId === "technical" &&
    !slugParam &&
    article &&
    article.slug !== "index"
  ) {
    return <Navigate to={articlePath("technical", article.slug)} replace />;
  }

  if (!sectionId || !VALID_SECTIONS.has(sectionId) || !section || !article) {
    return <Navigate to="/tutorials" replace />;
  }

  if (!resolved) {
    return <Navigate to="/tutorials" replace />;
  }

  const { prev, next } = neighbors;

  return (
    <article>
      <nav className="docs-breadcrumb" aria-label="Breadcrumb">
        <Link to="/tutorials">{t.nav.tutorials}</Link>
        <span aria-hidden="true">/</span>
        <Link to={section.path}>{sectionTitle}</Link>
        <span aria-hidden="true">/</span>
        <span className="docs-breadcrumb__current">{title}</span>
      </nav>

      {resolved.zhOnlyShown && (
        <p className="docs-lang-note" role="status">
          {t.tutorials.zhOnlyNote}
        </p>
      )}

      <MarkdownDoc markdown={resolved.markdown} sectionId={sectionId} />

      <nav className="docs-pager" aria-label={t.tutorials.pagerLabel}>
        {prev ? (
          <Link
            to={articlePath(sectionId, prev.slug)}
            className="docs-pager__link docs-pager__link--prev"
          >
            <span className="docs-pager__label">{t.tutorials.prev}</span>
            <span className="docs-pager__title">{prev.title[lang]}</span>
          </Link>
        ) : (
          <span />
        )}
        {next ? (
          <Link
            to={articlePath(sectionId, next.slug)}
            className="docs-pager__link docs-pager__link--next"
          >
            <span className="docs-pager__label">{t.tutorials.next}</span>
            <span className="docs-pager__title">{next.title[lang]}</span>
          </Link>
        ) : (
          <span />
        )}
      </nav>
    </article>
  );
}
