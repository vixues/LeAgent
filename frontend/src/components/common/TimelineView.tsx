import { type ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { CheckCircle, XCircle, Clock, Loader2, AlertTriangle, Circle } from 'lucide-react';

export interface TimelineItem {
  id: string;
  title: string;
  description?: string;
  status: 'success' | 'error' | 'running' | 'pending' | 'warning' | 'skipped';
  time?: string;
  duration?: string;
  meta?: ReactNode;
  details?: ReactNode;
}

interface TimelineViewProps {
  items: TimelineItem[];
  className?: string;
  compact?: boolean;
}

const statusConfig = {
  success: {
    icon: <CheckCircle className="w-4 h-4" />,
    color: 'text-green-500',
    bg: 'bg-green-100 dark:bg-green-900/30',
    line: 'bg-green-200 dark:bg-green-800',
  },
  error: {
    icon: <XCircle className="w-4 h-4" />,
    color: 'text-red-500',
    bg: 'bg-red-100 dark:bg-red-900/30',
    line: 'bg-red-200 dark:bg-red-800',
  },
  running: {
    icon: <Loader2 className="w-4 h-4 animate-spin" />,
    color: 'text-blue-500',
    bg: 'bg-blue-100 dark:bg-blue-900/30',
    line: 'bg-blue-200 dark:bg-blue-800',
  },
  pending: {
    icon: <Circle className="w-4 h-4" />,
    color: 'text-gray-400',
    bg: 'bg-gray-100 dark:bg-surface',
    line: 'bg-gray-200 dark:bg-gray-700',
  },
  warning: {
    icon: <AlertTriangle className="w-4 h-4" />,
    color: 'text-yellow-500',
    bg: 'bg-yellow-100 dark:bg-yellow-900/30',
    line: 'bg-yellow-200 dark:bg-yellow-800',
  },
  skipped: {
    icon: <Clock className="w-4 h-4" />,
    color: 'text-gray-400',
    bg: 'bg-gray-100 dark:bg-surface',
    line: 'bg-gray-200 dark:bg-gray-700',
  },
};

function TimelineView({ items, className, compact = false }: TimelineViewProps) {
  return (
    <div className={cn('relative', className)}>
      {items.map((item, index) => {
        const config = statusConfig[item.status] || statusConfig.pending;
        const isLast = index === items.length - 1;

        return (
          <div key={item.id} className="relative flex gap-3">
            {/* Vertical line */}
            {!isLast && (
              <div
                className={cn(
                  'absolute left-4 top-8 w-0.5',
                  config.line,
                  compact ? 'h-full' : 'h-full min-h-[24px]'
                )}
                style={{ top: '28px', bottom: '-4px' }}
              />
            )}

            {/* Status icon */}
            <div className="flex-shrink-0 z-10">
              <div className={cn('w-8 h-8 rounded-full flex items-center justify-center', config.bg)}>
                <span className={config.color}>{config.icon}</span>
              </div>
            </div>

            {/* Content */}
            <div className={cn('flex-1 min-w-0', compact ? 'pb-3' : 'pb-5')}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                    {item.title}
                  </p>
                  {item.description && (
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 truncate">
                      {item.description}
                    </p>
                  )}
                </div>
                <div className="flex-shrink-0 flex items-center gap-2 text-right">
                  {item.duration && (
                    <span className="text-xs text-gray-400 dark:text-gray-500">
                      {item.duration}
                    </span>
                  )}
                  {item.time && (
                    <span className="text-xs text-gray-400 dark:text-gray-500">{item.time}</span>
                  )}
                </div>
              </div>
              {item.meta && <div className="mt-1">{item.meta}</div>}
              {item.details && (
                <div className="mt-2 p-2 rounded-lg bg-gray-50 dark:bg-surface/50 text-xs">
                  {item.details}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
TimelineView.displayName = 'TimelineView';

export { TimelineView };
