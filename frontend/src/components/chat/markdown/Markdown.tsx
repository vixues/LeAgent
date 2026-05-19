import { useMemo, type ReactNode } from 'react';
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
import { isProbablyVideoUrl, isRtspUrl } from '@/components/chat/media/chatMediaUtils';
import { resolveCodingProjectPreviewHref } from '@/lib/previewUrl';
import { resolveMarkdownImageSrcFromAttachments } from '@/components/chat/media/chatMediaUtils';
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
}

/**
 * Remark plugin to transform :::type callout blocks into HTML divs.
 * Supports :::note, :::warning, :::tip
 */
function remarkCallouts() {
  return (tree: MdNode) => {
    const children = tree.children;
    if (!children) return;
    const result: MdNode[] = [];

    for (let i = 0; i < children.length; i++) {
      const node = children[i]!;
      if (
        node.type === 'paragraph' &&
        node.children &&
        node.children.length > 0
      ) {
        const firstChild = node.children[0]!;
        if (firstChild.type === 'text' && typeof firstChild.value === 'string') {
          const match = firstChild.value.match(/^:::(note|warning|tip)\s*\n?([\s\S]*?):::$/);
          if (match) {
            result.push({
              type: 'html',
              value: `<div class="chat-callout chat-callout-${match[1]}"><div class="chat-callout-title">${match[1]}</div>${(match[2] ?? '').trim()}</div>`,
            });
            continue;
          }
        }
      }
      result.push(node);
    }

    tree.children = result;
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
export function Markdown({ content, className, variant = 'default', imageAttachments }: MarkdownProps) {
  const remarkPlugins = useMemo(
    () => [remarkGfm, remarkMath, remarkCallouts],
    [],
  );
  const rehypePlugins = useMemo(() => [rehypeKatex, rehypeHighlight], []);

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
          resolveMarkdownImageSrcFromAttachments(src, imageAttachments) ?? src ?? '';
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
              : 'list-disc list-inside space-y-1 my-2'
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
              : 'list-decimal list-inside space-y-1 my-2'
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
              : 'overflow-x-auto my-3'
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

  return (
    <div
      className={cn(
        'max-w-none break-words',
        variant === 'article' && ARTICLE_PROSE,
        className
      )}
    >
      <ReactMarkdown remarkPlugins={remarkPlugins} rehypePlugins={rehypePlugins} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
