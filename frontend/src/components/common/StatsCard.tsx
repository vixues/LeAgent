import { type ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface StatsCardProps {
  title: string;
  value: string | number;
  icon?: ReactNode;
  description?: string;
  trend?: {
    value: number;
    label?: string;
  };
  color?: 'blue' | 'green' | 'yellow' | 'red' | 'gray';
  className?: string;
  onClick?: () => void;
}

const colorMap = {
  blue: {
    icon: 'bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400',
    value: 'text-blue-700 dark:text-blue-300',
  },
  green: {
    icon: 'bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400',
    value: 'text-green-700 dark:text-green-300',
  },
  yellow: {
    icon: 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-600 dark:text-yellow-400',
    value: 'text-yellow-700 dark:text-yellow-300',
  },
  red: {
    icon: 'bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400',
    value: 'text-red-700 dark:text-red-300',
  },
  gray: {
    icon: 'bg-gray-100 dark:bg-surface text-gray-600 dark:text-gray-400',
    value: 'text-gray-700 dark:text-gray-300',
  },
};

function StatsCard({
  title,
  value,
  icon,
  description,
  trend,
  color = 'blue',
  className,
  onClick,
}: StatsCardProps) {
  const colors = colorMap[color];

  const TrendIcon =
    trend && trend.value > 0 ? TrendingUp : trend && trend.value < 0 ? TrendingDown : Minus;
  const trendColor =
    trend && trend.value > 0
      ? 'text-green-600 dark:text-green-400'
      : trend && trend.value < 0
      ? 'text-red-600 dark:text-red-400'
      : 'text-gray-500 dark:text-gray-400';

  return (
    <div
      onClick={onClick}
      className={cn(
        'rounded-xl p-5 bg-surface',
        'border border-gray-200 dark:border-gray-700',
        'flex items-start gap-4',
        onClick && 'cursor-pointer hover:shadow-md transition-shadow',
        className
      )}
    >
      {icon && (
        <div className={cn('flex-shrink-0 w-11 h-11 rounded-xl flex items-center justify-center', colors.icon)}>
          <div className="w-5 h-5">{icon}</div>
        </div>
      )}
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">
          {title}
        </p>
        <p className={cn('text-2xl font-bold tabular-nums', colors.value)}>
          {value}
        </p>
        {(description || trend) && (
          <div className="mt-1 flex items-center gap-2">
            {trend && (
              <span className={cn('flex items-center gap-0.5 text-xs font-medium', trendColor)}>
                <TrendIcon className="w-3 h-3" />
                {Math.abs(trend.value)}%
              </span>
            )}
            {description && (
              <span className="text-xs text-gray-500 dark:text-gray-400">{description}</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
StatsCard.displayName = 'StatsCard';

export { StatsCard };
