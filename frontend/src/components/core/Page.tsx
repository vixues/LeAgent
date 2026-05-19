import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface PageProps {
  children: ReactNode;
  className?: string;
}

const Page = ({ children, className }: PageProps) => {
  return (
    <div className={cn('flex flex-col flex-1 gap-6', className)}>
      {children}
    </div>
  );
};

interface PageHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}

const PageHeader = ({ title, description, actions, className }: PageHeaderProps) => {
  return (
    <div className={cn('flex items-center justify-between mb-8 flex-wrap gap-4', className)}>
      <div>
        <h1 className="text-3xl font-bold text-foreground">{title}</h1>
        {description && (
          <p className="mt-2 text-muted-foreground text-sm md:text-base">
            {description}
          </p>
        )}
      </div>
      {actions && <div className="flex items-center gap-3">{actions}</div>}
    </div>
  );
};

interface PageSectionProps {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  headerClassName?: string;
  contentClassName?: string;
}

const PageSection = ({
  title,
  description,
  actions,
  children,
  className,
  headerClassName,
  contentClassName,
}: PageSectionProps) => {
  return (
    <section className={cn('mb-8', className)}>
      {(title || description || actions) && (
        <div className={cn('flex items-center justify-between mb-4 gap-4', headerClassName)}>
          <div>
            {title && (
              <h2 className="text-lg font-semibold text-foreground">{title}</h2>
            )}
            {description && (
              <p className="mt-1 text-sm text-muted-foreground">{description}</p>
            )}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      <div className={contentClassName}>{children}</div>
    </section>
  );
};

interface EmptyStateProps {
  icon?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}

const EmptyState = ({ icon, title, description, action, className }: EmptyStateProps) => {
  return (
    <div
      className={cn(
        'p-10 text-center rounded-2xl border border-dashed border-border bg-surface/60',
        className
      )}
    >
      {icon && (
        <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-surface-sunken flex items-center justify-center">
          {icon}
        </div>
      )}
      <h3 className="text-lg font-semibold text-foreground mb-2">{title}</h3>
      {description && (
        <p className="text-sm text-muted-foreground mb-4 max-w-md mx-auto">
          {description}
        </p>
      )}
      {action}
    </div>
  );
};

export { Page, PageHeader, PageSection, EmptyState };

