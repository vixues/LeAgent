import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

export interface FilterPillOption {
  value: string;
  label: string;
  icon?: ReactNode;
}

export interface FilterPillGroupProps {
  value: string;
  onChange: (value: string) => void;
  options: FilterPillOption[];
  'aria-label'?: string;
  className?: string;
}

/**
 * Compact horizontal pill filter — same visual language as `CategoryFilter`,
 * sized for toolbar rows (templates / workflow hub).
 */
export function FilterPillGroup({
  value,
  onChange,
  options,
  'aria-label': ariaLabel,
  className,
}: FilterPillGroupProps) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className={cn('flex min-w-0 flex-1 flex-wrap items-center gap-1.5', className)}
    >
      {options.map((opt) => {
        const isActive = value === opt.value;
        return (
          <button
            key={opt.value || '__all__'}
            type="button"
            aria-pressed={isActive}
            onClick={() => onChange(opt.value)}
            className={cn(
              'inline-flex shrink-0 items-center gap-1 rounded-full border px-2.5 py-1',
              'text-xs font-medium whitespace-nowrap transition-colors duration-200',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50 focus-visible:ring-offset-2 focus-visible:ring-offset-background',
              isActive
                ? 'border-primary-500/40 bg-primary-50 text-primary-700 shadow-sm dark:border-primary-400/40 dark:bg-primary-900/30 dark:text-primary-200'
                : 'border-border bg-surface text-muted-foreground hover:border-border hover:bg-surface-sunken hover:text-foreground',
            )}
          >
            {opt.icon ? (
              <span className="flex items-center [&>svg]:h-3 [&>svg]:w-3">{opt.icon}</span>
            ) : null}
            <span>{opt.label}</span>
          </button>
        );
      })}
    </div>
  );
}
