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
import { X } from 'lucide-react';

interface SheetContextValue {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  side: 'top' | 'right' | 'bottom' | 'left';
}

const SheetContext = createContext<SheetContextValue | undefined>(undefined);

const useSheetContext = () => {
  const context = useContext(SheetContext);
  if (!context) {
    throw new Error('Sheet components must be used within a Sheet');
  }
  return context;
};

interface SheetProps {
  children: ReactNode;
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  side?: 'top' | 'right' | 'bottom' | 'left';
}

const Sheet = ({
  children,
  open: controlledOpen,
  defaultOpen = false,
  onOpenChange,
  side = 'right',
}: SheetProps) => {
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
    <SheetContext.Provider value={{ open, onOpenChange: handleOpenChange, side }}>
      {children}
    </SheetContext.Provider>
  );
};

interface SheetTriggerProps extends HTMLAttributes<HTMLButtonElement> {
  asChild?: boolean;
}

const SheetTrigger = forwardRef<HTMLButtonElement, SheetTriggerProps>(
  ({ children, asChild, onClick, ...props }, ref) => {
    const { onOpenChange } = useSheetContext();

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

SheetTrigger.displayName = 'SheetTrigger';

interface SheetPortalProps {
  children: ReactNode;
}

/** Portals to document.body so fixed layers are not trapped under AppShell's main column (z-10) below NavRail (z-20/z-50). */
const SheetPortal = ({ children }: SheetPortalProps) => {
  const { open } = useSheetContext();
  if (!open) return null;
  if (typeof document === 'undefined') return null;
  return createPortal(<Fragment>{children}</Fragment>, document.body);
};

interface SheetOverlayProps extends HTMLAttributes<HTMLDivElement> {}

const SheetOverlay = forwardRef<HTMLDivElement, SheetOverlayProps>(({ className, ...props }, ref) => {
  const { onOpenChange } = useSheetContext();

  return (
    <div
      ref={ref}
      className={cn(
        'fixed inset-0 z-[80] bg-black/50 backdrop-blur-sm',
        'animate-in fade-in-0',
        'data-[state=closed]:animate-out data-[state=closed]:fade-out-0',
        className
      )}
      onClick={() => onOpenChange(false)}
      {...props}
    />
  );
});

SheetOverlay.displayName = 'SheetOverlay';

interface SheetContentProps extends HTMLAttributes<HTMLDivElement> {
  /** When false, omit the built-in corner close control (use a custom header close instead). */
  showCloseButton?: boolean;
}

const SheetContent = forwardRef<HTMLDivElement, SheetContentProps>(
  ({ className, children, showCloseButton = true, ...props }, ref) => {
    const { onOpenChange, side } = useSheetContext();

    useEffect(() => {
      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === 'Escape') {
          onOpenChange(false);
        }
      };
      document.addEventListener('keydown', handleKeyDown);
      return () => document.removeEventListener('keydown', handleKeyDown);
    }, [onOpenChange]);

    const sideStyles = {
      top: 'inset-x-0 top-0 border-b animate-in slide-in-from-top',
      bottom: 'inset-x-0 bottom-0 border-t animate-in slide-in-from-bottom',
      left: 'inset-y-0 left-0 h-full w-3/4 max-w-sm border-r animate-in slide-in-from-left',
      right: 'inset-y-0 right-0 h-full w-3/4 max-w-sm border-l animate-in slide-in-from-right',
    };

    return (
      <SheetPortal>
        <SheetOverlay />
        <div
          ref={ref}
          className={cn(
            'fixed z-[81] bg-surface shadow-xl',
            'border-gray-200 dark:border-gray-700',
            sideStyles[side],
            className
          )}
          onClick={(e) => e.stopPropagation()}
          {...props}
        >
          {children}
          {showCloseButton ? (
            <button
              type="button"
              onClick={() => onOpenChange(false)}
              className={cn(
                'absolute right-4 top-4 p-1 rounded-lg',
                'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300',
                'hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors'
              )}
              aria-label="Close"
            >
              <X className="w-5 h-5" />
            </button>
          ) : null}
        </div>
      </SheetPortal>
    );
  }
);

SheetContent.displayName = 'SheetContent';

interface SheetHeaderProps extends HTMLAttributes<HTMLDivElement> {}

const SheetHeader = forwardRef<HTMLDivElement, SheetHeaderProps>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn('flex flex-col space-y-1.5 px-6 py-4 border-b border-gray-200 dark:border-gray-700', className)}
    {...props}
  />
));

SheetHeader.displayName = 'SheetHeader';

interface SheetTitleProps extends HTMLAttributes<HTMLHeadingElement> {}

const SheetTitle = forwardRef<HTMLHeadingElement, SheetTitleProps>(({ className, ...props }, ref) => (
  <h2
    ref={ref}
    className={cn('text-lg font-semibold text-gray-900 dark:text-white', className)}
    {...props}
  />
));

SheetTitle.displayName = 'SheetTitle';

interface SheetDescriptionProps extends HTMLAttributes<HTMLParagraphElement> {}

const SheetDescription = forwardRef<HTMLParagraphElement, SheetDescriptionProps>(
  ({ className, ...props }, ref) => (
    <p
      ref={ref}
      className={cn('text-sm text-gray-500 dark:text-gray-400', className)}
      {...props}
    />
  )
);

SheetDescription.displayName = 'SheetDescription';

interface SheetFooterProps extends HTMLAttributes<HTMLDivElement> {}

const SheetFooter = forwardRef<HTMLDivElement, SheetFooterProps>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      'flex items-center justify-end gap-3 px-6 py-4',
      'border-t border-gray-200 dark:border-gray-700',
      'bg-gray-50 dark:bg-gray-800/50',
      className
    )}
    {...props}
  />
));

SheetFooter.displayName = 'SheetFooter';

interface SheetCloseProps extends HTMLAttributes<HTMLButtonElement> {}

const SheetClose = forwardRef<HTMLButtonElement, SheetCloseProps>(
  ({ className, children, onClick, ...props }, ref) => {
    const { onOpenChange } = useSheetContext();

    const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
      onClick?.(e);
      onOpenChange(false);
    };

    return (
      <button
        ref={ref}
        type="button"
        className={className}
        onClick={handleClick}
        {...props}
      >
        {children}
      </button>
    );
  }
);

SheetClose.displayName = 'SheetClose';

export {
  Sheet,
  SheetTrigger,
  SheetPortal,
  SheetOverlay,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter,
  SheetClose,
};
