import { forwardRef, type HTMLAttributes } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { LoadingSpinner } from './LoadingSpinner';

interface PageLoaderProps extends HTMLAttributes<HTMLDivElement> {
  message?: string;
  size?: 'sm' | 'md' | 'lg';
}

/** Maps legacy mascot sizes (32 / 64 / 96) to spinner ring sizes for similar visual weight. */
const SPINNER_SIZE: Record<NonNullable<PageLoaderProps['size']>, 'md' | 'lg' | 'xl'> = {
  sm: 'md',
  md: 'lg',
  lg: 'xl',
};

const MESSAGE_TEXT: Record<NonNullable<PageLoaderProps['size']>, string> = {
  sm: 'text-xs',
  md: 'text-sm',
  lg: 'text-base',
};

const GAP: Record<NonNullable<PageLoaderProps['size']>, string> = {
  sm: 'gap-1.5',
  md: 'gap-2',
  lg: 'gap-3',
};

const PageLoader = forwardRef<HTMLDivElement, PageLoaderProps>(
  ({ className, message, size = 'md', ...props }, ref) => {
    const { t } = useTranslation();
    return (
      <div
        ref={ref}
        role="status"
        aria-live="polite"
        aria-label={message || t('common.ariaLoading')}
        className={cn('flex flex-col items-center justify-center', GAP[size], className)}
        {...props}
      >
        <LoadingSpinner size={SPINNER_SIZE[size]} decorative className="shrink-0" />
        {message ? (
          <p
            className={cn(
              'text-center text-gray-500 dark:text-gray-400',
              MESSAGE_TEXT[size],
            )}
          >
            {message}
          </p>
        ) : null}
      </div>
    );
  },
);

PageLoader.displayName = 'PageLoader';

export { PageLoader };
export type { PageLoaderProps };
