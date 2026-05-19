import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cn } from '@/lib/utils';
import type { GenUiNode } from '@/types/genUi';

const s = (v: unknown): string => (typeof v === 'string' ? v : v != null ? String(v) : '');

/** Replaces the legacy regex-based renderer with a real GFM-aware markdown surface. */
export function GenUiMarkdown({ node }: { node: GenUiNode }) {
  const p = (node.props || {}) as Record<string, unknown>;
  const content = s(p.content || p.value);
  if (!content.trim()) return null;
  return (
    <div
      className={cn(
        'prose prose-sm dark:prose-invert max-w-none',
        'prose-headings:font-semibold prose-headings:text-foreground',
        'prose-p:text-foreground/90 prose-li:text-foreground/90',
        'prose-a:text-primary-600 dark:prose-a:text-primary-300 prose-a:no-underline hover:prose-a:underline',
        'prose-code:before:content-none prose-code:after:content-none',
        'prose-code:bg-surface-sunken prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-[0.85em]',
        'prose-pre:bg-surface-sunken prose-pre:text-foreground prose-pre:rounded-lg prose-pre:border prose-pre:border-border-subtle',
        'prose-blockquote:border-l-primary-500 prose-blockquote:text-foreground/80',
      )}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}

export function GenUiInlineMarkdown({
  value,
  className,
}: {
  value: unknown;
  className?: string;
}) {
  const content = s(value);
  if (!content.trim()) return null;

  return (
    <span className={cn('whitespace-pre-wrap', className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <>{children}</>,
        }}
      >
        {content}
      </ReactMarkdown>
    </span>
  );
}
