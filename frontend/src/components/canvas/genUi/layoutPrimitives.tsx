import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';
import type { GenUiNode } from '@/types/genUi';
import type { GenUiRenderContextValue } from '@/components/canvas/genUi/GenUiRenderContext';
import { composeDesignSurfaceClassName, getGenUiTheme } from '@/components/canvas/genUi/themeManager';

const b = (v: unknown): boolean => Boolean(v);

/** Map catalog ratio strings to CSS aspect-ratio value. */
function ratioToCss(ratioRaw: unknown): string | undefined {
  const raw = typeof ratioRaw === 'string' ? ratioRaw.trim() : '';
  if (!raw) return '16 / 9';
  const normalized = raw.replace(/\s+/g, '');
  const parts = normalized.split(/[:/]/).filter(Boolean);
  if (parts.length >= 2) {
    const a = Number(parts[0]);
    const bNum = Number(parts[1]);
    if (Number.isFinite(a) && Number.isFinite(bNum) && bNum !== 0) {
      return `${a} / ${bNum}`;
    }
  }
  return '16 / 9';
}

export function renderAspectBox(
  node: GenUiNode,
  depth: number,
  renderChild: (c: GenUiNode, d: number) => ReactNode,
): ReactNode {
  const p = (node.props || {}) as Record<string, unknown>;
  const ch = (node.children || []) as GenUiNode[];
  const ar = ratioToCss(p.ratio);
  const maxW = p.maxWidth != null ? `${Number(p.maxWidth)}px` : undefined;
  const overflowHidden = (p.overflow as string) !== 'visible';

  return (
    <div
      key={node.nodeId}
      className={cn('w-full', b(p.rounded) && 'rounded-xl', overflowHidden && 'overflow-hidden')}
      style={{
        aspectRatio: ar,
        maxWidth: maxW,
      }}
    >
      <div className={cn('flex h-full min-h-0 w-full flex-col gap-2', overflowHidden && 'overflow-hidden')}>
        {ch.map((c) => (
          <div key={c.nodeId} className="min-h-0 min-w-0 shrink-0">
            {renderChild(c, depth + 1)}
          </div>
        ))}
      </div>
    </div>
  );
}

export function renderDesignSurface(
  node: GenUiNode,
  depth: number,
  renderChild: (c: GenUiNode, d: number, ctx: GenUiRenderContextValue) => ReactNode,
  ctx: GenUiRenderContextValue,
): ReactNode {
  const p = (node.props || {}) as Record<string, unknown>;
  const ch = (node.children || []) as GenUiNode[];
  const theme = getGenUiTheme(p.preset);
  const themedCtx: GenUiRenderContextValue = { ...ctx, themeId: theme.id };

  return (
    <div key={node.nodeId} className={composeDesignSurfaceClassName(p.preset, p.padding)} data-genui-theme={theme.id}>
      <div className={cn('space-y-2', theme.contentClassName)}>
        {ch.map((c) => renderChild(c, depth + 1, themedCtx))}
      </div>
    </div>
  );
}
