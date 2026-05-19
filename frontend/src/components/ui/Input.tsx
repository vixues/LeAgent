import { forwardRef, type InputHTMLAttributes, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
  error?: string;
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, leftIcon, rightIcon, error, ...props }, ref) => {
    return (
      <div className="relative">
        {leftIcon && (
          <div className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground-tertiary">
            {leftIcon}
          </div>
        )}
        <input
          ref={ref}
          className={cn(
            'w-full rounded-lg border bg-surface px-4 py-2 text-sm text-foreground transition-colors placeholder:text-muted-foreground-tertiary',
            'focus:outline-none focus:ring-2 focus:ring-primary-500/20',
            'disabled:opacity-60 disabled:bg-surface-sunken disabled:border-border-subtle',
            'dark:bg-surface-elevated',
            error
              ? 'border-red-500 focus:border-red-500 focus:ring-red-500/20'
              : 'border-border focus:border-primary-500 dark:focus:border-primary-400',
            leftIcon && 'pl-10',
            rightIcon && 'pr-10',
            className
          )}
          {...props}
        />
        {rightIcon && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground-tertiary">
            {rightIcon}
          </div>
        )}
        {error && <p className="mt-1 text-xs text-red-500">{error}</p>}
      </div>
    );
  }
);

Input.displayName = 'Input';

export { Input };
