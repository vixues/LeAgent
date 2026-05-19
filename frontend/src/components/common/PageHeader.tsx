import { type ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface BreadcrumbItem {
  label: string;
  href?: string;
  onClick?: () => void;
}

interface PageHeaderProps {
  title: string;
  description?: string;
  icon?: ReactNode;
  breadcrumbs?: BreadcrumbItem[];
  actions?: ReactNode;
  className?: string;
  /** Override default title typography (default: text-xl) */
  titleClassName?: string;
  badge?: ReactNode;
}

function PageHeader({
  title,
  description,
  icon,
  breadcrumbs,
  actions,
  className,
  titleClassName,
  badge,
}: PageHeaderProps) {
  return (
    // NOTE: No built-in `mb-6` anymore — vertical rhythm is owned by the
    // parent (<PageShell/> uses `gap-8`). Callers that still need spacing
    // can pass it via `className`.
    <div className={cn('flex flex-col gap-1', className)}>
      {breadcrumbs && breadcrumbs.length > 0 && (
        <nav className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground mb-1">
          {breadcrumbs.map((item, i) => (
            <span key={i} className="flex items-center gap-1.5 whitespace-nowrap">
              {i > 0 && <span className="text-muted-foreground-tertiary">/</span>}
              {item.href || item.onClick ? (
                <button
                  type="button"
                  onClick={item.onClick}
                  className="text-muted-foreground hover:text-foreground transition-colors whitespace-nowrap"
                >
                  {item.label}
                </button>
              ) : (
                <span className="text-foreground whitespace-nowrap">{item.label}</span>
              )}
            </span>
          ))}
        </nav>
      )}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          {icon && (
            <div className="flex-shrink-0 w-10 h-10 rounded-xl bg-primary-100 dark:bg-primary-900/30 flex items-center justify-center text-primary-600 dark:text-primary-400">
              {icon}
            </div>
          )}
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 min-w-0">
              <h1
                className={cn(
                  'font-semibold text-foreground truncate whitespace-nowrap min-w-0',
                  titleClassName ?? 'text-xl'
                )}
              >
                {title}
              </h1>
              {badge && <span className="flex-shrink-0 whitespace-nowrap">{badge}</span>}
            </div>
            {description && (
              <p className="text-sm text-muted-foreground mt-0.5 truncate whitespace-nowrap">
                {description}
              </p>
            )}
          </div>
        </div>
        {actions && (
          // gap-3 (12px): minimum comfortable gap between action buttons;
          // standardized so every page header feels the same.
          <div className="flex items-center gap-3 flex-shrink-0">{actions}</div>
        )}
      </div>
    </div>
  );
}
PageHeader.displayName = 'PageHeader';

export { PageHeader };
