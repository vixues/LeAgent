import { LICENSE_URL, REPO_RAW_BASE, REPO_URL } from "./content";
import {
  articlePath,
  type TutorialSectionId,
} from "./tutorials";

const SECTION_PREFIXES: Array<{
  pattern: RegExp;
  section: TutorialSectionId;
}> = [
  { pattern: /(?:^|\/)interview\//, section: "interview" },
  { pattern: /(?:^|\/)guides\/agent\//, section: "agent" },
  { pattern: /(?:^|\/)agent\//, section: "agent" },
  { pattern: /(?:^|\/)technical\//, section: "technical" },
];

/**
 * Rewrite relative image / asset paths so a uploaded dist/ is self-contained.
 * Prefer vendored /docs/assets/* (copied at build time); fall back to GitHub raw.
 */
export function rewriteAssetSrc(src: string | undefined): string | undefined {
  if (!src) return src;
  if (
    src.startsWith("http://") ||
    src.startsWith("https://") ||
    src.startsWith("data:") ||
    src.startsWith("/")
  ) {
    // Already absolute site path or remote — keep. If someone baked a raw GitHub
    // docs/assets URL, map back to local vendored copy when possible.
    const localFromRaw = src.match(
      /raw\.githubusercontent\.com\/[^/]+\/[^/]+\/[^/]+\/(docs\/assets\/.+)$/i,
    );
    if (localFromRaw?.[1]) {
      return `/${localFromRaw[1]}`;
    }
    return src;
  }

  // GitHub Actions badge quirks in README: ../../actions/.../badge.svg
  if (src.includes("actions/workflows/") && src.endsWith("badge.svg")) {
    const workflow = src.match(/actions\/workflows\/([^/]+)/)?.[1];
    if (workflow) {
      return `${REPO_URL}/actions/workflows/${workflow}/badge.svg`;
    }
  }

  const cleaned = src.replace(/^\.\//, "").replace(/^(\.\.\/)+/, "");

  // README logo / hero screenshots — shipped inside dist via public/docs/assets
  if (cleaned.startsWith("docs/assets/")) {
    return `/${cleaned}`;
  }

  return `${REPO_RAW_BASE}/${cleaned}`;
}

/**
 * Prepare README / markdown HTML blobs before react-markdown + rehype-raw.
 * Rewrites relative src/href values that sit inside raw HTML tags.
 */
export function prepareMarkdownHtml(markdown: string): string {
  return markdown
    .replace(
      /\bsrc=(["'])([^"']+)\1/gi,
      (_m, quote: string, src: string) =>
        `src=${quote}${rewriteAssetSrc(src) ?? src}${quote}`,
    )
    .replace(
      /\bhref=(["'])(?!https?:|mailto:|#|\/)([^"']+)\1/gi,
      (_m, quote: string, href: string) => {
        const next = rewriteMarkdownHref(href, "intro") ?? href;
        if (next.startsWith("/")) {
          return `href=${quote}${next}${quote}`;
        }
        if (/^LICENSE$/i.test(href)) {
          return `href=${quote}${LICENSE_URL}${quote}`;
        }
        if (/^AGENTS\.md$/i.test(href)) {
          return `href=${quote}${REPO_URL}/blob/main/AGENTS.md${quote}`;
        }
        if (/^docs\//i.test(href) || /^backend\//i.test(href)) {
          return `href=${quote}${REPO_URL}/blob/main/${href}${quote}`;
        }
        return `href=${quote}${next}${quote}`;
      },
    );
}

/**
 * Rewrite relative markdown hrefs to in-site tutorial routes when possible.
 * External http(s) and in-page anchors are left untouched.
 */
export function rewriteMarkdownHref(
  href: string | undefined,
  currentSection: TutorialSectionId,
): string | undefined {
  if (!href) return href;
  if (
    href.startsWith("http://") ||
    href.startsWith("https://") ||
    href.startsWith("mailto:") ||
    href.startsWith("#") ||
    href.startsWith("/tutorials")
  ) {
    return href;
  }

  const [pathPart, hash = ""] = href.split("#");
  const path = pathPart ?? "";
  const suffix = hash ? `#${hash}` : "";

  // Root README links
  if (/^README(_zh|_lzh)?\.md$/i.test(path)) {
    return `/tutorials/intro${suffix}`;
  }

  if (/^docs\/tutorial(_zh)?\.md$/i.test(path)) {
    return `${REPO_URL}/blob/main/${path}${suffix}`;
  }

  if (/^AGENTS\.md$/i.test(path) || /^LICENSE$/i.test(path)) {
    return path.toUpperCase() === "LICENSE"
      ? LICENSE_URL
      : `${REPO_URL}/blob/main/AGENTS.md`;
  }

  // Detect section from path
  let section: TutorialSectionId | null = null;
  for (const { pattern, section: id } of SECTION_PREFIXES) {
    if (pattern.test(path)) {
      section = id;
      break;
    }
  }

  const base = path.split("/").pop() ?? "";
  if (!base.toLowerCase().endsWith(".md")) {
    if (/^(docs|backend|config|website|frontend|desktop)\//i.test(path)) {
      return `${REPO_URL}/blob/main/${path}${suffix}`;
    }
    return href;
  }

  let slug = base.replace(/\.md$/i, "");
  if (slug.toLowerCase() === "readme") {
    slug = "index";
  }

  if (section === "technical") {
    slug = slug.replace(/_zh$/i, "");
  }

  if (!section) {
    // Same-directory link inside current section
    section = currentSection;
  }

  if (section === "intro") {
    return `/tutorials/intro${suffix}`;
  }

  return `${articlePath(section, slug)}${suffix}`;
}
