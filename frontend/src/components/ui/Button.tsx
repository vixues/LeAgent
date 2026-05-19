import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

export type ResponsiveBreakpoint = 'sm' | 'md' | 'lg' | 'xl';

/** Soft primary surface — matches template cards (“Use template”) and dashboard CTAs. */
export const PRIMARY_SOFT_CTA_CLASSNAME =
  'bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400 hover:bg-primary-100 dark:hover:bg-primary-900/40';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'primarySolid' | 'secondary' | 'ghost' | 'danger' | 'outline';
  size?: 'sm' | 'md' | 'lg' | 'icon';
  loading?: boolean;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
  /**
   * When set, the text label (children) is hidden below the given viewport
   * breakpoint, leaving the icon visible. Requires a `leftIcon` or `rightIcon`
   * for the control to remain recognizable. If no `title`/`aria-label` is
   * provided and `children` is a plain string, it is used automatically so the
   * collapsed icon-only state stays discoverable.
   */
  responsive?: ResponsiveBreakpoint;
}

const responsiveLabelClass: Record<ResponsiveBreakpoint, string> = {
  sm: 'hidden sm:inline',
  md: 'hidden md:inline',
  lg: 'hidden lg:inline',
  xl: 'hidden xl:inline',
};

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant = 'primary',
      size = 'md',
      loading = false,
      disabled,
      leftIcon,
      rightIcon,
      responsive,
      children,
      title,
      'aria-label': ariaLabel,
      ...props
    },
    ref
  ) => {
    const inferredAccessibleName =
      responsive && typeof children === 'string' ? children : undefined;
    const resolvedTitle = title ?? inferredAccessibleName;
    const resolvedAriaLabel = ariaLabel ?? inferredAccessibleName;
    const variants = {
      primary: `${PRIMARY_SOFT_CTA_CLASSNAME} focus:ring-primary-500/40`,
      primarySolid:
        'bg-primary-600 text-white hover:bg-primary-700 focus:ring-primary-500 dark:bg-primary-500 dark:hover:bg-primary-600',
      secondary:
        'bg-surface-sunken text-foreground hover:bg-border-subtle focus:ring-primary-500/50 dark:bg-surface-elevated dark:hover:bg-surface-sunken',
      ghost:
        'bg-transparent text-muted-foreground hover:bg-surface-sunken focus:ring-primary-500/50 dark:hover:bg-surface-elevated',
      danger: 'bg-red-600 text-white hover:bg-red-700 focus:ring-red-500',
      outline:
        'border border-border bg-transparent text-foreground hover:bg-surface-sunken focus:ring-primary-500/50 dark:hover:bg-surface-elevated',
    };

    const sizes = {
      sm: 'px-3 py-1.5 text-xs',
      md: 'px-4 py-2 text-sm',
      lg: 'px-6 py-3 text-base',
      icon: 'p-2',
    };

    const hasChildren = children !== undefined && children !== null && children !== false;

    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        title={resolvedTitle}
        aria-label={resolvedAriaLabel}
        className={cn(
          'inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors duration-200',
          'focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:ring-offset-2 focus:ring-offset-background',
          'active:scale-[0.98]',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          variants[variant],
          sizes[size],
          className
        )}
        {...props}
      >
        {loading ? (
          <svg
            className="animate-spin h-4 w-4 flex-shrink-0"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
        ) : (
          leftIcon && <span className="flex-shrink-0 inline-flex items-center">{leftIcon}</span>
        )}
        {hasChildren && (
          <span
            className={cn(
              'whitespace-nowrap',
              responsive && responsiveLabelClass[responsive]
            )}
          >
            {children}
          </span>
        )}
        {rightIcon && <span className="flex-shrink-0 inline-flex items-center">{rightIcon}</span>}
      </button>
    );
  }
);

Button.displayName = 'Button';

export { Button };
