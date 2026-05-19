import { forwardRef, type HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

interface SkeletonProps extends HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'circle' | 'text';
  animation?: 'pulse' | 'wave' | 'none';
}

const Skeleton = forwardRef<HTMLDivElement, SkeletonProps>(
  ({ className, variant = 'default', animation = 'pulse', ...props }, ref) => {
    const variants = {
      default: 'rounded-md',
      circle: 'rounded-full',
      text: 'rounded h-4',
    };

    const animations = {
      pulse: 'animate-pulse',
      wave: 'animate-skeleton-wave',
      none: '',
    };

    return (
      <div
        ref={ref}
        className={cn(
          'bg-gray-200 dark:bg-gray-700',
          variants[variant],
          animations[animation],
          className
        )}
        {...props}
      />
    );
  }
);

Skeleton.displayName = 'Skeleton';

interface SkeletonTextProps extends HTMLAttributes<HTMLDivElement> {
  lines?: number;
  lastLineWidth?: string;
}

const SkeletonText = forwardRef<HTMLDivElement, SkeletonTextProps>(
  ({ className, lines = 3, lastLineWidth = '75%', ...props }, ref) => {
    return (
      <div ref={ref} className={cn('space-y-2', className)} {...props}>
        {Array.from({ length: lines }).map((_, index) => (
          <Skeleton
            key={index}
            variant="text"
            style={index === lines - 1 ? { width: lastLineWidth } : undefined}
          />
        ))}
      </div>
    );
  }
);

SkeletonText.displayName = 'SkeletonText';

interface SkeletonAvatarProps extends HTMLAttributes<HTMLDivElement> {
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
}

const SkeletonAvatar = forwardRef<HTMLDivElement, SkeletonAvatarProps>(
  ({ className, size = 'md', ...props }, ref) => {
    const sizes = {
      xs: 'h-6 w-6',
      sm: 'h-8 w-8',
      md: 'h-10 w-10',
      lg: 'h-12 w-12',
      xl: 'h-16 w-16',
    };

    return (
      <Skeleton
        ref={ref}
        variant="circle"
        className={cn(sizes[size], className)}
        {...props}
      />
    );
  }
);

SkeletonAvatar.displayName = 'SkeletonAvatar';

interface SkeletonCardProps extends HTMLAttributes<HTMLDivElement> {
  hasImage?: boolean;
  hasFooter?: boolean;
}

const SkeletonCard = forwardRef<HTMLDivElement, SkeletonCardProps>(
  ({ className, hasImage = false, hasFooter = false, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          'rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden',
          className
        )}
        {...props}
      >
        {hasImage && <Skeleton className="h-48 w-full rounded-none" />}
        <div className="p-4 space-y-3">
          <Skeleton className="h-6 w-3/4" />
          <SkeletonText lines={2} />
        </div>
        {hasFooter && (
          <div className="px-4 py-3 border-t border-gray-200 dark:border-gray-700 flex justify-between items-center">
            <Skeleton className="h-8 w-20" />
            <Skeleton className="h-8 w-20" />
          </div>
        )}
      </div>
    );
  }
);

SkeletonCard.displayName = 'SkeletonCard';

interface SkeletonTableProps extends HTMLAttributes<HTMLDivElement> {
  rows?: number;
  columns?: number;
}

const SkeletonTable = forwardRef<HTMLDivElement, SkeletonTableProps>(
  ({ className, rows = 5, columns = 4, ...props }, ref) => {
    return (
      <div ref={ref} className={cn('w-full', className)} {...props}>
        <div className="border-b border-gray-200 dark:border-gray-700 pb-2 mb-2">
          <div className="flex gap-4">
            {Array.from({ length: columns }).map((_, index) => (
              <Skeleton key={index} className="h-4 flex-1" />
            ))}
          </div>
        </div>
        <div className="space-y-3">
          {Array.from({ length: rows }).map((_, rowIndex) => (
            <div key={rowIndex} className="flex gap-4">
              {Array.from({ length: columns }).map((_, colIndex) => (
                <Skeleton key={colIndex} className="h-4 flex-1" />
              ))}
            </div>
          ))}
        </div>
      </div>
    );
  }
);

SkeletonTable.displayName = 'SkeletonTable';

export { Skeleton, SkeletonText, SkeletonAvatar, SkeletonCard, SkeletonTable };
