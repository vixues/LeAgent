import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import rehypeHighlight from 'rehype-highlight';
import { cn } from '@/lib/utils';
import { CodeBlock } from './CodeBlock';
import { MermaidDiagram } from './MermaidDiagram';
import { ChatImage } from '@/components/chat/media/ChatImage';
import { ChatInlineVideo } from '@/components/chat/media/ChatInlineVideo';
import { ChatRtspStream } from '@/components/chat/media/ChatRtspStream';
import {
  isChatRenderableImageSrc,
  isProbablyVideoUrl,
  isRtspUrl,
  resolveMarkdownImageSrcFromAttachments,
} from '@/components/chat/media/chatMediaUtils';
import { resolveCodingProjectPreviewHref } from '@/lib/previewUrl';
import type { Attachment } from '@/types/chat';

interface MarkdownProps {
  content: string;
  className?: string;
  /** Comfortable reading width & heading rhythm for docs / skill bodies (modal, guides). */
  variant?: 'default' | 'article';
  /**
   * When markdown image ``src`` is a bare filename (e.g. tool-saved ``plot.png``), resolve it
   * against these session attachments so ``ChatImage`` gets a real preview URL.
   */
  imageAttachments?: readonly Attachment[];
  /**
   * Hot streaming row. While true we (a) skip ``rehype-highlight`` so code fences
   * are not re-tokenised on every token, and (b) throttle the markdown re-parse
   * to ~10 Hz instead of the ~60 Hz rAF content flush. A final highlighted parse
   * runs once this flips back to ``false`` at stream end.
   */
  streaming?: boolean;
}

/** Throttle the parsed content to ``intervalMs`` while streaming; flush immediately when streaming stops. */
const STREAMING_PARSE_INTERVAL_MS = 100;

function useThrottledContent(content: string, streaming: boolean): string {
  const [throttled, setThrottled] = useState(content);
  const latestRef = useRef(content);
  const lastFlushRef = useRef(0);
  const timerRef = useRef<number | null>(null);
  latestRef.current = content;

  useEffect(() => {
    if (!streaming) {
      if (timerRef.current != null) {
        window.clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      setThrottled(content);
      return;
    }
    const now = Date.now();
    const elapsed = now - lastFlushRef.current;
    if (elapsed >= STREAMING_PARSE_INTERVAL_MS) {
      lastFlushRef.current = now;
      setThrottled(latestRef.current);
    } else if (timerRef.current == null) {
      timerRef.current = window.setTimeout(() => {
        timerRef.current = null;
        lastFlushRef.current = Date.now();
        setThrottled(latestRef.current);
      }, STREAMING_PARSE_INTERVAL_MS - elapsed);
    }
  }, [content, streaming]);

  useEffect(
    () => () => {
      if (timerRef.current != null) window.clearTimeout(timerRef.current);
    },
    [],
  );

  return streaming ? throttled : content;
}

/** Long-form docs / skill SKILL.md body — tuned for modals and guides. */
const ARTICLE_PROSE = cn(
  'prose prose-sm dark:prose-invert max-w-none antialiased',
  'selection:bg-primary-500/18 selection:text-foreground',
  'prose-headings:font-semibold prose-headings:text-foreground prose-headings:tracking-tight prose-headings:scroll-mt-24',
  'prose-h1:text-[1.65rem] prose-h1:leading-snug prose-h1:mt-8 prose-h1:mb-5 prose-h1:pb-3 prose-h1:border-b prose-h1:border-border/70',
  'prose-h2:text-xl prose-h2:mt-10 prose-h2:mb-3 prose-h2:pb-1 prose-h2:border-b prose-h2:border-border/40',
  'prose-h3:text-lg prose-h3:mt-8 prose-h3:mb-2.5',
  'prose-h4:text-base prose-h4:mt-7 prose-h4:mb-2',
  'prose-p:leading-[1.78] prose-p:text-foreground/[0.92] prose-p:my-[1.1em]',
  'prose-strong:text-foreground prose-strong:font-semibold',
  'prose-a:text-primary-600 dark:prose-a:text-primary-400 prose-a:no-underline hover:prose-a:underline prose-a:font-medium prose-a:break-words prose-a:underline-offset-2',
  'prose-code:before:content-none prose-code:after:content-none',
  'prose-code:bg-surface-sunken prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded-md prose-code:text-[0.9em] prose-code:font-mono prose-code:font-normal prose-code:whitespace-pre-wrap prose-code:break-words',
  'prose-li:leading-relaxed prose-li:my-1',
  '[&_kbd]:rounded [&_kbd]:border [&_kbd]:border-border/80 [&_kbd]:bg-surface-sunken [&_kbd]:px-1.5 [&_kbd]:py-0.5 [&_kbd]:text-xs [&_kbd]:font-mono'
);

interface MdNode {
  type: string;
  value?: string;
  children?: MdNode[];
  data?: {
    hName?: string;
    hProperties?: Record<string, unknown>;
  };
}

/** Supported callout / admonition kinds → display title. */
const CALLOUT_TITLES: Record<string, string> = {
  note: 'Note',
  info: 'Info',
  tip: 'Tip',
  success: 'Success',
  warning: 'Warning',
  caution: 'Caution',
  danger: 'Danger',
  important: 'Important',
};

function normalizeCalloutType(raw: string): string {
  const t = raw.toLowerCase();
  return t in CALLOUT_TITLES ? t : 'note';
}

/**
 * Build a callout as a real ``div`` (via mdast → hast ``hName``) so that the
 * body keeps its parsed markdown — links, bold, inline code, nested lists —
 * and flows through the same themed component overrides as the rest of chat.
 */
function makeCalloutNode(type: string, body: MdNode[]): MdNode {
  const title: MdNode = {
    type: 'paragraph',
    data: { hName: 'div', hProperties: { className: ['chat-callout-title'] } },
    children: [{ type: 'text', value: CALLOUT_TITLES[type] ?? 'Note' }],
  };
  return {
    type: 'blockquote',
    data: {
      hName: 'div',
      hProperties: { className: ['chat-callout', `chat-callout-${type}`] },
    },
    children: [title, ...body],
  };
}

/**
 * Remark plugin for admonitions. Supports two authoring styles:
 *   • GitHub-style alerts:  ``> [!NOTE]`` / ``[!TIP]`` / ``[!WARNING]`` …
 *   • Container syntax:     ``:::note … :::`` (single- or multi-paragraph)
 * Both render through the themed ``.chat-callout`` styles with markdown intact.
 */
function remarkCallouts() {
  return (tree: MdNode) => {
    const children = tree.children;
    if (!children) return;
    const out: MdNode[] = [];

    for (let i = 0; i < children.length; i++) {
      const node = children[i]!;

      // 1) GitHub-style alerts inside a blockquote: > [!NOTE]
      if (node.type === 'blockquote' && node.children && node.children.length > 0) {
        const firstPara = node.children[0]!;
        const firstText = firstPara.children?.[0];
        if (
          firstPara.type === 'paragraph' &&
          firstText &&
          firstText.type === 'text' &&
          typeof firstText.value === 'string'
        ) {
          const m = firstText.value.match(/^\[!(\w+)\][ \t]*(?:\r?\n)?/);
          if (m) {
            const type = normalizeCalloutType(m[1]!);
            firstText.value = firstText.value.slice(m[0].length);
            if (firstText.value === '') firstPara.children!.shift();
            if (!firstPara.children || firstPara.children.length === 0) {
              node.children!.shift();
            }
            out.push(makeCalloutNode(type, node.children!));
            continue;
          }
        }
      }

      // 2) Container syntax: :::note … :::
      if (node.type === 'paragraph' && node.children && node.children.length > 0) {
        const firstText = node.children[0]!;
        if (firstText.type === 'text' && typeof firstText.value === 'string') {
          const open = firstText.value.match(/^:::(\w+)[ \t]*(?:\r?\n)?/);
          if (open) {
            const type = normalizeCalloutType(open[1]!);
            const last = node.children[node.children.length - 1]!;
            const closesHere =
              node.children.length >= 1 &&
              last.type === 'text' &&
              typeof last.value === 'string' &&
              /\r?\n?:::[ \t]*$/.test(last.value);

            if (closesHere) {
              firstText.value = firstText.value.slice(open[0].length);
              last.value = last.value!.replace(/\r?\n?:::[ \t]*$/, '');
              const inner = node.children.filter(
                (c) => !(c.type === 'text' && c.value === ''),
              );
              out.push(makeCalloutNode(type, [{ type: 'paragraph', children: inner }]));
              continue;
            }

            // Multi-paragraph container: scan forward for a lone ``:::`` line.
            let close = -1;
            for (let j = i + 1; j < children.length; j++) {
              const cand = children[j]!;
              const ct = cand.children?.[0];
              if (
                cand.type === 'paragraph' &&
                cand.children?.length === 1 &&
                ct?.type === 'text' &&
                typeof ct.value === 'string' &&
                ct.value.trim() === ':::'
              ) {
                close = j;
                break;
              }
            }
            if (close !== -1) {
              firstText.value = firstText.value.slice(open[0].length);
              const body: MdNode[] = [];
              if (firstText.value.trim() !== '') {
                body.push(node);
              } else if (node.children.length > 1) {
                node.children.shift();
                body.push(node);
              }
              for (let j = i + 1; j < close; j++) body.push(children[j]!);
              out.push(makeCalloutNode(type, body));
              i = close;
              continue;
            }
          }
        }
      }

      out.push(node);
    }

    tree.children = out;
  };
}

function extractLanguage(classNames?: string[]): string | undefined {
  if (!classNames) return undefined;
  for (const cls of classNames) {
    const match = cls.match(/language-(\w+)/);
    if (match) return match[1];
  }
  return undefined;
}

function extractTextContent(nodes?: Array<{ value?: string; children?: Array<{ value?: string; children?: unknown[] }> }>): string {
  if (!nodes) return '';
  let text = '';
  for (const node of nodes) {
    if (node.value) {
      text += node.value;
    } else if (node.children) {
      text += extractTextContent(node.children as typeof nodes);
    }
  }
  return text;
}

/**
 * Canonical Markdown renderer for the chat interface.
 * Full GFM + KaTeX math + Mermaid diagrams + syntax highlighting +
 * callouts + line numbers + copy/download on code blocks.
 *
 * Use `variant="article"` for long-form skill bodies and docs modals (clear hierarchy & rhythm).
 */
/**
 * Strip any residual ``<think>…</think>`` blocks from content before rendering.
 * These should normally be removed by the backend (parse_think_tags), but may
 * leak through when a provider is configured without tag-parsing enabled.
 */
function stripThinkTags(text: string): string {
  if (!text.includes('<think>')) return text;
  return text.replace(/<think>[\s\S]*?<\/think>/gi, '').replace(/^\n+/, '');
}

export function Markdown({
  content,
  className,
  variant = 'default',
  imageAttachments,
  streaming = false,
}: MarkdownProps) {
  const parseContent = useThrottledContent(content, streaming);
  const safeContent = useMemo(() => stripThinkTags(parseContent), [parseContent]);
  const remarkPlugins = useMemo(
    () => [remarkGfm, remarkMath, remarkCallouts],
    [],
  );
  // Defer both KaTeX and syntax highlighting until the stream settles. Both
  // `rehype-katex` and `rehype-highlight` re-process the whole subtree on every
  // parse; running them at streaming cadence dominates CPU for math/code-heavy
  // replies. While streaming we render raw markdown only and apply the final
  // typeset/highlight pass once `streaming` flips back to `false`.
  const rehypePlugins = useMemo(
    () => (streaming ? [] : [rehypeKatex, rehypeHighlight]),
    [streaming],
  );

  const components = useMemo(
    () => ({
      pre: ({ children, node, ...rest }: { children?: ReactNode; node?: { children?: unknown[] }; [key: string]: unknown }) => {
        const wrap = (nodeInner: ReactNode) =>
          variant === 'article' ? (
            <div className="not-prose my-5 w-full min-w-0">{nodeInner}</div>
          ) : (
            nodeInner
          );

        if (node?.children?.length === 1) {
          const codeEl = node.children[0] as {
            tagName?: string;
            properties?: Record<string, unknown>;
            children?: Array<{ value?: string }>;
          };
          if (codeEl.tagName === 'code') {
            const classNames = (codeEl.properties?.className as string[]) ?? [];
            const lang = extractLanguage(classNames);

            if (lang === 'mermaid') {
              const text = extractTextContent(codeEl.children as Parameters<typeof extractTextContent>[0]);
              return wrap(<MermaidDiagram source={text.trim()} />);
            }

            return wrap(
              <CodeBlock language={lang}>
                <code
                  className={cn((codeEl.properties?.className as string[])?.join(' '), 'font-mono')}
                >
                  {children}
                </code>
              </CodeBlock>
            );
          }
        }
        return wrap(<pre {...rest}>{children}</pre>);
      },
      code: ({ className: cls, children, ...rest }: { className?: string; children?: ReactNode }) => {
        const isInline = !cls;
        if (isInline) {
          return (
            <code
              className={cn(
                'rounded-md font-mono',
                variant === 'article'
                  ? 'bg-surface-sunken px-1.5 py-0.5 text-[0.9em] text-foreground/95'
                  : 'bg-surface-sunken px-1.5 py-0.5 text-sm'
              )}
              {...rest}
            >
              {children}
            </code>
          );
        }
        return (
          <code className={cn(cls, 'font-mono')} {...rest}>
            {children}
          </code>
        );
      },
      a: ({ href, children }: { href?: string; children?: ReactNode }) => {
        const resolved = href ? resolveCodingProjectPreviewHref(href) : href;
        if (resolved && isRtspUrl(resolved)) {
          const label = typeof children === 'string' ? children : undefined;
          return <ChatRtspStream src={resolved} title={label} />;
        }
        if (resolved && isProbablyVideoUrl(resolved)) {
          return <ChatInlineVideo src={resolved} />;
        }
        return (
          <a
            href={resolved}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary-600 dark:text-primary-400 hover:underline"
          >
            {children}
          </a>
        );
      },
      img: ({ src, alt }: { src?: string; alt?: string }) => {
        const resolved =
          resolveMarkdownImageSrcFromAttachments(src, imageAttachments, alt) ?? src ?? '';
        if (!resolved.trim() || !isChatRenderableImageSrc(resolved)) {
          return (
            <span className="inline-flex max-w-full rounded-md bg-surface-sunken px-2 py-1 text-xs text-muted-foreground">
              {typeof alt === 'string' && alt.trim() ? alt : 'Image unavailable'}
            </span>
          );
        }
        return (
          <span
            className={cn(
              'block max-w-full',
              variant === 'article' ? 'my-5 rounded-lg ring-1 ring-border/40 overflow-hidden' : 'my-3'
            )}
          >
            <ChatImage src={resolved} alt={typeof alt === 'string' ? alt : ''} />
          </span>
        );
      },
      ul: ({ children }: { children?: ReactNode }) => (
        <ul
          className={
            variant === 'article'
              ? 'my-5 space-y-2.5 pl-5 list-disc marker:text-muted-foreground text-foreground/90 [&_ul]:mt-2'
              : 'list-disc pl-5 space-y-1 my-2'
          }
        >
          {children}
        </ul>
      ),
      ol: ({ children }: { children?: ReactNode }) => (
        <ol
          className={
            variant === 'article'
              ? 'my-5 space-y-2.5 pl-5 list-decimal marker:text-muted-foreground text-foreground/90 [&_ol]:mt-2'
              : 'list-decimal pl-5 space-y-1 my-2'
          }
        >
          {children}
        </ol>
      ),
      hr: () => <hr className={variant === 'article' ? 'my-10 border-border/70' : 'my-4 border-border'} />,
      blockquote: ({ children }: { children?: ReactNode }) => (
        <blockquote
          className={
            variant === 'article'
              ? 'border-l-[3px] border-primary-500/70 bg-primary-500/[0.06] py-3 px-4 my-6 rounded-r-lg text-foreground/90 not-italic [&_p]:my-2 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0'
              : 'border-l-4 border-primary-300 dark:border-primary-600 pl-4 my-2 italic text-muted-foreground'
          }
        >
          {children}
        </blockquote>
      ),
      table: ({ children }: { children?: ReactNode }) => (
        <div
          className={
            variant === 'article'
              ? 'not-prose overflow-x-auto my-7 rounded-xl ring-1 ring-border/55 bg-surface/40 shadow-sm'
              : 'overflow-x-auto my-3 rounded-lg ring-1 ring-border-subtle'
          }
        >
          <table
            className={
              variant === 'article'
                ? 'min-w-full divide-y divide-border/70 text-[0.9375rem] leading-snug'
                : 'min-w-full divide-y divide-border overflow-hidden text-sm'
            }
          >
            {children}
          </table>
        </div>
      ),
      thead: ({ children }: { children?: ReactNode }) =>
        variant === 'article' ? (
          <thead className="bg-surface-sunken/90 [&_th]:border-b [&_th]:border-border/60">{children}</thead>
        ) : (
          <thead>{children}</thead>
        ),
      tbody: ({ children }: { children?: ReactNode }) =>
        variant === 'article' ? (
          <tbody className="divide-y divide-border/45 [&_tr:nth-child(even)]:bg-surface-sunken/25">{children}</tbody>
        ) : (
          <tbody>{children}</tbody>
        ),
      tr: ({ children }: { children?: ReactNode }) => <tr className={variant === 'article' ? 'transition-colors hover:bg-primary-500/[0.04]' : ''}>{children}</tr>,
      th: ({ children }: { children?: ReactNode }) => (
        <th
          className={
            variant === 'article'
              ? 'px-4 py-3 text-left text-[0.7rem] font-semibold uppercase tracking-wide text-muted-foreground'
              : 'px-3 py-2.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider bg-surface-sunken/80'
          }
        >
          {children}
        </th>
      ),
      td: ({ children }: { children?: ReactNode }) => (
        <td
          className={
            variant === 'article'
              ? 'px-4 py-3 text-foreground/90 align-top border-0'
              : 'px-3 py-2.5 text-sm text-foreground border-t border-border-subtle align-top'
          }
        >
          {children}
        </td>
      ),
      input: ({ type, checked, ...rest }: { type?: string; checked?: boolean }) => {
        if (type === 'checkbox') {
          return (
            <input
              type="checkbox"
              checked={checked}
              readOnly
              className="mr-1.5 rounded accent-primary-500"
              {...rest}
            />
          );
        }
        return <input type={type} {...rest} />;
      },
      details: ({ children }: { children?: ReactNode }) => (
        <details
          className={
            variant === 'article'
              ? 'my-5 rounded-lg border border-border/80 bg-surface-sunken/30 [&>summary]:cursor-pointer [&>summary]:list-none [&>summary::-webkit-details-marker]:hidden [&>summary]:px-4 [&>summary]:py-3 [&>summary]:text-sm [&>summary]:font-semibold [&>summary]:text-foreground'
              : 'my-2 rounded-lg border border-border-subtle bg-surface-sunken/20 [&>summary]:cursor-pointer [&>summary]:px-3 [&>summary]:py-2 [&>summary]:text-sm [&>summary]:font-medium'
          }
        >
          {children}
        </details>
      ),
    }) as unknown as Components,
    [variant, imageAttachments],
  );

  // Reuse the same element reference between throttle flushes so React skips
  // reconciling (and re-parsing) the markdown subtree on every parent render.
  const rendered = useMemo(
    () => (
      <ReactMarkdown remarkPlugins={remarkPlugins} rehypePlugins={rehypePlugins} components={components}>
        {safeContent}
      </ReactMarkdown>
    ),
    [safeContent, remarkPlugins, rehypePlugins, components],
  );

  return (
    <div
      className={cn(
        'max-w-none break-words',
        variant === 'article' && ARTICLE_PROSE,
        className
      )}
    >
      {rendered}
    </div>
  );
}
