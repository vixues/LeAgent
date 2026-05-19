import {
  forwardRef,
  Fragment,
  createContext,
  useContext,
  useState,
  type ReactNode,
  type HTMLAttributes,
  useCallback,
  useEffect,
} from 'react';
import { createPortal } from 'react-dom';
import { cn } from '@/lib/utils';

interface DialogContextValue {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const DialogContext = createContext<DialogContextValue | undefined>(undefined);

const useDialogContext = () => {
  const context = useContext(DialogContext);
  if (!context) {
    throw new Error('Dialog components must be used within a Dialog');
  }
  return context;
};

interface DialogProps {
  children: ReactNode;
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
}

const Dialog = ({ children, open: controlledOpen, defaultOpen = false, onOpenChange }: DialogProps) => {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(defaultOpen);
  const isControlled = controlledOpen !== undefined;
  const open = isControlled ? controlledOpen : uncontrolledOpen;

  const handleOpenChange = useCallback(
    (newOpen: boolean) => {
      if (!isControlled) {
        setUncontrolledOpen(newOpen);
      }
      onOpenChange?.(newOpen);
    },
    [isControlled, onOpenChange]
  );

  return (
    <DialogContext.Provider value={{ open, onOpenChange: handleOpenChange }}>
      {children}
    </DialogContext.Provider>
  );
};

interface DialogTriggerProps extends HTMLAttributes<HTMLButtonElement> {
  asChild?: boolean;
}

const DialogTrigger = forwardRef<HTMLButtonElement, DialogTriggerProps>(
  ({ children, asChild, onClick, ...props }, ref) => {
    const { onOpenChange } = useDialogContext();

    const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
      onClick?.(e);
      onOpenChange(true);
    };

    if (asChild) {
      return <>{children}</>;
    }

    return (
      <button ref={ref} type="button" onClick={handleClick} {...props}>
        {children}
      </button>
    );
  }
);

DialogTrigger.displayName = 'DialogTrigger';

interface DialogPortalProps {
  children: ReactNode;
}

const DialogPortal = ({ children }: DialogPortalProps) => {
  const { open } = useDialogContext();
  if (!open) return null;
  if (typeof document === 'undefined') return null;
  return createPortal(<Fragment>{children}</Fragment>, document.body);
};

interface DialogOverlayProps extends HTMLAttributes<HTMLDivElement> {}

const DialogOverlay = forwardRef<HTMLDivElement, DialogOverlayProps>(({ className, ...props }, ref) => {
  const { onOpenChange } = useDialogContext();

  return (
    <div
      ref={ref}
      className={cn(
        'fixed inset-0 z-50 bg-black/50 backdrop-blur-sm',
        'animate-in fade-in-0',
        'data-[state=closed]:animate-out data-[state=closed]:fade-out-0',
        className
      )}
      onClick={() => onOpenChange(false)}
      {...props}
    />
  );
});

DialogOverlay.displayName = 'DialogOverlay';

interface DialogContentProps extends HTMLAttributes<HTMLDivElement> {
  onEscapeKeyDown?: () => void;
  onInteractOutside?: () => void;
  size?: 'sm' | 'md' | 'lg' | 'xl';
}

const dialogSizeMap = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
};

const DialogContent = forwardRef<HTMLDivElement, DialogContentProps>(
  ({ className, children, onEscapeKeyDown, size = 'lg', ...props }, ref) => {
    const { onOpenChange } = useDialogContext();

    useEffect(() => {
      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === 'Escape') {
          onEscapeKeyDown?.();
          onOpenChange(false);
        }
      };
      document.addEventListener('keydown', handleKeyDown);
      return () => document.removeEventListener('keydown', handleKeyDown);
    }, [onOpenChange, onEscapeKeyDown]);

    return (
      <DialogPortal>
        <DialogOverlay />
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            ref={ref}
            className={cn(
              'relative w-full rounded-xl bg-surface',
              'border border-border shadow-xl',
              'animate-in fade-in-0 zoom-in-95 slide-in-from-bottom-4',
              'data-[state=closed]:animate-out data-[state=closed]:fade-out-0',
              'data-[state=closed]:zoom-out-95 data-[state=closed]:slide-out-to-bottom-4',
              'max-h-[90vh] overflow-auto',
              dialogSizeMap[size],
              className
            )}
            onClick={(e) => e.stopPropagation()}
            {...props}
          >
            {children}
          </div>
        </div>
      </DialogPortal>
    );
  }
);

DialogContent.displayName = 'DialogContent';

interface DialogHeaderProps extends HTMLAttributes<HTMLDivElement> {}

const DialogHeader = forwardRef<HTMLDivElement, DialogHeaderProps>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn('flex flex-col space-y-1.5 px-6 py-4 border-b border-border', className)}
    {...props}
  />
));

DialogHeader.displayName = 'DialogHeader';

interface DialogTitleProps extends HTMLAttributes<HTMLHeadingElement> {}

const DialogTitle = forwardRef<HTMLHeadingElement, DialogTitleProps>(({ className, ...props }, ref) => (
  <h2
    ref={ref}
    className={cn('text-lg font-semibold text-foreground', className)}
    {...props}
  />
));

DialogTitle.displayName = 'DialogTitle';

interface DialogDescriptionProps extends HTMLAttributes<HTMLParagraphElement> {}

const DialogDescription = forwardRef<HTMLParagraphElement, DialogDescriptionProps>(
  ({ className, ...props }, ref) => (
    <p
      ref={ref}
      className={cn('text-sm text-muted-foreground', className)}
      {...props}
    />
  )
);

DialogDescription.displayName = 'DialogDescription';

interface DialogFooterProps extends HTMLAttributes<HTMLDivElement> {}

const DialogFooter = forwardRef<HTMLDivElement, DialogFooterProps>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      'flex items-center justify-end gap-3 px-6 py-4',
      'border-t border-border',
      'bg-surface-sunken rounded-b-xl',
      className
    )}
    {...props}
  />
));

DialogFooter.displayName = 'DialogFooter';

interface DialogCloseProps extends HTMLAttributes<HTMLButtonElement> {}

const DialogClose = forwardRef<HTMLButtonElement, DialogCloseProps>(
  ({ className, children, onClick, ...props }, ref) => {
    const { onOpenChange } = useDialogContext();

    const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
      onClick?.(e);
      onOpenChange(false);
    };

    return (
      <button
        ref={ref}
        type="button"
        className={cn(
          'absolute right-4 top-4 p-1 rounded-lg',
          'text-muted-foreground-tertiary hover:text-foreground',
          'hover:bg-surface-sunken dark:hover:bg-surface-elevated transition-colors',
          className
        )}
        onClick={handleClick}
        {...props}
      >
        {children || (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        )}
      </button>
    );
  }
);

DialogClose.displayName = 'DialogClose';

export {
  Dialog,
  DialogTrigger,
  DialogPortal,
  DialogOverlay,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
};
