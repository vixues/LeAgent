import { useEffect } from "react";
import { SITE_ORIGIN } from "@/lib/content";

export interface DocumentMetaOptions {
  title: string;
  description: string;
  path: string;
  type?: "website" | "article";
  jsonLd?: Record<string, unknown> | Record<string, unknown>[];
}

function upsertMeta(
  selector: string,
  attrs: Record<string, string>,
  createTag: "meta" | "link" = "meta",
): void {
  let el = document.head.querySelector(selector) as
    | HTMLMetaElement
    | HTMLLinkElement
    | null;
  if (!el) {
    el = document.createElement(createTag);
    document.head.appendChild(el);
  }
  for (const [key, value] of Object.entries(attrs)) {
    el.setAttribute(key, value);
  }
}

function upsertJsonLd(data: Record<string, unknown> | Record<string, unknown>[]): void {
  const id = "leagent-jsonld";
  let el = document.getElementById(id) as HTMLScriptElement | null;
  if (!el) {
    el = document.createElement("script");
    el.id = id;
    el.type = "application/ld+json";
    document.head.appendChild(el);
  }
  el.textContent = JSON.stringify(data);
}

/**
 * Update document title / Open Graph / canonical for SPA routes.
 */
export function useDocumentMeta({
  title,
  description,
  path,
  type = "website",
  jsonLd,
}: DocumentMetaOptions): void {
  useEffect(() => {
    const url = `${SITE_ORIGIN.replace(/\/$/, "")}${path === "/" ? "/" : path}`;
    document.title = title;

    upsertMeta('meta[name="description"]', {
      name: "description",
      content: description,
    });
    upsertMeta('link[rel="canonical"]', { rel: "canonical", href: url }, "link");
    upsertMeta('meta[property="og:title"]', {
      property: "og:title",
      content: title,
    });
    upsertMeta('meta[property="og:description"]', {
      property: "og:description",
      content: description,
    });
    upsertMeta('meta[property="og:url"]', {
      property: "og:url",
      content: url,
    });
    upsertMeta('meta[property="og:type"]', {
      property: "og:type",
      content: type,
    });
    upsertMeta('meta[name="twitter:title"]', {
      name: "twitter:title",
      content: title,
    });
    upsertMeta('meta[name="twitter:description"]', {
      name: "twitter:description",
      content: description,
    });

    if (jsonLd) upsertJsonLd(jsonLd);
  }, [title, description, path, type, jsonLd]);
}
