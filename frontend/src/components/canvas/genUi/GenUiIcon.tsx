import { Suspense, lazy, type ComponentType, type LazyExoticComponent } from 'react';
import type { LucideProps } from 'lucide-react';
import dynamicIconImports from 'lucide-react/dynamicIconImports';
import { cn } from '@/lib/utils';
import type { GenUiNode } from '@/types/genUi';

const imports = dynamicIconImports as Record<
  string,
  () => Promise<{ default: ComponentType<LucideProps> }>
>;

/** Stable lazy component per slug — avoid `lazy()` inside `useMemo` (React 19 “Should have a queue” / #311). */
const lucideLazyBySlug = new Map<string, LazyExoticComponent<ComponentType<LucideProps>>>();

function lazyLucideForSlug(slug: string): LazyExoticComponent<ComponentType<LucideProps>> {
  let Cmp = lucideLazyBySlug.get(slug);
  if (!Cmp) {
    const load = imports[slug] ?? imports['circle-help'];
    Cmp = lazy(() => {
      if (!load) {
        return Promise.resolve({ default: () => null });
      }
      return load();
    });
    lucideLazyBySlug.set(slug, Cmp);
  }
  return Cmp;
}

const ICON_COLOR_CLASS: Record<string, string> = {
  muted: 'text-muted-foreground',
  default: 'text-foreground',
  primary: 'text-primary-600 dark:text-primary-400',
  success: 'text-green-600 dark:text-green-400',
  warning: 'text-amber-600 dark:text-amber-400',
  error: 'text-red-600 dark:text-red-400',
};

function isLikelyEmojiOrSymbol(raw: string): boolean {
  const t = raw.trim();
  if (!t) return true;
  // ASCII letters → treat as icon name candidate when not pure digits
  if (/[a-z]/i.test(t)) return false;
  return true;
}

/** PascalCase / camelCase → kebab-case for Lucide slug (e.g. CircleAlert → circle-alert). */
function pascalToKebab(raw: string): string {
  return raw
    .trim()
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .replace(/([A-Z])([A-Z][a-z])/g, '$1-$2')
    .replace(/([a-zA-Z])(\d+)/g, '$1-$2')
    .replace(/(\d)([A-Za-z])/g, '$1-$2')
    .toLowerCase()
    .replace(/\s+/g, '-');
}

function resolveLucideSlug(name: string, iconSet: unknown): string | null {
  const t = name.trim();
  if (!t) return 'circle-help';
  if (iconSet === 'emoji') return null;

  const direct = t.toLowerCase().replace(/\s+/g, '-');
  if (imports[direct]) return direct;

  if (iconSet === 'lucide') {
    const fromPascal = pascalToKebab(t);
    if (imports[fromPascal]) return fromPascal;
    return imports[direct] ? direct : 'circle-help';
  }

  // auto: explicit kebab or single lowercase word → Lucide if registered
  if (/^[a-z0-9]+(?:-[a-z0-9]+)*$/i.test(t) && imports[direct]) return direct;

  if (!isLikelyEmojiOrSymbol(t)) {
    const k = pascalToKebab(t);
    if (imports[k]) return k;
  }

  return null;
}

function DynamicLucideGlyph({
  slug,
  size,
  className,
  strokeWidth,
}: {
  slug: string;
  size: number;
  className?: string;
  strokeWidth?: number;
}) {
  const Cmp = lazyLucideForSlug(slug);
  return (
    <Suspense
      fallback={
        <span
          className="inline-block shrink-0 rounded bg-muted/40 animate-pulse"
          style={{ width: size, height: size }}
          aria-hidden
        />
      }
    >
      <Cmp
        size={size}
        className={cn('shrink-0', className)}
        strokeWidth={strokeWidth ?? 2}
        aria-hidden
      />
    </Suspense>
  );
}

/** GenUi ``Icon``: Lucide (``name`` as kebab slug or PascalCase) or emoji when ``iconSet`` / heuristics say so. */
export function GenUiIcon({ node }: { node: GenUiNode }) {
  const p = (node.props || {}) as Record<string, unknown>;
  const name = String(p.name ?? 'sparkles');
  const iconSize = Math.min(96, Math.max(12, Number(p.size) || 20));
  const colorKey = typeof p.color === 'string' ? p.color : 'default';
  const colorClass = ICON_COLOR_CLASS[colorKey] ?? ICON_COLOR_CLASS.default;
  const strokeW = p.strokeWidth != null ? Number(p.strokeWidth) : undefined;

  const slug = resolveLucideSlug(name, p.iconSet);

  if (slug == null) {
    if (isLikelyEmojiOrSymbol(name)) {
      return (
        <span
          key={node.nodeId}
          className={cn('inline-flex items-center justify-center leading-none', colorClass)}
          style={{ fontSize: `${iconSize}px` }}
          role="img"
          aria-label={name}
        >
          {name}
        </span>
      );
    }
    return (
      <span
        key={node.nodeId}
        className={cn('inline-flex items-center justify-center', colorClass)}
        role="img"
        aria-label={name}
        title={name}
      >
        <DynamicLucideGlyph slug="circle-help" size={iconSize} strokeWidth={strokeW} />
      </span>
    );
  }

  return (
    <span key={node.nodeId} className={cn('inline-flex items-center justify-center', colorClass)} role="img" aria-label={slug}>
      <DynamicLucideGlyph slug={slug} size={iconSize} strokeWidth={strokeW} />
    </span>
  );
}
