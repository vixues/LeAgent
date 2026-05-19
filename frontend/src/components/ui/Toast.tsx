import { forwardRef, type HTMLAttributes, type ReactNode, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { X, CheckCircle, AlertCircle, AlertTriangle, Info } from 'lucide-react';

export type ToastVariant = 'default' | 'success' | 'error' | 'warning' | 'info';

export interface ToastProps extends HTMLAttributes<HTMLDivElement> {
  variant?: ToastVariant;
  title?: string;
  description?: string;
  action?: ReactNode;
  onClose?: () => void;
  duration?: number;
  open?: boolean;
}

const Toast = forwardRef<HTMLDivElement, ToastProps>(
  (
    {
      className,
      variant = 'default',
      title,
      description,
      action,
      onClose,
      duration = 5000,
      open = true,
      ...props
    },
    ref
  ) => {
    useEffect(() => {
      if (!open || duration === Infinity) return;

      const timer = setTimeout(() => {
        onClose?.();
      }, duration);

      return () => clearTimeout(timer);
    }, [open, duration, onClose]);

    if (!open) return null;

    const variants = {
      default: 'bg-surface border-gray-200 dark:border-gray-700',
      success: 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800',
      error: 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800',
      warning: 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800',
      info: 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800',
    };

    const iconColors = {
      default: 'text-gray-500',
      success: 'text-green-500',
      error: 'text-red-500',
      warning: 'text-yellow-500',
      info: 'text-blue-500',
    };

    const icons = {
      default: null,
      success: <CheckCircle className={cn('w-5 h-5', iconColors[variant])} />,
      error: <AlertCircle className={cn('w-5 h-5', iconColors[variant])} />,
      warning: <AlertTriangle className={cn('w-5 h-5', iconColors[variant])} />,
      info: <Info className={cn('w-5 h-5', iconColors[variant])} />,
    };

    return (
      <div
        ref={ref}
        role="alert"
        className={cn(
          'pointer-events-auto relative flex w-full items-start gap-3 overflow-hidden rounded-lg border p-4 shadow-lg',
          'animate-in slide-in-from-right-full',
          variants[variant],
          className
        )}
        {...props}
      >
        {icons[variant]}
        <div className="flex-1 space-y-1">
          {title && (
            <div className="text-sm font-semibold text-gray-900 dark:text-white">{title}</div>
          )}
          {description && (
            <div className="text-sm text-gray-600 dark:text-gray-400">{description}</div>
          )}
        </div>
        {action}
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className={cn(
              'absolute right-2 top-2 p-1 rounded-md',
              'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300',
              'hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors'
            )}
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>
    );
  }
);

Toast.displayName = 'Toast';

interface ToastTitleProps extends HTMLAttributes<HTMLDivElement> {}

const ToastTitle = forwardRef<HTMLDivElement, ToastTitleProps>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn('text-sm font-semibold text-gray-900 dark:text-white', className)}
    {...props}
  />
));

ToastTitle.displayName = 'ToastTitle';

interface ToastDescriptionProps extends HTMLAttributes<HTMLDivElement> {}

const ToastDescription = forwardRef<HTMLDivElement, ToastDescriptionProps>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn('text-sm text-gray-600 dark:text-gray-400', className)}
      {...props}
    />
  )
);

ToastDescription.displayName = 'ToastDescription';

interface ToastActionProps extends HTMLAttributes<HTMLButtonElement> {
  altText: string;
}

const ToastAction = forwardRef<HTMLButtonElement, ToastActionProps>(
  ({ className, altText, ...props }, ref) => (
    <button
      ref={ref}
      type="button"
      className={cn(
        'inline-flex h-8 shrink-0 items-center justify-center rounded-md px-3',
        'text-sm font-medium transition-colors',
        'bg-transparent border border-gray-200 dark:border-gray-700',
        'hover:bg-gray-100 dark:hover:bg-gray-800',
        'focus:outline-none focus:ring-2 focus:ring-primary-500',
        'disabled:pointer-events-none disabled:opacity-50',
        className
      )}
      {...props}
    />
  )
);

ToastAction.displayName = 'ToastAction';

interface ToastCloseProps extends HTMLAttributes<HTMLButtonElement> {}

const ToastClose = forwardRef<HTMLButtonElement, ToastCloseProps>(
  ({ className, ...props }, ref) => (
    <button
      ref={ref}
      type="button"
      className={cn(
        'absolute right-2 top-2 p-1 rounded-md opacity-70',
        'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300',
        'hover:opacity-100 transition-opacity',
        className
      )}
      {...props}
    >
      <X className="w-4 h-4" />
    </button>
  )
);

ToastClose.displayName = 'ToastClose';

export { Toast, ToastTitle, ToastDescription, ToastAction, ToastClose };
