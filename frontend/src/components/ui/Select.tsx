import { forwardRef, type SelectHTMLAttributes } from 'react';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'size'> {
  error?: string;
  /** Compact toolbar sizing — matches `Input` `text-xs py-1.5`. */
  selectSize?: 'sm' | 'md';
}

const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, error, selectSize = 'md', children, ...props }, ref) => {
    return (
      <div className="relative">
        <select
          ref={ref}
          className={cn(
            'w-full appearance-none rounded-lg border bg-surface text-foreground transition-colors',
            'focus:outline-none focus:ring-2 focus:ring-primary-500/20',
            'disabled:cursor-not-allowed disabled:opacity-50 disabled:bg-surface-sunken',
            selectSize === 'sm' ? 'py-1.5 pl-3 pr-8 text-xs' : 'px-4 py-2 pr-10 text-sm',
            error
              ? 'border-red-500 focus:border-red-500 focus:ring-red-500/20'
              : 'border-border focus:border-primary-500 dark:focus:border-primary-400',
            className,
          )}
          {...props}
        >
          {children}
        </select>
        <div className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground-tertiary">
          <ChevronDown
            className={cn(selectSize === 'sm' ? 'h-3.5 w-3.5' : 'h-4 w-4')}
            aria-hidden
          />
        </div>
        {error ? <p className="mt-1 text-xs text-red-500">{error}</p> : null}
      </div>
    );
  },
);

Select.displayName = 'Select';

export { Select };
