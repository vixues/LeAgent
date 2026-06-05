import { useMemo } from 'react';
import { cn } from '@/lib/utils';
import type { GenUiNode } from '@/types/genUi';
import { useGenUiRenderContext } from '@/components/canvas/genUi/GenUiRenderContext';

function wrapHtmlFragment(html: string): string {
  const trimmed = html.trim();
  if (!trimmed) return '';
  if (/<html[\s>]/i.test(trimmed)) return trimmed;
  return `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/></head><body>${trimmed}</body></html>`;
}

function parseHeight(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value) && value > 0) {
    return Math.min(2000, Math.max(120, Math.round(value)));
  }
  if (typeof value === 'string') {
    const n = parseInt(value.replace(/px$/i, '').trim(), 10);
    if (Number.isFinite(n) && n > 0) return Math.min(2000, Math.max(120, n));
  }
  return 320;
}

export function GenUiHtmlFrame({ node }: { node: GenUiNode }) {
  const ctx = useGenUiRenderContext();
  const p = (node.props || {}) as Record<string, unknown>;
  const rawHtml = typeof p.html === 'string' ? p.html : '';
  const title = typeof p.title === 'string' && p.title.trim() ? p.title.trim() : 'Embedded HTML';
  const height = parseHeight(p.height);
  const jsEnabled = Boolean(ctx.jsEnabled);

  const srcDoc = useMemo(() => wrapHtmlFragment(rawHtml), [rawHtml]);
  const sandbox = jsEnabled ? 'allow-scripts' : '';

  if (!srcDoc) {
    return (
      <div className="rounded-lg border border-dashed border-border p-3 text-xs text-muted-foreground">
        HtmlFrame: empty html
      </div>
    );
  }

  return (
    <div
      className={cn(
        'overflow-hidden rounded-lg border border-border bg-background',
        !jsEnabled && 'opacity-95',
      )}
    >
      {!jsEnabled && (
        <div className="border-b border-border bg-surface-sunken/80 px-2 py-1 text-[10px] text-muted-foreground">
          JS disabled — enable JS in the preview toolbar to run scripts
        </div>
      )}
      <iframe
        key={jsEnabled ? 'js-on' : 'js-off'}
        title={title}
        srcDoc={srcDoc}
        sandbox={sandbox || undefined}
        className="w-full border-0"
        style={{ height }}
        referrerPolicy="no-referrer"
      />
    </div>
  );
}
