import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { PageHeader } from '@/components/common/PageHeader';

interface BreadcrumbItem {
  label: string;
  href?: string;
  onClick?: () => void;
}

interface PageShellProps {
  /** Optional page title. If omitted (and no `actions`), no PageHeader is rendered. */
  title?: string;
  description?: string;
  icon?: ReactNode;
  badge?: ReactNode;
  actions?: ReactNode;
  breadcrumbs?: BreadcrumbItem[];
  /** Override default title typography (kept for legacy callers; default `text-xl`). */
  titleClassName?: string;
  /** Extra classes on the body container (after the header). */
  contentClassName?: string;
  /**
   * Skip the `max-w-7xl` content column constraint — use when the page needs to
   * span the full WorkPanel width (e.g. FolderPage's two-column explorer).
   */
  fullBleed?: boolean;
  /** Extra classes on the outer shell. */
  className?: string;
  children?: ReactNode;
}

/**
 * Canonical outer wrapper for every non-canvas route.
 *
 * Responsibilities:
 *  - Enforces consistent max-width + centered content column (unless `fullBleed`).
 *  - Owns vertical rhythm between the page header and body (`gap-8` = 32px).
 *  - Never sets `min-h-screen` — scrolling is owned by <WorkPanel/> so the app
 *    shell is the single scroll container (fixes mobile overflow + double
 *    scrollbar issues that plagued pages with their own `min-h-screen`).
 */
export function PageShell({
  title,
  description,
  icon,
  badge,
  actions,
  breadcrumbs,
  titleClassName,
  contentClassName,
  fullBleed = false,
  className,
  children,
}: PageShellProps) {
  const showHeader = Boolean(title || actions || breadcrumbs?.length);

  return (
    <div
      className={cn(
        'flex min-h-0 flex-1 flex-col gap-8',
        !fullBleed && 'mx-auto w-full max-w-7xl',
        className
      )}
    >
      {showHeader && (
        <PageHeader
          title={title ?? ''}
          description={description}
          icon={icon}
          badge={badge}
          actions={actions}
          breadcrumbs={breadcrumbs}
          titleClassName={titleClassName}
          /* mb-0: PageShell's `gap-8` owns the header→body rhythm now. */
          className="mb-0"
        />
      )}
      <div className={cn('flex min-h-0 flex-1 flex-col gap-8 min-w-0', contentClassName)}>
        {children}
      </div>
    </div>
  );
}
PageShell.displayName = 'PageShell';

interface PageSectionProps {
  title?: string;
  description?: string;
  actions?: ReactNode;
  className?: string;
  bodyClassName?: string;
  children?: ReactNode;
}

/**
 * Sub-block inside a PageShell when a page has multiple grouped sections that
 * don't each deserve their own <Card>. Keeps spacing consistent with the shell.
 */
export function PageSection({
  title,
  description,
  actions,
  className,
  bodyClassName,
  children,
}: PageSectionProps) {
  return (
    <section className={cn('flex flex-col gap-4', className)}>
      {(title || actions) && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            {title && (
              <h2 className="text-base font-semibold text-foreground truncate">
                {title}
              </h2>
            )}
            {description && (
              <p className="mt-0.5 text-sm text-muted-foreground truncate">
                {description}
              </p>
            )}
          </div>
          {actions && <div className="flex items-center gap-3">{actions}</div>}
        </div>
      )}
      <div className={cn('space-y-6', bodyClassName)}>{children}</div>
    </section>
  );
}
PageSection.displayName = 'PageSection';
