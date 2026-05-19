import { forwardRef, type HTMLAttributes } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

interface LoadingSpinnerProps extends HTMLAttributes<HTMLDivElement> {
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
  variant?: 'primary' | 'white' | 'gray';
  label?: string;
  /** Hide from assistive tech when a parent (e.g. PageLoader) owns the status region. */
  decorative?: boolean;
}

const LoadingSpinner = forwardRef<HTMLDivElement, LoadingSpinnerProps>(
  ({ className, size = 'md', variant = 'primary', label, decorative = false, ...props }, ref) => {
    const { t } = useTranslation();
    const sizes = {
      xs: 'h-3 w-3',
      sm: 'h-4 w-4',
      md: 'h-6 w-6',
      lg: 'h-8 w-8',
      xl: 'h-12 w-12',
    };

    const borderSizes = {
      xs: 'border',
      sm: 'border-2',
      md: 'border-2',
      lg: 'border-[3px]',
      xl: 'border-4',
    };

    const variants = {
      primary: 'border-primary-600/30 border-t-primary-600',
      white: 'border-white/30 border-t-white',
      gray: 'border-gray-300 dark:border-gray-600 border-t-gray-600 dark:border-t-gray-300',
    };

    return (
      <div
        ref={ref}
        className={cn('flex items-center justify-center gap-2', className)}
        {...(decorative
          ? { 'aria-hidden': true as const }
          : {
              role: 'status' as const,
              'aria-label': label || t('common.ariaLoading'),
            })}
        {...props}
      >
        <div
          className={cn(
            'animate-spin rounded-full',
            sizes[size],
            borderSizes[size],
            variants[variant]
          )}
        />
        {label && (
          <span className="text-sm text-gray-600 dark:text-gray-400">{label}</span>
        )}
      </div>
    );
  }
);

LoadingSpinner.displayName = 'LoadingSpinner';

interface LoadingOverlayProps extends HTMLAttributes<HTMLDivElement> {
  loading?: boolean;
  label?: string;
  blur?: boolean;
}

const LoadingOverlay = forwardRef<HTMLDivElement, LoadingOverlayProps>(
  ({ className, children, loading = false, label, blur = false, ...props }, ref) => {
    return (
      <div ref={ref} className={cn('relative', className)} {...props}>
        {children}
        {loading && (
          <div
            className={cn(
              'absolute inset-0 flex items-center justify-center',
              'bg-surface/80 z-10',
              blur && 'backdrop-blur-sm'
            )}
          >
            <LoadingSpinner size="lg" label={label} />
          </div>
        )}
      </div>
    );
  }
);

LoadingOverlay.displayName = 'LoadingOverlay';

interface LoadingDotsProps extends HTMLAttributes<HTMLDivElement> {
  size?: 'sm' | 'md' | 'lg';
}

const LoadingDots = forwardRef<HTMLDivElement, LoadingDotsProps>(
  ({ className, size = 'md', ...props }, ref) => {
    const { t } = useTranslation();
    const sizes = {
      sm: 'h-1.5 w-1.5',
      md: 'h-2 w-2',
      lg: 'h-3 w-3',
    };

    return (
      <div
        ref={ref}
        className={cn('flex items-center gap-1', className)}
        role="status"
        aria-label={t('common.ariaLoading')}
        {...props}
      >
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className={cn(
              'rounded-full bg-gray-600 dark:bg-gray-400 animate-pulse',
              sizes[size]
            )}
            style={{ animationDelay: `${i * 150}ms` }}
          />
        ))}
      </div>
    );
  }
);

LoadingDots.displayName = 'LoadingDots';

export { LoadingSpinner, LoadingOverlay, LoadingDots };
