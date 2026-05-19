/**
 * Professional component renderers for the GenUi catalog.
 *
 * These complement the bread-and-butter renderers in `GenUiRegistry.tsx` —
 * they're broken out so the registry switch stays scannable and the new
 * surfaces can evolve independently.
 */

import type { ReactNode } from 'react';
import { Check, Loader2, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { GenUiImage } from '@/components/canvas/genUi/GenUiImage';
import { IconGlyph } from '@/components/canvas/genUi/IconGlyph';
import { cardSurface, SHADOW_TOKENS } from '@/components/canvas/genUi/styles';
import type { GenUiNode } from '@/types/genUi';

const s = (v: unknown): string => (typeof v === 'string' ? v : v != null ? String(v) : '');
const b = (v: unknown): boolean => Boolean(v);

interface RenderArgs {
  node: GenUiNode;
  depth: number;
  renderChild: (c: GenUiNode, d: number) => ReactNode;
}

const COLUMN_CLASSES: Record<number, string> = {
  1: 'grid-cols-1',
  2: 'grid-cols-1 sm:grid-cols-2',
  3: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3',
  4: 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-4',
  5: 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-5',
  6: 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-6',
};

function clampColumns(value: unknown, fallback = 3): number {
  const n = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.max(1, Math.min(6, Math.round(n)));
}

// ---------------------------------------------------------------------------
// SectionHeader
// ---------------------------------------------------------------------------

export function renderSectionHeader({ node, depth, renderChild }: RenderArgs): ReactNode {
  const p = (node.props || {}) as Record<string, unknown>;
  const ch = (node.children || []) as GenUiNode[];
  return (
    <div key={node.nodeId} className="flex items-start justify-between gap-3 mb-3">
      <div className="min-w-0">
        {!!p.eyebrow && (
          <p className="text-[10px] uppercase tracking-[0.14em] font-semibold text-primary-600 dark:text-primary-300">
            {s(p.eyebrow)}
          </p>
        )}
        <div className="flex items-center gap-2 mt-0.5">
          {!!p.icon && <IconGlyph name={p.icon} size={20} tone={s(p.iconTone) || 'primary'} />}
          {!!p.title && (
            <h3 className="text-base font-semibold text-foreground leading-tight">{s(p.title)}</h3>
          )}
        </div>
        {!!p.description && (
          <p className="text-xs text-muted-foreground mt-1 max-w-[64ch]">{s(p.description)}</p>
        )}
      </div>
      {ch.length > 0 && (
        <div className="flex shrink-0 items-center gap-2">
          {ch.map((c) => (
            <span key={c.nodeId}>{renderChild(c, depth + 1)}</span>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// KpiBoard — grid of MetricCard children (or any cards).
// ---------------------------------------------------------------------------

export function renderKpiBoard({ node, depth, renderChild }: RenderArgs): ReactNode {
  const p = (node.props || {}) as Record<string, unknown>;
  const ch = (node.children || []) as GenUiNode[];
  const cols = clampColumns(p.columns, Math.min(4, Math.max(1, ch.length || 3)));
  return (
    <div key={node.nodeId} className={cn('grid gap-3', COLUMN_CLASSES[cols] ?? COLUMN_CLASSES[3])}>
      {ch.map((c) => (
        <div key={c.nodeId} className="min-w-0">
          {renderChild(c, depth + 1)}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// FeatureGrid — repeating icon + title + description grid.
// ---------------------------------------------------------------------------

interface FeatureItem {
  icon?: unknown;
  iconTone?: string;
  title?: string;
  description?: string;
  badge?: string;
}

export function renderFeatureGrid({ node }: RenderArgs): ReactNode {
  const p = (node.props || {}) as Record<string, unknown>;
  const items = Array.isArray(p.items) ? (p.items as FeatureItem[]) : [];
  const cols = clampColumns(p.columns, Math.min(3, Math.max(1, items.length || 3)));
  if (!items.length) return null;
  return (
    <div key={node.nodeId} className={cn('grid gap-3', COLUMN_CLASSES[cols] ?? COLUMN_CLASSES[3])}>
      {items.map((it, i) => (
        <div
          key={i}
          className={cn(cardSurface('elevated', { radius: 'lg' }), 'p-4 space-y-2 transition-colors hover:border-primary-300/60')}
        >
          <div className="flex items-center justify-between">
            <div
              className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-100/70 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300"
              aria-hidden
            >
              <IconGlyph name={it.icon ?? 'sparkles'} size={18} tone={it.iconTone || 'primary'} />
            </div>
            {it.badge && (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300">
                {it.badge}
              </span>
            )}
          </div>
          {it.title && <p className="text-sm font-semibold text-foreground">{it.title}</p>}
          {it.description && (
            <p className="text-xs text-muted-foreground leading-relaxed">{it.description}</p>
          )}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stepper
// ---------------------------------------------------------------------------

interface StepItem {
  title?: string;
  description?: string;
  icon?: unknown;
  status?: 'complete' | 'current' | 'pending' | 'error';
}

const STATUS_BADGE: Record<string, { ring: string; bg: string; text: string }> = {
  complete: {
    ring: 'ring-mint-300 dark:ring-mint-700',
    bg: 'bg-mint-500 text-white',
    text: 'text-mint-700 dark:text-mint-300',
  },
  current: {
    ring: 'ring-primary-300 dark:ring-primary-700',
    bg: 'bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300',
    text: 'text-primary-700 dark:text-primary-300',
  },
  pending: {
    ring: 'ring-border',
    bg: 'bg-surface-elevated text-muted-foreground border border-border',
    text: 'text-muted-foreground',
  },
  error: {
    ring: 'ring-rose-300 dark:ring-rose-700',
    bg: 'bg-rose-600 text-white',
    text: 'text-rose-700 dark:text-rose-300',
  },
};

export function renderStepper({ node }: RenderArgs): ReactNode {
  const p = (node.props || {}) as Record<string, unknown>;
  const orientation = (p.orientation as string) === 'horizontal' ? 'horizontal' : 'vertical';
  const steps = Array.isArray(p.steps) ? (p.steps as StepItem[]) : [];
  const current = typeof p.current === 'number' ? p.current : -1;
  if (!steps.length) return null;

  if (orientation === 'horizontal') {
    return (
      <ol key={node.nodeId} className="flex w-full items-stretch gap-2 overflow-x-auto no-scrollbar">
        {steps.map((step, i) => {
          const status = step.status ?? (i < current ? 'complete' : i === current ? 'current' : 'pending');
          const sty = STATUS_BADGE[status] ?? STATUS_BADGE.pending!;
          return (
            <li key={i} className="flex min-w-[140px] flex-1 items-start gap-2">
              <span
                className={cn(
                  'mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ring-2',
                  sty.ring,
                  sty.bg,
                )}
              >
                {status === 'complete' ? <Check className="h-3.5 w-3.5" aria-hidden /> : i + 1}
              </span>
              <div className="min-w-0">
                {step.title && (
                  <p className={cn('text-xs font-semibold leading-tight', sty.text)}>{step.title}</p>
                )}
                {step.description && (
                  <p className="text-[11px] text-muted-foreground mt-0.5 leading-snug line-clamp-2">
                    {step.description}
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    );
  }

  return (
    <ol key={node.nodeId} className="relative space-y-3 pl-7">
      <span className="pointer-events-none absolute left-3 top-3 bottom-3 w-px bg-border" aria-hidden />
      {steps.map((step, i) => {
        const status = step.status ?? (i < current ? 'complete' : i === current ? 'current' : 'pending');
        const sty = STATUS_BADGE[status] ?? STATUS_BADGE.pending!;
        return (
          <li key={i} className="relative">
            <span
              className={cn(
                'absolute -left-7 top-0.5 inline-flex h-6 w-6 items-center justify-center rounded-full text-[11px] font-semibold ring-2',
                sty.ring,
                sty.bg,
              )}
            >
              {status === 'complete' ? (
                <Check className="h-3 w-3" aria-hidden />
              ) : status === 'error' ? (
                <X className="h-3 w-3" aria-hidden />
              ) : status === 'current' ? (
                <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
              ) : (
                i + 1
              )}
            </span>
            {step.title && (
              <p className={cn('text-sm font-semibold leading-tight', sty.text)}>{step.title}</p>
            )}
            {step.description && (
              <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{step.description}</p>
            )}
          </li>
        );
      })}
    </ol>
  );
}

// ---------------------------------------------------------------------------
// QuoteCard
// ---------------------------------------------------------------------------

export function renderQuoteCard({ node }: RenderArgs): ReactNode {
  const p = (node.props || {}) as Record<string, unknown>;
  const quote = s(p.quote);
  const author = s(p.author);
  const role = s(p.role);
  const avatarUrl = s(p.avatarUrl);
  const initials = author.split(' ').map((w) => w[0]).join('').slice(0, 2).toUpperCase();
  return (
    <figure
      key={node.nodeId}
      className={cn(cardSurface('tinted', { radius: 'lg' }), 'p-5 sm:p-6 space-y-3 relative overflow-hidden')}
    >
      <span className="absolute -top-3 -left-1 text-7xl font-serif text-primary-500/15 select-none" aria-hidden>
        “
      </span>
      <blockquote className="relative text-sm sm:text-base text-foreground/90 leading-relaxed font-medium">
        {quote || 'Quote text'}
      </blockquote>
      {(author || role || avatarUrl) && (
        <figcaption className="flex items-center gap-3 pt-2 border-t border-primary-200/40 dark:border-primary-800/40">
          {avatarUrl ? (
            <img src={avatarUrl} alt={author || 'avatar'} className="h-9 w-9 rounded-full object-cover" />
          ) : (
            <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-primary-100 text-primary-700 text-xs font-semibold dark:bg-primary-900/40 dark:text-primary-200">
              {initials || '“'}
            </span>
          )}
          <div className="min-w-0">
            {author && <p className="text-sm font-semibold text-foreground">{author}</p>}
            {role && <p className="text-xs text-muted-foreground">{role}</p>}
          </div>
        </figcaption>
      )}
    </figure>
  );
}

// ---------------------------------------------------------------------------
// KeyValueList
// ---------------------------------------------------------------------------

interface KvItem {
  label?: string;
  value?: string;
  icon?: unknown;
}

export function renderKeyValueList({ node }: RenderArgs): ReactNode {
  const p = (node.props || {}) as Record<string, unknown>;
  const items = Array.isArray(p.items) ? (p.items as KvItem[]) : [];
  const cols = clampColumns(p.columns, items.length > 4 ? 2 : 1);
  if (!items.length) return null;
  return (
    <dl
      key={node.nodeId}
      className={cn(
        'grid gap-x-6 gap-y-2',
        cols === 1 ? 'grid-cols-1' : 'grid-cols-1 sm:grid-cols-2',
      )}
    >
      {items.map((it, i) => (
        <div
          key={i}
          className="flex items-start justify-between gap-4 border-b border-border-subtle/60 last:border-b-0 pb-2"
        >
          <dt className="flex items-center gap-1.5 text-xs uppercase tracking-wider font-medium text-muted-foreground">
            {!!it.icon && <IconGlyph name={it.icon} size={14} tone="muted" />}
            {it.label}
          </dt>
          <dd className="text-sm text-foreground font-medium text-right break-words">{it.value}</dd>
        </div>
      ))}
    </dl>
  );
}

// ---------------------------------------------------------------------------
// ImageGallery — multiple images with lightbox via GenUiImage.
// ---------------------------------------------------------------------------

interface GalleryItem {
  src?: string;
  alt?: string;
  caption?: string;
  aspect?: string;
}

export function renderImageGallery({ node }: RenderArgs): ReactNode {
  const p = (node.props || {}) as Record<string, unknown>;
  const items = Array.isArray(p.items) ? (p.items as GalleryItem[]) : [];
  if (!items.length) return null;
  const cols = clampColumns(p.columns, Math.min(3, Math.max(1, items.length)));
  const aspect = typeof p.aspect === 'string' && p.aspect.trim() ? p.aspect.trim() : '4:3';
  const lightbox = p.lightbox != null ? b(p.lightbox) : true;
  const shadow = SHADOW_TOKENS[s(p.shadow) || 'sm'] ?? SHADOW_TOKENS.sm;

  return (
    <div key={node.nodeId} className={cn('grid gap-3', COLUMN_CLASSES[cols] ?? COLUMN_CLASSES[3])}>
      {items.map((it, i) => (
        <div key={i} className={cn('rounded-xl overflow-hidden border border-border-subtle bg-surface-elevated', shadow)}>
          <GenUiImage
            node={{
              nodeId: `${node.nodeId}-img-${i}`,
              kind: 'Image',
              props: {
                src: it.src,
                alt: it.alt,
                caption: it.caption,
                aspect: it.aspect || aspect,
                fit: 'cover',
                rounded: false,
                lightbox,
              },
            }}
          />
        </div>
      ))}
    </div>
  );
}
