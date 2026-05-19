import { forwardRef, useState, type HTMLAttributes, type ImgHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

interface AvatarProps extends HTMLAttributes<HTMLDivElement> {
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
}

const Avatar = forwardRef<HTMLDivElement, AvatarProps>(
  ({ className, size = 'md', ...props }, ref) => {
    const sizes = {
      xs: 'h-6 w-6',
      sm: 'h-8 w-8',
      md: 'h-10 w-10',
      lg: 'h-12 w-12',
      xl: 'h-16 w-16',
    };

    return (
      <div
        ref={ref}
        className={cn(
          'relative flex shrink-0 overflow-hidden rounded-full',
          'bg-gray-100 dark:bg-gray-800',
          sizes[size],
          className
        )}
        {...props}
      />
    );
  }
);

Avatar.displayName = 'Avatar';

interface AvatarImageProps extends ImgHTMLAttributes<HTMLImageElement> {}

const AvatarImage = forwardRef<HTMLImageElement, AvatarImageProps>(
  ({ className, src, alt = '', onError, ...props }, ref) => {
    const [hasError, setHasError] = useState(false);

    if (!src || hasError) {
      return null;
    }

    return (
      <img
        ref={ref}
        src={src}
        alt={alt}
        className={cn('aspect-square h-full w-full object-cover', className)}
        onError={(e) => {
          setHasError(true);
          onError?.(e);
        }}
        {...props}
      />
    );
  }
);

AvatarImage.displayName = 'AvatarImage';

interface AvatarFallbackProps extends HTMLAttributes<HTMLDivElement> {
  delayMs?: number;
}

const AvatarFallback = forwardRef<HTMLDivElement, AvatarFallbackProps>(
  ({ className, children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={cn(
          'flex h-full w-full items-center justify-center rounded-full',
          'bg-gray-200 dark:bg-gray-700',
          'text-gray-600 dark:text-gray-300 font-medium',
          className
        )}
        {...props}
      >
        {children}
      </div>
    );
  }
);

AvatarFallback.displayName = 'AvatarFallback';

interface AvatarGroupProps extends HTMLAttributes<HTMLDivElement> {
  max?: number;
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
}

const AvatarGroup = forwardRef<HTMLDivElement, AvatarGroupProps>(
  ({ className, children, max = 4, size = 'md', ...props }, ref) => {
    const childArray = Array.isArray(children) ? children : [children];
    const visibleAvatars = childArray.slice(0, max);
    const remainingCount = childArray.length - max;

    const sizes = {
      xs: 'h-6 w-6 text-xs',
      sm: 'h-8 w-8 text-xs',
      md: 'h-10 w-10 text-sm',
      lg: 'h-12 w-12 text-sm',
      xl: 'h-16 w-16 text-base',
    };

    return (
      <div ref={ref} className={cn('flex -space-x-2', className)} {...props}>
        {visibleAvatars}
        {remainingCount > 0 && (
          <div
            className={cn(
              'relative flex shrink-0 items-center justify-center rounded-full',
              'bg-gray-200 dark:bg-gray-700 border-2 border-white dark:border-gray-900',
              'text-gray-600 dark:text-gray-300 font-medium',
              sizes[size]
            )}
          >
            +{remainingCount}
          </div>
        )}
      </div>
    );
  }
);

AvatarGroup.displayName = 'AvatarGroup';

export { Avatar, AvatarImage, AvatarFallback, AvatarGroup };
