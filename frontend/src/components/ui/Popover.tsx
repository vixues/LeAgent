import {
  forwardRef,
  createContext,
  useContext,
  useState,
  useRef,
  useEffect,
  type ReactNode,
  type HTMLAttributes,
  type ButtonHTMLAttributes,
  type ReactElement,
  cloneElement,
  isValidElement,
  useCallback,
} from 'react';
import { cn } from '@/lib/utils';

interface PopoverContextValue {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  triggerRef: React.RefObject<Element | null>;
}

const PopoverContext = createContext<PopoverContextValue | undefined>(undefined);

const usePopoverContext = () => {
  const context = useContext(PopoverContext);
  if (!context) {
    throw new Error('Popover components must be used within a Popover');
  }
  return context;
};

interface PopoverProps {
  children: ReactNode;
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
}

const Popover = ({ children, open: controlledOpen, defaultOpen = false, onOpenChange }: PopoverProps) => {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(defaultOpen);
  const triggerRef = useRef<Element | null>(null);
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
    <PopoverContext.Provider value={{ open, onOpenChange: handleOpenChange, triggerRef }}>
      <div className="relative inline-block">{children}</div>
    </PopoverContext.Provider>
  );
};

interface PopoverTriggerProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  asChild?: boolean;
}

const PopoverTrigger = forwardRef<HTMLButtonElement, PopoverTriggerProps>(
  ({ children, asChild, onClick, ...props }, ref) => {
    const { open, onOpenChange, triggerRef } = usePopoverContext();

    const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
      onClick?.(e);
      onOpenChange(!open);
    };

    return (
      <button
        ref={(node) => {
          (triggerRef as React.MutableRefObject<Element | null>).current = node;
          if (typeof ref === 'function') ref(node);
          else if (ref) ref.current = node;
        }}
        type="button"
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={handleClick}
        {...props}
      >
        {children}
      </button>
    );
  }
);

PopoverTrigger.displayName = 'PopoverTrigger';

interface PopoverClickTriggerProps {
  children: ReactElement;
  disabled?: boolean;
}

/** Toggle target is the child element (e.g. ``<svg>``) — no wrapping ``<button>``. */
function PopoverClickTrigger({ children, disabled = false }: PopoverClickTriggerProps) {
  const { open, onOpenChange, triggerRef } = usePopoverContext();

  if (!isValidElement(children)) {
    throw new Error('PopoverClickTrigger expects a single React element child');
  }

  const childProps = children.props as {
    onClick?: (e: React.MouseEvent) => void;
    onKeyDown?: (e: React.KeyboardEvent) => void;
    ref?: React.Ref<unknown>;
  };

  return cloneElement(children, {
    ref: (node: Element | null) => {
      (triggerRef as React.MutableRefObject<Element | null>).current = node;
      const r = childProps.ref;
      if (typeof r === 'function') r(node);
      else if (r && typeof r === 'object') (r as React.MutableRefObject<unknown>).current = node;
    },
    onClick: (e: React.MouseEvent) => {
      childProps.onClick?.(e);
      if (disabled || e.defaultPrevented) return;
      onOpenChange(!open);
    },
    onKeyDown: (e: React.KeyboardEvent) => {
      childProps.onKeyDown?.(e);
      if (disabled || e.defaultPrevented) return;
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onOpenChange(!open);
      }
    },
    role: (children.props as { role?: string }).role ?? 'button',
    tabIndex: disabled ? -1 : ((children.props as { tabIndex?: number }).tabIndex ?? 0),
    'aria-expanded': open,
    'aria-haspopup': 'dialog',
    'aria-disabled': disabled || undefined,
    className: cn((children.props as { className?: string }).className),
  } as never);
}

PopoverClickTrigger.displayName = 'PopoverClickTrigger';

interface PopoverContentProps extends HTMLAttributes<HTMLDivElement> {
  side?: 'top' | 'right' | 'bottom' | 'left';
  align?: 'start' | 'center' | 'end';
  sideOffset?: number;
  alignOffset?: number;
}

const PopoverContent = forwardRef<HTMLDivElement, PopoverContentProps>(
  (
    {
      className,
      children,
      side = 'bottom',
      align = 'center',
      sideOffset = 4,
      alignOffset = 0,
      ...props
    },
    ref
  ) => {
    const { open, onOpenChange, triggerRef } = usePopoverContext();
    const contentRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
      if (!open) return;

      const handleClickOutside = (e: MouseEvent) => {
        const t = e.target as Node;
        if (contentRef.current?.contains(t)) return;
        if (triggerRef.current?.contains(t)) return;
        onOpenChange(false);
      };

      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === 'Escape') {
          onOpenChange(false);
        }
      };

      document.addEventListener('mousedown', handleClickOutside);
      document.addEventListener('keydown', handleKeyDown);

      return () => {
        document.removeEventListener('mousedown', handleClickOutside);
        document.removeEventListener('keydown', handleKeyDown);
      };
    }, [open, onOpenChange, triggerRef]);

    if (!open) return null;

    const sideStyles = {
      top: 'bottom-full mb-1',
      bottom: 'top-full mt-1',
      left: 'right-full mr-1',
      right: 'left-full ml-1',
    };

    const alignStyles = {
      start: side === 'top' || side === 'bottom' ? 'left-0' : 'top-0',
      center: side === 'top' || side === 'bottom' ? 'left-1/2 -translate-x-1/2' : 'top-1/2 -translate-y-1/2',
      end: side === 'top' || side === 'bottom' ? 'right-0' : 'bottom-0',
    };

    return (
      <div
        ref={(node) => {
          (contentRef as React.MutableRefObject<HTMLDivElement | null>).current = node;
          if (typeof ref === 'function') ref(node);
          else if (ref) ref.current = node;
        }}
        role="dialog"
        className={cn(
          'absolute z-50 w-72 rounded-lg p-4',
          'bg-surface',
          'border border-gray-200 dark:border-gray-700 shadow-lg',
          'animate-in fade-in-0 zoom-in-95',
          sideStyles[side],
          alignStyles[align],
          className
        )}
        style={{ [side === 'top' || side === 'bottom' ? 'marginTop' : 'marginLeft']: sideOffset }}
        {...props}
      >
        {children}
      </div>
    );
  }
);

PopoverContent.displayName = 'PopoverContent';

interface PopoverCloseProps extends HTMLAttributes<HTMLButtonElement> {}

const PopoverClose = forwardRef<HTMLButtonElement, PopoverCloseProps>(
  ({ className, children, onClick, ...props }, ref) => {
    const { onOpenChange } = usePopoverContext();

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

PopoverClose.displayName = 'PopoverClose';

export { Popover, PopoverTrigger, PopoverClickTrigger, PopoverContent, PopoverClose };
