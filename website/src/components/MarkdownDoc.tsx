import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import { Link } from "react-router-dom";
import type { Components } from "react-markdown";
import {
  prepareMarkdownHtml,
  rewriteAssetSrc,
  rewriteMarkdownHref,
} from "@/lib/mdLinks";
import type { TutorialSectionId } from "@/lib/tutorials";

interface MarkdownDocProps {
  markdown: string;
  sectionId: TutorialSectionId;
}

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\u4e00-\u9fff\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-");
}

function textFromChildren(children: ReactNode): string {
  if (typeof children === "string" || typeof children === "number") {
    return String(children);
  }
  if (Array.isArray(children)) {
    return children.map(textFromChildren).join("");
  }
  return "";
}

export function MarkdownDoc({ markdown, sectionId }: MarkdownDocProps) {
  const source =
    sectionId === "intro" ? prepareMarkdownHtml(markdown) : markdown;

  const components: Components = {
    a({ href, children }) {
      const rewritten = rewriteMarkdownHref(href, sectionId);
      if (!rewritten) {
        return <a>{children}</a>;
      }
      if (rewritten.startsWith("/")) {
        const [to, hash] = rewritten.split("#");
        return (
          <Link to={hash ? `${to}#${hash}` : (to ?? rewritten)}>
            {children}
          </Link>
        );
      }
      const external =
        rewritten.startsWith("http://") || rewritten.startsWith("https://");
      return (
        <a
          href={rewritten}
          {...(external
            ? { target: "_blank", rel: "noopener noreferrer" }
            : {})}
        >
          {children}
        </a>
      );
    },
    img({ src, alt, width, height }) {
      const resolved = rewriteAssetSrc(src) ?? src;
      const isBadge =
        typeof resolved === "string" &&
        (resolved.includes("img.shields.io") ||
          resolved.includes("badge.svg") ||
          resolved.includes("/badge."));
      return (
        <img
          src={resolved}
          alt={alt ?? ""}
          width={width}
          height={height}
          className={isBadge ? "docs-badge" : undefined}
          loading="lazy"
        />
      );
    },
    h1({ children }) {
      const text = textFromChildren(children);
      return <h1 id={slugify(text)}>{children}</h1>;
    },
    h2({ children }) {
      const text = textFromChildren(children);
      return <h2 id={slugify(text)}>{children}</h2>;
    },
    h3({ children }) {
      const text = textFromChildren(children);
      return <h3 id={slugify(text)}>{children}</h3>;
    },
    pre({ children }) {
      return <pre className="docs-code-block">{children}</pre>;
    },
    code({ className, children }) {
      const isBlock = Boolean(className);
      if (isBlock) {
        return <code className={className}>{children}</code>;
      }
      return <code className="docs-inline-code">{children}</code>;
    },
    table({ children }) {
      return (
        <div className="docs-table-wrap">
          <table>{children}</table>
        </div>
      );
    },
  };

  return (
    <div className="docs-prose">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw]}
        components={components}
      >
        {source}
      </ReactMarkdown>
    </div>
  );
}
