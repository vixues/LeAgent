/**
 * Shared Tailwind class maps for GenUi node renderers.
 *
 * Token contract: every "primary" intent maps to the system `primary` scale
 * (sky-blue) wired in `tailwind.config.js` + `globals.css`. Hard-coded
 * `bg-blue-*` is forbidden here so the GenUi surface stays in lock-step with
 * the rest of the workspace (header, side rail, toasts, etc.).
 */

export const SEVERITY_STYLES: Record<string, { bg: string; border: string; text: string; icon: string }> = {
  info: {
    bg: 'bg-primary-50 dark:bg-primary-950/30',
    border: 'border-primary-200/80 dark:border-primary-800/70',
    text: 'text-primary-800 dark:text-primary-300',
    icon: 'info',
  },
  success: {
    bg: 'bg-mint-50 dark:bg-mint-950/30',
    border: 'border-mint-200/80 dark:border-mint-800/70',
    text: 'text-mint-700 dark:text-mint-300',
    icon: 'circle-check',
  },
  warning: {
    bg: 'bg-amber-50 dark:bg-amber-950/30',
    border: 'border-amber-200/80 dark:border-amber-800/70',
    text: 'text-amber-800 dark:text-amber-300',
    icon: 'triangle-alert',
  },
  error: {
    bg: 'bg-rose-50 dark:bg-rose-950/30',
    border: 'border-rose-200/80 dark:border-rose-800/70',
    text: 'text-rose-700 dark:text-rose-300',
    icon: 'circle-alert',
  },
};

export const BADGE_VARIANTS: Record<string, string> = {
  default: 'bg-surface-sunken text-foreground/80 dark:bg-surface-elevated dark:text-foreground/80',
  primary: 'bg-primary-100 text-primary-800 dark:bg-primary-900/40 dark:text-primary-200',
  success: 'bg-mint-100 text-mint-800 dark:bg-mint-900/40 dark:text-mint-200',
  warning: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
  error: 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-200',
  info: 'bg-primary-100 text-primary-800 dark:bg-primary-900/40 dark:text-primary-200',
  neutral: 'bg-surface-sunken text-muted-foreground dark:bg-surface-elevated',
};

export const BUTTON_VARIANTS: Record<string, string> = {
  primary:
    'bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400 hover:bg-primary-100 dark:hover:bg-primary-900/40 border-primary-300 dark:border-primary-600 focus-visible:ring-2 focus-visible:ring-primary-500/40',
  secondary:
    'bg-surface-sunken hover:bg-border-subtle text-foreground border-border dark:bg-surface-elevated dark:hover:bg-surface-sunken',
  outline:
    'bg-transparent hover:bg-surface-sunken text-foreground border-border dark:hover:bg-surface-elevated',
  ghost:
    'bg-transparent hover:bg-surface-sunken text-foreground border-transparent dark:hover:bg-surface-elevated',
  danger:
    'bg-rose-600 hover:bg-rose-700 text-white border-rose-600 focus-visible:ring-2 focus-visible:ring-rose-500/40',
  success:
    'bg-mint-600 hover:bg-mint-700 text-white border-mint-600 focus-visible:ring-2 focus-visible:ring-mint-500/40',
};

export const TAG_COLORS: Record<string, string> = {
  gray: 'bg-surface-sunken text-foreground/80 dark:bg-surface-elevated dark:text-foreground/80',
  neutral: 'bg-surface-sunken text-foreground/80 dark:bg-surface-elevated dark:text-foreground/80',
  blue: 'bg-primary-100 text-primary-800 dark:bg-primary-900/40 dark:text-primary-200',
  primary: 'bg-primary-100 text-primary-800 dark:bg-primary-900/40 dark:text-primary-200',
  green: 'bg-mint-100 text-mint-800 dark:bg-mint-900/40 dark:text-mint-200',
  mint: 'bg-mint-100 text-mint-800 dark:bg-mint-900/40 dark:text-mint-200',
  red: 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-200',
  rose: 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-200',
  yellow: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
  amber: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
  purple: 'bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-200',
  violet: 'bg-violet-100 text-violet-800 dark:bg-violet-900/40 dark:text-violet-200',
  peach: 'bg-peach-100 text-peach-800 dark:bg-peach-900/40 dark:text-peach-200',
};

export const PROGRESS_COLORS: Record<string, string> = {
  primary: 'bg-primary-500',
  success: 'bg-mint-500',
  warning: 'bg-amber-500',
  error: 'bg-rose-500',
};

export const TEXT_COLORS: Record<string, string> = {
  muted: 'text-muted-foreground',
  default: 'text-foreground',
  primary: 'text-primary-600 dark:text-primary-300',
  success: 'text-mint-600 dark:text-mint-300',
  warning: 'text-amber-600 dark:text-amber-300',
  error: 'text-rose-600 dark:text-rose-300',
};

export const TEXT_SIZES: Record<string, string> = {
  xs: 'text-xs',
  sm: 'text-sm',
  base: 'text-base',
  lg: 'text-lg',
  xl: 'text-xl',
  '2xl': 'text-2xl',
};

/** Soft semantic widget frames used by the slot-aware root renderer. */
export const UI_SLOT_FRAME: Record<string, { label: string; className: string }> = {
  weather: {
    label: 'Weather',
    className:
      'rounded-xl border border-primary-200/80 dark:border-primary-800/80 overflow-hidden bg-surface-elevated shadow-soft',
  },
  calendar: {
    label: 'Calendar',
    className:
      'rounded-xl border border-violet-200/80 dark:border-violet-800/80 overflow-hidden bg-surface-elevated shadow-soft',
  },
  generic: {
    label: 'Widget',
    className: 'rounded-xl border border-border overflow-hidden bg-surface-elevated shadow-soft',
  },
};

// ---------------------------------------------------------------------------
// Shared design tokens — single source of truth for new component renderers.
// ---------------------------------------------------------------------------

export const SHADOW_TOKENS: Record<string, string> = {
  none: '',
  sm: 'shadow-sm',
  md: 'shadow-md',
  lg: 'shadow-lg',
  xl: 'shadow-xl',
  soft: 'shadow-soft',
  glow: 'shadow-glow',
};

export const RADIUS_TOKENS: Record<string, string> = {
  none: 'rounded-none',
  sm: 'rounded-md',
  md: 'rounded-lg',
  lg: 'rounded-xl',
  xl: 'rounded-2xl',
  full: 'rounded-full',
};

export const ICON_SIZE_TOKENS: Record<string, number> = {
  xs: 14,
  sm: 16,
  md: 20,
  lg: 24,
  xl: 32,
  '2xl': 40,
};

export const PADDING_TOKENS: Record<string, string> = {
  none: 'p-0',
  xs: 'p-2',
  sm: 'p-3',
  md: 'p-4',
  lg: 'p-6',
  xl: 'p-8',
};

export const GAP_TOKENS: Record<string, string> = {
  none: 'gap-0',
  xs: 'gap-1',
  sm: 'gap-2',
  md: 'gap-3',
  lg: 'gap-4',
  xl: 'gap-6',
};

export type CardSurfaceVariant = 'default' | 'elevated' | 'outlined' | 'glass' | 'tinted' | 'flat';

/**
 * Compose Card / Surface base classes. Returns a single class string suitable
 * for `cn()`. Keeps every card visually consistent with the workspace shell.
 */
export function cardSurface(
  variant: CardSurfaceVariant = 'default',
  options: { radius?: keyof typeof RADIUS_TOKENS; shadow?: keyof typeof SHADOW_TOKENS } = {},
): string {
  const radius = RADIUS_TOKENS[options.radius ?? 'lg'];
  const shadow = SHADOW_TOKENS[options.shadow ?? (variant === 'elevated' ? 'soft' : 'none')];
  const base = (() => {
    switch (variant) {
      case 'elevated':
        return 'border border-border-subtle bg-surface-elevated';
      case 'outlined':
        return 'border border-border bg-transparent';
      case 'glass':
        return 'border border-white/10 dark:border-white/5 bg-surface/70 backdrop-blur';
      case 'tinted':
        return 'border border-primary-200/60 dark:border-primary-800/60 bg-primary-50/60 dark:bg-primary-950/20';
      case 'flat':
        return 'border-0 bg-surface-sunken';
      case 'default':
      default:
        return 'border border-border bg-surface-elevated';
    }
  })();
  return [base, radius, shadow].filter(Boolean).join(' ');
}

/** Resolve numeric icon size from token name or raw number. */
export function resolveIconSize(value: unknown, fallback = 20): number {
  if (typeof value === 'number' && Number.isFinite(value)) return Math.min(96, Math.max(10, value));
  if (typeof value === 'string') {
    const t = value.trim().toLowerCase();
    if (t in ICON_SIZE_TOKENS) return ICON_SIZE_TOKENS[t]!;
    const parsed = Number(t);
    if (Number.isFinite(parsed) && parsed > 0) return Math.min(96, Math.max(10, parsed));
  }
  return fallback;
}
