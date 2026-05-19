import type { ComponentProps, ReactNode } from 'react';
import {
  BadgeCheck,
  Boxes,
  Briefcase,
  Building2,
  ClipboardCheck,
  Cog,
  Database,
  DollarSign,
  FileText,
  Headphones,
  LayoutGrid,
  Layers,
  LifeBuoy,
  type LucideIcon,
  Mail,
  Megaphone,
  MessageSquare,
  Package,
  Rocket,
  Scale,
  Server,
  Shield,
  ShieldCheck,
  ShoppingCart,
  Target,
  TrendingUp,
  Users,
  Wallet,
  Wrench,
  Workflow,
} from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Canonical mapping from backend category identifiers to Lucide icons.
 *
 * The backend may send category ids in a few different shapes (`finance`,
 * `finance_accounting`, `finance-and-accounting`, `Finance & Accounting`);
 * {@link normalizeCategoryId} handles the normalization before lookup.
 *
 * To add a new category:
 *  1. Add an entry below keyed by the normalized id.
 *  2. Add a matching tint in {@link CATEGORY_TINTS} so pills / badges stay
 *     visually aligned with the design-system accent palette (§3.4.2).
 */
const CATEGORY_ICONS: Record<string, LucideIcon> = {
  analytics: TrendingUp,
  approval: BadgeCheck,
  approvals: BadgeCheck,
  audit: ClipboardCheck,
  communication: Mail,
  compliance: ShieldCheck,
  compliance_and_audit: ShieldCheck,
  compliance_audit: ShieldCheck,
  customer: Headphones,
  customer_service: Headphones,
  customer_support: LifeBuoy,
  data: Database,
  data_management: Database,
  data_processing: Database,
  development: Wrench,
  devops: Server,
  document: FileText,
  document_management: FileText,
  document_processing: FileText,
  finance: DollarSign,
  finance_accounting: Wallet,
  finance_and_accounting: Wallet,
  general: LayoutGrid,
  hr: Users,
  human_resources: Users,
  inventory: Boxes,
  it: Server,
  legal: Scale,
  marketing: Megaphone,
  messaging: MessageSquare,
  operations: Cog,
  organization: Building2,
  procurement: ShoppingCart,
  productivity: Rocket,
  project_management: Briefcase,
  quality: BadgeCheck,
  sales: Target,
  security: Shield,
  stock: Package,
  support: LifeBuoy,
  technology: Server,
  workflow: Workflow,
};

/**
 * Soft accent tint per category (light / dark pairs) matching the accent
 * palette in `tailwind.config.js`. Used by {@link CategoryIconBadge} and
 * category chips to give each category a stable, calm color identity.
 */
const CATEGORY_TINTS: Record<string, string> = {
  analytics:
    'bg-lavender-100 text-lavender-700 dark:bg-lavender-900/30 dark:text-lavender-200',
  approval: 'bg-mint-100 text-mint-700 dark:bg-mint-900/30 dark:text-mint-200',
  approvals: 'bg-mint-100 text-mint-700 dark:bg-mint-900/30 dark:text-mint-200',
  audit: 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-200',
  communication: 'bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-200',
  compliance: 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-200',
  compliance_and_audit:
    'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-200',
  compliance_audit:
    'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-200',
  customer: 'bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-200',
  customer_service: 'bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-200',
  customer_support: 'bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-200',
  data: 'bg-primary-100 text-primary-700 dark:bg-primary-900/30 dark:text-primary-200',
  data_management:
    'bg-primary-100 text-primary-700 dark:bg-primary-900/30 dark:text-primary-200',
  data_processing:
    'bg-primary-100 text-primary-700 dark:bg-primary-900/30 dark:text-primary-200',
  development: 'bg-primary-100 text-primary-700 dark:bg-primary-900/30 dark:text-primary-200',
  devops: 'bg-primary-100 text-primary-700 dark:bg-primary-900/30 dark:text-primary-200',
  document: 'bg-peach-100 text-peach-700 dark:bg-peach-900/30 dark:text-peach-200',
  document_management:
    'bg-peach-100 text-peach-700 dark:bg-peach-900/30 dark:text-peach-200',
  document_processing:
    'bg-peach-100 text-peach-700 dark:bg-peach-900/30 dark:text-peach-200',
  finance: 'bg-peach-100 text-peach-700 dark:bg-peach-900/30 dark:text-peach-200',
  finance_accounting:
    'bg-peach-100 text-peach-700 dark:bg-peach-900/30 dark:text-peach-200',
  finance_and_accounting:
    'bg-peach-100 text-peach-700 dark:bg-peach-900/30 dark:text-peach-200',
  general: 'bg-surface-sunken text-muted-foreground dark:bg-surface-sunken',
  hr: 'bg-lavender-100 text-lavender-700 dark:bg-lavender-900/30 dark:text-lavender-200',
  human_resources:
    'bg-lavender-100 text-lavender-700 dark:bg-lavender-900/30 dark:text-lavender-200',
  inventory: 'bg-mint-100 text-mint-700 dark:bg-mint-900/30 dark:text-mint-200',
  it: 'bg-primary-100 text-primary-700 dark:bg-primary-900/30 dark:text-primary-200',
  legal: 'bg-surface-sunken text-muted-foreground dark:bg-surface-sunken',
  marketing: 'bg-peach-100 text-peach-700 dark:bg-peach-900/30 dark:text-peach-200',
  messaging: 'bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-200',
  operations:
    'bg-primary-100 text-primary-700 dark:bg-primary-900/30 dark:text-primary-200',
  organization:
    'bg-lavender-100 text-lavender-700 dark:bg-lavender-900/30 dark:text-lavender-200',
  procurement: 'bg-mint-100 text-mint-700 dark:bg-mint-900/30 dark:text-mint-200',
  productivity:
    'bg-primary-100 text-primary-700 dark:bg-primary-900/30 dark:text-primary-200',
  project_management:
    'bg-lavender-100 text-lavender-700 dark:bg-lavender-900/30 dark:text-lavender-200',
  quality: 'bg-mint-100 text-mint-700 dark:bg-mint-900/30 dark:text-mint-200',
  sales: 'bg-peach-100 text-peach-700 dark:bg-peach-900/30 dark:text-peach-200',
  security: 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-200',
  stock: 'bg-mint-100 text-mint-700 dark:bg-mint-900/30 dark:text-mint-200',
  support: 'bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-200',
  technology:
    'bg-primary-100 text-primary-700 dark:bg-primary-900/30 dark:text-primary-200',
  workflow:
    'bg-primary-100 text-primary-700 dark:bg-primary-900/30 dark:text-primary-200',
};

const DEFAULT_ICON: LucideIcon = Layers;
const DEFAULT_TINT =
  'bg-surface-sunken text-muted-foreground dark:bg-surface-sunken';

/**
 * Normalize arbitrary backend category identifiers into the snake_case
 * form used as keys in {@link CATEGORY_ICONS}. Strips non-alphanumerics,
 * collapses whitespace, and ignores leading/trailing separators.
 */
function normalizeCategoryId(input: string | undefined | null): string {
  if (!input) return '';
  return input
    .toLowerCase()
    .replace(/&/g, 'and')
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

/** Lookup the Lucide icon component for a given category id. */
export function getCategoryIcon(id: string | undefined | null): LucideIcon {
  const key = normalizeCategoryId(id);
  return CATEGORY_ICONS[key] ?? DEFAULT_ICON;
}

/**
 * Lookup the bg/text tint utilities for a given category id.
 * Always returns a valid class string; unknown ids use a neutral tint.
 */
export function getCategoryTint(id: string | undefined | null): string {
  const key = normalizeCategoryId(id);
  return CATEGORY_TINTS[key] ?? DEFAULT_TINT;
}

export type CategoryIconSize = 'xs' | 'sm' | 'md' | 'lg';

const badgeSizeClasses: Record<CategoryIconSize, string> = {
  xs: 'h-5 w-5 rounded-md',
  sm: 'h-7 w-7 rounded-md',
  md: 'h-9 w-9 rounded-lg',
  lg: 'h-11 w-11 rounded-xl',
};

const iconSizeClasses: Record<CategoryIconSize, string> = {
  xs: 'h-3 w-3',
  sm: 'h-3.5 w-3.5',
  md: 'h-[18px] w-[18px]',
  lg: 'h-5 w-5',
};

export interface CategoryIconBadgeProps
  extends Omit<ComponentProps<'div'>, 'children'> {
  /** Category id from the backend. Any shape is accepted. */
  categoryId?: string | null;
  /** Override the looked-up icon (e.g. to force a specific Lucide icon). */
  icon?: LucideIcon;
  /** Override the looked-up tint class string. */
  tintClassName?: string;
  size?: CategoryIconSize;
  /** Optional accessible label. Defaults to aria-hidden. */
  label?: string;
}

/**
 * Square tinted icon badge used in list/card rows in place of an emoji.
 * Keeps the visual weight of the original emoji glyph while swapping in a
 * proper Lucide icon on a calm accent background (§3.2, §3.10).
 */
export function CategoryIconBadge({
  categoryId,
  icon,
  tintClassName,
  size = 'md',
  label,
  className,
  ...rest
}: CategoryIconBadgeProps) {
  const Icon = icon ?? getCategoryIcon(categoryId);
  const tint = tintClassName ?? getCategoryTint(categoryId);
  return (
    <div
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className={cn(
        'inline-flex shrink-0 items-center justify-center',
        badgeSizeClasses[size],
        tint,
        className,
      )}
      {...rest}
    >
      <Icon className={iconSizeClasses[size]} strokeWidth={2} />
    </div>
  );
}

export interface CategoryInlineIconProps {
  categoryId?: string | null;
  icon?: LucideIcon;
  className?: string;
}

/**
 * Minimal inline variant (no background) for use inside dense pills like
 * {@link CategoryFilter}. Picks up the current text color.
 */
export function CategoryInlineIcon({
  categoryId,
  icon,
  className,
}: CategoryInlineIconProps): ReactNode {
  const Icon = icon ?? getCategoryIcon(categoryId);
  return <Icon className={cn('h-3.5 w-3.5', className)} strokeWidth={2} />;
}

export type { LucideIcon };
