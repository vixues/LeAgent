import { cn } from '@/lib/utils';
import { cardSurface, type CardSurfaceVariant } from '@/components/canvas/genUi/styles';

export type { CardSurfaceVariant };

export const GEN_UI_THEME_IDS = [
  'poster',
  'slide',
  'card',
  'editorial',
  'minimal',
  'brutalist',
  'geek',
] as const;

export type GenUiThemeId = (typeof GEN_UI_THEME_IDS)[number];

export type GenUiThemeTone =
  | 'expressive'
  | 'presentation'
  | 'compact'
  | 'editorial'
  | 'minimal'
  | 'high-contrast'
  | 'technical';

export interface GenUiThemeDefinition {
  id: GenUiThemeId;
  label: string;
  description: string;
  tone: GenUiThemeTone;
  surfaceClassName: string;
  contentClassName?: string;
  accentClassName?: string;
  /** Panel chrome for Card / DataCard / MetricCard children inside this theme. */
  nestedCardClassName?: string;
  /** Descendant typography overrides on nested panels. */
  nestedCardContentClassName?: string;
}

const THEME_ID_SET = new Set<string>(GEN_UI_THEME_IDS);

const DESIGN_PADDING = {
  none: 'p-0',
  sm: 'p-3',
  md: 'p-5',
  lg: 'p-8',
} as const;
type DesignSurfacePadding = keyof typeof DESIGN_PADDING;
const DEFAULT_DESIGN_PADDING = DESIGN_PADDING.md;

export const GEN_UI_THEMES: Record<GenUiThemeId, GenUiThemeDefinition> = {
  poster: {
    id: 'poster',
    label: 'Poster',
    description: 'Large expressive gradient surface for hero posters and announcement cards.',
    tone: 'expressive',
    surfaceClassName:
      'rounded-2xl bg-gradient-to-br from-indigo-600 via-violet-600 to-fuchsia-600 text-white shadow-2xl ring-1 ring-white/10',
  },
  slide: {
    id: 'slide',
    label: 'Slide',
    description: 'Neutral elevated frame for presentation slides and balanced visual sections.',
    tone: 'presentation',
    surfaceClassName: 'rounded-xl border border-border bg-surface-elevated text-foreground shadow-md',
  },
  card: {
    id: 'card',
    label: 'Card',
    description: 'Compact card surface that follows the workspace card tokens.',
    tone: 'compact',
    surfaceClassName: 'rounded-xl border border-border bg-card text-card-foreground shadow-lg',
  },
  editorial: {
    id: 'editorial',
    label: 'Editorial',
    description: 'Warm document surface for reports, summaries, and magazine-like layouts.',
    tone: 'editorial',
    surfaceClassName:
      'rounded-xl border border-stone-200 bg-stone-50 text-stone-900 dark:border-stone-700 dark:bg-stone-950 dark:text-stone-100 shadow-sm',
  },
  minimal: {
    id: 'minimal',
    label: 'Minimal',
    description: 'Quiet low-chrome surface for professional docs and dense information.',
    tone: 'minimal',
    surfaceClassName: 'rounded-lg border-0 bg-background text-foreground shadow-none ring-1 ring-border/60',
  },
  brutalist: {
    id: 'brutalist',
    label: 'Brutalist',
    description: 'Raw high-contrast mono surface for intentionally loud layouts.',
    tone: 'high-contrast',
    surfaceClassName:
      'rounded-none border-4 border-foreground bg-yellow-300 text-black font-mono uppercase tracking-wide shadow-[6px_6px_0_0_rgb(0,0,0)] dark:bg-yellow-400',
  },
  geek: {
    id: 'geek',
    label: 'Geek',
    description: 'Terminal-inspired cyber surface for code, ops, diagnostics, and technical dashboards.',
    tone: 'technical',
    surfaceClassName:
      'rounded-2xl border border-emerald-400/40 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.22),transparent_30%),linear-gradient(135deg,#020617,#0f172a_55%,#064e3b)] text-emerald-50 font-mono shadow-[0_0_36px_rgba(16,185,129,0.22)] ring-1 ring-cyan-300/20',
    contentClassName: '[&_h1]:text-emerald-50 [&_h2]:text-emerald-50 [&_h3]:text-emerald-50 [&_h4]:text-emerald-50 [&_p]:text-emerald-50/90 [&_.text-muted-foreground]:!text-cyan-200/80',
    accentClassName: 'text-cyan-200',
    nestedCardClassName:
      'border border-emerald-400/30 bg-slate-950/80 text-emerald-50 shadow-[inset_0_1px_0_rgba(45,212,191,0.12)] backdrop-blur-sm',
    nestedCardContentClassName:
      '[&_.text-foreground]:text-emerald-50 [&_.text-muted-foreground]:text-cyan-200/80 [&_.text-primary-600]:text-cyan-300 [&_.dark\\:text-primary-300]:text-cyan-300',
  },
};

export function normalizeGenUiThemeId(value: unknown, fallback: GenUiThemeId = 'slide'): GenUiThemeId {
  const raw = typeof value === 'string' ? value.trim().toLowerCase() : '';
  return THEME_ID_SET.has(raw) ? (raw as GenUiThemeId) : fallback;
}

export function getGenUiTheme(value: unknown, fallback: GenUiThemeId = 'slide'): GenUiThemeDefinition {
  return GEN_UI_THEMES[normalizeGenUiThemeId(value, fallback)];
}

export function getGenUiThemeIds(): GenUiThemeId[] {
  return [...GEN_UI_THEME_IDS];
}

export function resolveDesignSurfacePadding(value: unknown): string {
  const key = typeof value === 'string' ? value.trim().toLowerCase() : 'md';
  return key in DESIGN_PADDING ? DESIGN_PADDING[key as DesignSurfacePadding] : DEFAULT_DESIGN_PADDING;
}

export function composeDesignSurfaceClassName(themeValue: unknown, paddingValue: unknown): string {
  const theme = getGenUiTheme(themeValue);
  return cn('min-w-0 max-w-full', theme.surfaceClassName, resolveDesignSurfacePadding(paddingValue));
}

/** Card / panel surface inside an active DesignSurface theme (falls back to global card tokens). */
export function composeThemedCardClassName(
  themeId: GenUiThemeId | null | undefined,
  variant: CardSurfaceVariant = 'default',
): string {
  if (themeId) {
    const nested = GEN_UI_THEMES[themeId]?.nestedCardClassName;
    if (nested) return cn('rounded-2xl', nested);
  }
  if (variant === 'elevated') return cardSurface('elevated', { radius: 'xl', shadow: 'md' });
  if (variant === 'outlined') return cardSurface('outlined', { radius: 'xl' });
  if (variant === 'glass') return cardSurface('glass', { radius: 'xl' });
  if (variant === 'tinted') return cardSurface('tinted', { radius: 'xl' });
  return cardSurface('default', { radius: 'xl' });
}

export function getThemedCardContentClassName(themeId: GenUiThemeId | null | undefined): string | undefined {
  if (!themeId) return undefined;
  return GEN_UI_THEMES[themeId]?.nestedCardContentClassName;
}
