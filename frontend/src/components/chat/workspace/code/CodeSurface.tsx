import { useEffect, useMemo, useRef } from 'react';
import hljs from 'highlight.js';
import 'highlight.js/styles/github-dark.css';
import { cn } from '@/lib/utils';

interface CodeSurfaceProps {
  /** Plain code body. Mutually exclusive with `diff`. */
  code?: string;
  /** Before/after pair rendered as a stacked unified diff. */
  diff?: { before: string; after: string };
  language?: string;
  wrap?: boolean;
  showLineNumbers?: boolean;
  /** Keep the viewport pinned to the newest line while content streams in. */
  tail?: boolean;
  maxHeightClass?: string;
  className?: string;
  /** Placeholder when there is no body yet (e.g. streaming start). */
  placeholder?: string;
}

function highlightLine(line: string, language: string): string {
  const safe = line.length > 0 ? line : ' ';
  try {
    if (language && hljs.getLanguage(language)) {
      return hljs.highlight(safe, { language }).value;
    }
    return hljs.highlightAuto(safe).value;
  } catch {
    return safe;
  }
}

interface LineRowsProps {
  lines: string[];
  language: string;
  showLineNumbers: boolean;
  wrap: boolean;
  startNumber?: number;
  tone?: 'add' | 'remove';
}

function LineRows({
  lines,
  language,
  showLineNumbers,
  wrap,
  startNumber = 1,
  tone,
}: LineRowsProps) {
  return (
    <table className="w-full border-collapse">
      <tbody>
        {lines.map((line, index) => (
          <tr
            key={`${index}-${line.length}`}
            className={cn(
              tone === 'add' && 'bg-emerald-500/[0.06]',
              tone === 'remove' && 'bg-rose-500/[0.06]',
            )}
          >
            {showLineNumbers && (
              <td
                className={cn(
                  'select-none border-r border-border-subtle/40 pr-2 text-right align-top text-[10px] tabular-nums',
                  tone === 'add'
                    ? 'text-emerald-600/80 dark:text-emerald-400/80'
                    : tone === 'remove'
                      ? 'text-rose-600/80 dark:text-rose-400/80'
                      : 'text-muted-foreground/45',
                )}
                style={{ minWidth: '2.5rem' }}
              >
                {tone === 'add' ? '+' : tone === 'remove' ? '−' : startNumber + index}
              </td>
            )}
            <td
              className={cn(
                'pl-2.5 align-top',
                wrap ? 'whitespace-pre-wrap break-words' : 'whitespace-pre',
              )}
            >
              <span
                className="block w-full min-w-0 bg-transparent !bg-transparent"
                dangerouslySetInnerHTML={{ __html: highlightLine(line, language) }}
              />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/**
 * Shared streaming-first code / diff renderer for the workspace Code tab. Uses
 * per-line highlight.js so incremental streaming stays cheap, supports word
 * wrap, line numbers, tail-scroll, and a stacked unified-diff mode. This single
 * primitive replaces the five bespoke code panels the tab used to ship.
 */
export function CodeSurface({
  code,
  diff,
  language = 'plaintext',
  wrap = false,
  showLineNumbers = true,
  tail = false,
  maxHeightClass = 'max-h-[45vh]',
  className,
  placeholder = '…',
}: CodeSurfaceProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  const removed = useMemo(
    () => (diff ? diff.before.split('\n') : []),
    [diff],
  );
  const added = useMemo(() => (diff ? diff.after.split('\n') : []), [diff]);
  const lines = useMemo(() => (code ? code.split('\n') : []), [code]);

  useEffect(() => {
    if (!tail || !scrollRef.current) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [tail, code, diff?.after]);

  const isEmpty = diff
    ? removed.length === 0 && added.length === 0
    : lines.length === 0 || (lines.length === 1 && lines[0] === '');

  return (
    <div
      ref={scrollRef}
      className={cn(
        'workspace-code-hljs overflow-auto bg-gray-50 dark:bg-surface',
        maxHeightClass,
        className,
      )}
    >
      <pre className="m-0 px-1.5 py-2.5 font-mono text-[11.5px] leading-relaxed">
        <code className={cn('hljs !bg-transparent', `language-${language}`)}>
          {isEmpty ? (
            <span className="px-1.5 text-muted-foreground/60">{placeholder}</span>
          ) : diff ? (
            <>
              {removed.length > 0 && removed.some((l) => l.length > 0) && (
                <LineRows
                  lines={removed}
                  language={language}
                  showLineNumbers={showLineNumbers}
                  wrap={wrap}
                  tone="remove"
                />
              )}
              <LineRows
                lines={added}
                language={language}
                showLineNumbers={showLineNumbers}
                wrap={wrap}
                tone="add"
              />
            </>
          ) : (
            <LineRows
              lines={lines}
              language={language}
              showLineNumbers={showLineNumbers}
              wrap={wrap}
            />
          )}
        </code>
      </pre>
    </div>
  );
}
