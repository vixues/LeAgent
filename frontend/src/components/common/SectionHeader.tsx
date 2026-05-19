import { type ElementType, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface SectionHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  className?: string;
  titleClassName?: string;
  /** Heading level for a11y / outline. Default `h3` for in-card sections. */
  titleAs?: 'h2' | 'h3';
}

/**
 * In-card / in-section header with icon + title on one row, optional
 * description aligned under the title, and right-aligned actions.
 */
function SectionHeader({
  title,
  description,
  icon,
  actions,
  className,
  titleClassName,
  titleAs = 'h3',
}: SectionHeaderProps) {
  const Heading = titleAs as ElementType;
  const hasDescription = Boolean(description);

  return (
    <div
      className={cn(
        'flex w-full min-w-0 flex-wrap justify-between gap-4 sm:gap-6',
        hasDescription ? 'items-start' : 'items-center',
        className
      )}
    >
      <div className="flex min-w-0 flex-1 flex-col gap-y-0.5">
        <Heading
          className={cn(
            'min-w-0 font-semibold text-foreground',
            titleClassName ?? 'text-lg',
            icon ? 'flex items-center gap-2' : 'truncate'
          )}
        >
          {icon && (
            <span className="shrink-0 text-muted-foreground" aria-hidden="true">
              {icon}
            </span>
          )}
          {icon ? <span className="min-w-0 truncate">{title}</span> : title}
        </Heading>
        {description && (
          <p className="line-clamp-2 text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {actions && (
        <div className="flex flex-shrink-0 flex-wrap items-center gap-2 sm:gap-3">
          {actions}
        </div>
      )}
    </div>
  );
}
SectionHeader.displayName = 'SectionHeader';

export { SectionHeader };
