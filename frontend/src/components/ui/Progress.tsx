import { forwardRef, type HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

interface ProgressProps extends HTMLAttributes<HTMLDivElement> {
  value?: number;
  max?: number;
  variant?: 'default' | 'success' | 'warning' | 'error';
  size?: 'sm' | 'md' | 'lg';
  showValue?: boolean;
  indeterminate?: boolean;
}

const Progress = forwardRef<HTMLDivElement, ProgressProps>(
  (
    {
      className,
      value = 0,
      max = 100,
      variant = 'default',
      size = 'md',
      showValue = false,
      indeterminate = false,
      ...props
    },
    ref
  ) => {
    const percentage = Math.min(100, Math.max(0, (value / max) * 100));

    const variants = {
      default: 'bg-primary-600 dark:bg-primary-500',
      success: 'bg-green-600 dark:bg-green-500',
      warning: 'bg-yellow-600 dark:bg-yellow-500',
      error: 'bg-red-600 dark:bg-red-500',
    };

    const sizes = {
      sm: 'h-1',
      md: 'h-2',
      lg: 'h-3',
    };

    return (
      <div className={cn('w-full', className)}>
        <div
          ref={ref}
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={max}
          aria-valuenow={indeterminate ? undefined : value}
          className={cn(
            'w-full overflow-hidden rounded-full bg-gray-200 dark:bg-gray-700',
            sizes[size]
          )}
          {...props}
        >
          <div
            className={cn(
              'h-full rounded-full transition-[width] duration-300 ease-in-out',
              variants[variant],
              indeterminate && 'animate-progress-indeterminate'
            )}
            style={indeterminate ? { width: '50%' } : { width: `${percentage}%` }}
          />
        </div>
        {showValue && !indeterminate && (
          <div className="mt-1 text-xs text-gray-500 dark:text-gray-400 text-right">
            {Math.round(percentage)}%
          </div>
        )}
      </div>
    );
  }
);

Progress.displayName = 'Progress';

interface CircularProgressProps extends HTMLAttributes<HTMLDivElement> {
  value?: number;
  max?: number;
  size?: number;
  strokeWidth?: number;
  variant?: 'default' | 'success' | 'warning' | 'error';
  showValue?: boolean;
  indeterminate?: boolean;
}

const CircularProgress = forwardRef<HTMLDivElement, CircularProgressProps>(
  (
    {
      className,
      value = 0,
      max = 100,
      size = 48,
      strokeWidth = 4,
      variant = 'default',
      showValue = false,
      indeterminate = false,
      ...props
    },
    ref
  ) => {
    const percentage = Math.min(100, Math.max(0, (value / max) * 100));
    const radius = (size - strokeWidth) / 2;
    const circumference = radius * 2 * Math.PI;
    const offset = circumference - (percentage / 100) * circumference;

    const strokeColors = {
      default: 'stroke-primary-600 dark:stroke-primary-500',
      success: 'stroke-green-600 dark:stroke-green-500',
      warning: 'stroke-yellow-600 dark:stroke-yellow-500',
      error: 'stroke-red-600 dark:stroke-red-500',
    };

    return (
      <div
        ref={ref}
        className={cn('relative inline-flex items-center justify-center', className)}
        style={{ width: size, height: size }}
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={indeterminate ? undefined : value}
        {...props}
      >
        <svg
          className={cn('transform -rotate-90', indeterminate && 'animate-spin')}
          width={size}
          height={size}
        >
          <circle
            className="stroke-gray-200 dark:stroke-gray-700"
            fill="none"
            strokeWidth={strokeWidth}
            r={radius}
            cx={size / 2}
            cy={size / 2}
          />
          <circle
            className={cn(strokeColors[variant], 'transition-[stroke-dashoffset] duration-300 ease-in-out')}
            fill="none"
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            r={radius}
            cx={size / 2}
            cy={size / 2}
            strokeDasharray={circumference}
            strokeDashoffset={indeterminate ? circumference * 0.75 : offset}
          />
        </svg>
        {showValue && !indeterminate && (
          <span className="absolute text-xs font-medium text-gray-700 dark:text-gray-300">
            {Math.round(percentage)}%
          </span>
        )}
      </div>
    );
  }
);

CircularProgress.displayName = 'CircularProgress';

export { Progress, CircularProgress };
