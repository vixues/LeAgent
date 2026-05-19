import { type ReactNode, useState } from 'react';
import { cn } from '@/lib/utils';
import { AppSidebar } from './AppSidebar';
import { Header } from './Header';

interface MainLayoutProps {
  children: ReactNode;
  showSidebar?: boolean;
  showHeader?: boolean;
  headerTitle?: string;
  headerActions?: ReactNode;
  sidebarCollapsed?: boolean;
  onSidebarCollapsedChange?: (collapsed: boolean) => void;
}

const MainLayout = ({
  children,
  showSidebar = true,
  showHeader = true,
  headerTitle,
  headerActions,
  sidebarCollapsed: controlledCollapsed,
  onSidebarCollapsedChange,
}: MainLayoutProps) => {
  const [uncontrolledCollapsed, setUncontrolledCollapsed] = useState(false);
  const isControlled = controlledCollapsed !== undefined;
  const collapsed = isControlled ? controlledCollapsed : uncontrolledCollapsed;

  const handleCollapsedChange = (value: boolean) => {
    if (!isControlled) {
      setUncontrolledCollapsed(value);
    }
    onSidebarCollapsedChange?.(value);
  };

  return (
    <div className="min-h-screen bg-background">
      {showSidebar && (
        <AppSidebar collapsed={collapsed} onCollapsedChange={handleCollapsedChange} />
      )}

      <div
        className={cn(
          'flex flex-col min-h-screen transition-[color,background-color,border-color,box-shadow,opacity,transform] duration-300',
          showSidebar && (collapsed ? 'ml-16' : 'ml-64')
        )}
      >
        {showHeader && (
          <Header
            title={headerTitle}
            actions={headerActions}
            showMenuButton={!showSidebar}
            onMenuClick={() => handleCollapsedChange(!collapsed)}
          />
        )}

        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
};

interface PageContainerProps {
  children: ReactNode;
  className?: string;
  maxWidth?: 'sm' | 'md' | 'lg' | 'xl' | '2xl' | 'full';
}

const PageContainer = ({
  children,
  className,
  maxWidth = 'full',
}: PageContainerProps) => {
  const maxWidths = {
    sm: 'max-w-screen-sm',
    md: 'max-w-screen-md',
    lg: 'max-w-screen-lg',
    xl: 'max-w-screen-xl',
    '2xl': 'max-w-screen-2xl',
    full: 'max-w-full',
  };

  return (
    <div className={cn('mx-auto w-full', maxWidths[maxWidth], className)}>
      {children}
    </div>
  );
};

interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: ReactNode;
  breadcrumbs?: { label: string; href?: string }[];
  className?: string;
}

const PageHeader = ({
  title,
  description,
  actions,
  breadcrumbs,
  className,
}: PageHeaderProps) => {
  return (
    <div className={cn('mb-6', className)}>
      {breadcrumbs && breadcrumbs.length > 0 && (
        <nav className="flex items-center space-x-2 text-sm text-muted-foreground mb-2">
          {breadcrumbs.map((crumb, index) => (
            <span key={index} className="flex items-center">
              {index > 0 && <span className="mx-2 text-muted-foreground-tertiary">/</span>}
              {crumb.href ? (
                <a
                  href={crumb.href}
                  className="hover:text-primary-600 dark:hover:text-primary-400 transition-colors"
                >
                  {crumb.label}
                </a>
              ) : (
                <span className="text-foreground">{crumb.label}</span>
              )}
            </span>
          ))}
        </nav>
      )}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">{title}</h1>
          {description && (
            <p className="mt-1 text-sm text-muted-foreground">{description}</p>
          )}
        </div>
        {actions && <div className="flex items-center gap-3">{actions}</div>}
      </div>
    </div>
  );
};

interface PageSectionProps {
  title?: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}

const PageSection = ({
  title,
  description,
  actions,
  children,
  className,
}: PageSectionProps) => {
  return (
    <section className={cn('mb-8', className)}>
      {(title || actions) && (
        <div className="flex items-center justify-between mb-4">
          <div>
            {title && (
              <h2 className="text-lg font-semibold text-foreground">
                {title}
              </h2>
            )}
            {description && (
              <p className="text-sm text-muted-foreground">{description}</p>
            )}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
};

export { MainLayout, PageContainer, PageHeader, PageSection };
