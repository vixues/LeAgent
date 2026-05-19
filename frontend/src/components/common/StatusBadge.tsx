import { forwardRef, type HTMLAttributes, type ReactNode } from 'react';
import { cn } from '@/lib/utils';
import type { ResponsiveBreakpoint } from '@/components/ui/Button';
import {
  CheckCircle,
  XCircle,
  Clock,
  AlertTriangle,
  Loader2,
  Pause,
  Play,
  Ban,
  HelpCircle,
  SkipForward,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

type StatusType =
  | 'pending'
  | 'running'
  | 'success'
  | 'error'
  | 'warning'
  | 'paused'
  | 'cancelled'
  | 'skipped'
  | 'draft'
  | 'active'
  | 'inactive'
  | 'unknown';

interface StatusBadgeProps extends HTMLAttributes<HTMLSpanElement> {
  status: StatusType;
  showIcon?: boolean;
  showLabel?: boolean;
  size?: 'sm' | 'md' | 'lg';
  pulse?: boolean;
  customLabel?: string;
  /**
   * When set, the label is hidden below the given viewport breakpoint so the
   * badge collapses to icon-only in tight toolbars. The full label is kept as
   * `title` for accessibility.
   */
  responsive?: ResponsiveBreakpoint;
}

const responsiveLabelClass: Record<ResponsiveBreakpoint, string> = {
  sm: 'hidden sm:inline',
  md: 'hidden md:inline',
  lg: 'hidden lg:inline',
  xl: 'hidden xl:inline',
};

const StatusBadge = forwardRef<HTMLSpanElement, StatusBadgeProps>(
  (
    {
      className,
      status,
      showIcon = true,
      showLabel = true,
      size = 'md',
      pulse = false,
      customLabel,
      responsive,
      title,
      ...props
    },
    ref
  ) => {
    const { t } = useTranslation();

    const statusConfig: Record<
      StatusType,
      {
        label: string;
        icon: ReactNode;
        colors: string;
        dotColor: string;
      }
    > = {
      pending: {
        label: t('status.pending'),
        icon: <Clock className="w-full h-full" />,
        colors: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
        dotColor: 'bg-gray-500',
      },
      running: {
        label: t('status.running'),
        icon: <Loader2 className="w-full h-full animate-spin" />,
        colors: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
        dotColor: 'bg-blue-500',
      },
      success: {
        label: t('status.success'),
        icon: <CheckCircle className="w-full h-full" />,
        colors: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
        dotColor: 'bg-green-500',
      },
      error: {
        label: t('status.error'),
        icon: <XCircle className="w-full h-full" />,
        colors: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
        dotColor: 'bg-red-500',
      },
      warning: {
        label: t('status.warning'),
        icon: <AlertTriangle className="w-full h-full" />,
        colors: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300',
        dotColor: 'bg-yellow-500',
      },
      paused: {
        label: t('status.paused'),
        icon: <Pause className="w-full h-full" />,
        colors: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300',
        dotColor: 'bg-orange-500',
      },
      cancelled: {
        label: t('status.cancelled'),
        icon: <Ban className="w-full h-full" />,
        colors: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
        dotColor: 'bg-gray-400',
      },
      skipped: {
        label: t('status.skipped'),
        icon: <SkipForward className="w-full h-full" />,
        colors: 'bg-slate-100 text-slate-700 dark:bg-slate-800/50 dark:text-slate-300',
        dotColor: 'bg-slate-400',
      },
      draft: {
        label: t('status.draft'),
        icon: <HelpCircle className="w-full h-full" />,
        colors: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
        dotColor: 'bg-gray-400',
      },
      active: {
        label: t('status.active'),
        icon: <Play className="w-full h-full" />,
        colors: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
        dotColor: 'bg-green-500',
      },
      inactive: {
        label: t('status.inactive'),
        icon: <Pause className="w-full h-full" />,
        colors: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
        dotColor: 'bg-gray-400',
      },
      unknown: {
        label: t('status.unknown'),
        icon: <HelpCircle className="w-full h-full" />,
        colors: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
        dotColor: 'bg-gray-400',
      },
    };

    const config = statusConfig[status] || statusConfig.unknown;

    const sizes = {
      sm: {
        container: 'px-1.5 py-0.5 text-xs gap-1',
        icon: 'w-3 h-3',
        dot: 'w-1.5 h-1.5',
      },
      md: {
        container: 'px-2 py-0.5 text-xs gap-1.5',
        icon: 'w-3.5 h-3.5',
        dot: 'w-2 h-2',
      },
      lg: {
        container: 'px-2.5 py-1 text-sm gap-2',
        icon: 'w-4 h-4',
        dot: 'w-2.5 h-2.5',
      },
    };

    const sizeConfig = sizes[size];
    const resolvedLabel = customLabel || config.label;
    const resolvedTitle = title ?? (responsive ? resolvedLabel : undefined);

    return (
      <span
        ref={ref}
        title={resolvedTitle}
        className={cn(
          'inline-flex items-center rounded-full font-medium whitespace-nowrap',
          config.colors,
          sizeConfig.container,
          className
        )}
        {...props}
      >
        {showIcon && (
          <span className={cn('flex-shrink-0', sizeConfig.icon)}>{config.icon}</span>
        )}
        {!showIcon && pulse && (
          <span className="relative flex-shrink-0">
            <span className={cn('rounded-full', config.dotColor, sizeConfig.dot)} />
            {(status === 'running' || status === 'active') && (
              <span
                className={cn(
                  'absolute inset-0 rounded-full animate-ping opacity-75',
                  config.dotColor
                )}
              />
            )}
          </span>
        )}
        {showLabel && (
          <span
            className={cn(
              'whitespace-nowrap',
              responsive && responsiveLabelClass[responsive]
            )}
          >
            {resolvedLabel}
          </span>
        )}
      </span>
    );
  }
);

StatusBadge.displayName = 'StatusBadge';

interface StatusDotProps extends HTMLAttributes<HTMLSpanElement> {
  status: StatusType;
  size?: 'sm' | 'md' | 'lg';
  pulse?: boolean;
}

const StatusDot = forwardRef<HTMLSpanElement, StatusDotProps>(
  ({ className, status, size = 'md', pulse = false, ...props }, ref) => {
    const dotColors: Record<StatusType, string> = {
      pending: 'bg-gray-500',
      running: 'bg-blue-500',
      success: 'bg-green-500',
      error: 'bg-red-500',
      warning: 'bg-yellow-500',
      paused: 'bg-orange-500',
      cancelled: 'bg-gray-400',
      skipped: 'bg-slate-400',
      draft: 'bg-gray-400',
      active: 'bg-green-500',
      inactive: 'bg-gray-400',
      unknown: 'bg-gray-400',
    };

    const sizes = {
      sm: 'w-1.5 h-1.5',
      md: 'w-2 h-2',
      lg: 'w-3 h-3',
    };

    const color = dotColors[status] || dotColors.unknown;
    const shouldPulse = pulse && (status === 'running' || status === 'active');

    return (
      <span ref={ref} className={cn('relative inline-flex', className)} {...props}>
        <span className={cn('rounded-full', color, sizes[size])} />
        {shouldPulse && (
          <span
            className={cn(
              'absolute inset-0 rounded-full animate-ping opacity-75',
              color
            )}
          />
        )}
      </span>
    );
  }
);

StatusDot.displayName = 'StatusDot';

export { StatusBadge, StatusDot, type StatusType };
