import {
  forwardRef,
  createContext,
  useContext,
  useState,
  useRef,
  useEffect,
  useLayoutEffect,
  type CSSProperties,
  type ReactNode,
  type HTMLAttributes,
  type ButtonHTMLAttributes,
  useCallback,
} from 'react';
import { createPortal } from 'react-dom';
import { cn } from '@/lib/utils';

interface DropdownContextValue {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  triggerRef: React.RefObject<HTMLButtonElement | null>;
}

const DropdownContext = createContext<DropdownContextValue | undefined>(undefined);

const useDropdownContext = () => {
  const context = useContext(DropdownContext);
  if (!context) {
    throw new Error('DropdownMenu components must be used within a DropdownMenu');
  }
  return context;
};

interface DropdownMenuProps {
  children: ReactNode;
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  /**
   * Use in sidebars / full-width rows: root wrapper becomes `block w-full` so triggers
   * with `w-full` stretch to the parent. Default `inline-block` keeps header icon menus compact.
   */
  fullWidth?: boolean;
}

const DropdownMenu = ({
  children,
  open: controlledOpen,
  defaultOpen = false,
  onOpenChange,
  fullWidth = false,
}: DropdownMenuProps) => {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(defaultOpen);
  const triggerRef = useRef<HTMLButtonElement>(null);
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
    <DropdownContext.Provider value={{ open, onOpenChange: handleOpenChange, triggerRef }}>
      <div
        className={cn(
          'relative',
          fullWidth ? 'block w-full min-w-0' : 'inline-block'
        )}
      >
        {children}
      </div>
    </DropdownContext.Provider>
  );
};

interface DropdownMenuTriggerProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  asChild?: boolean;
}

const DropdownMenuTrigger = forwardRef<HTMLButtonElement, DropdownMenuTriggerProps>(
  ({ children, asChild, onClick, ...props }, ref) => {
    const { open, onOpenChange, triggerRef } = useDropdownContext();

    const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
      onClick?.(e);
      onOpenChange(!open);
    };

    return (
      <button
        ref={(node) => {
          (triggerRef as React.MutableRefObject<HTMLButtonElement | null>).current = node;
          if (typeof ref === 'function') ref(node);
          else if (ref) ref.current = node;
        }}
        type="button"
        aria-expanded={open}
        aria-haspopup="menu"
        data-state={open ? 'open' : 'closed'}
        onClick={handleClick}
        {...props}
      >
        {children}
      </button>
    );
  }
);

DropdownMenuTrigger.displayName = 'DropdownMenuTrigger';

interface DropdownMenuContentProps extends HTMLAttributes<HTMLDivElement> {
  align?: 'start' | 'center' | 'end';
  side?: 'top' | 'bottom';
  sideOffset?: number;
}

const DropdownMenuContent = forwardRef<HTMLDivElement, DropdownMenuContentProps>(
  ({ className, children, align = 'start', side = 'bottom', sideOffset = 4, ...props }, ref) => {
    const { open, onOpenChange, triggerRef } = useDropdownContext();
    const contentRef = useRef<HTMLDivElement>(null);
    const [fixedStyle, setFixedStyle] = useState<CSSProperties>({});

    useEffect(() => {
      if (!open) return;

      const handleClickOutside = (e: MouseEvent) => {
        const target = e.target as Node;
        if (triggerRef.current?.contains(target)) {
          return;
        }
        if (contentRef.current && !contentRef.current.contains(target)) {
          onOpenChange(false);
        }
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

    useLayoutEffect(() => {
      if (!open) {
        setFixedStyle({});
        return;
      }

      const update = () => {
        const trigger = triggerRef.current?.getBoundingClientRect();
        const el = contentRef.current;
        if (!trigger) return;

        const measured = el?.offsetWidth ?? 0;
        /** min-w-[8rem] — used until the menu has painted and measured */
        const menuWidth = measured > 0 ? measured : Math.max(trigger.width, 128);
        const margin = 8;
        let left = trigger.left;
        if (align === 'end') {
          left = trigger.right - menuWidth;
        } else if (align === 'center') {
          left = trigger.left + trigger.width / 2 - menuWidth / 2;
        }
        const vw = typeof window !== 'undefined' ? window.innerWidth : 0;
        if (vw > 0) {
          left = Math.min(Math.max(left, margin), vw - menuWidth - margin);
        }

        if (side === 'top') {
          setFixedStyle({
            left,
            bottom:
              typeof window !== 'undefined'
                ? window.innerHeight - trigger.top + sideOffset
                : undefined,
          });
        } else {
          setFixedStyle({
            left,
            top: trigger.bottom + sideOffset,
          });
        }
      };

      update();
      const raf = requestAnimationFrame(update);
      window.addEventListener('scroll', update, true);
      window.addEventListener('resize', update);

      return () => {
        cancelAnimationFrame(raf);
        window.removeEventListener('scroll', update, true);
        window.removeEventListener('resize', update);
      };
    }, [open, align, side, sideOffset, triggerRef]);

    if (!open) return null;

    const menu = (
      <div
        ref={(node) => {
          (contentRef as React.MutableRefObject<HTMLDivElement | null>).current = node;
          if (typeof ref === 'function') ref(node);
          else if (ref) ref.current = node;
        }}
        role="menu"
        data-side={side}
        className={cn(
          'fixed z-[100] min-w-[8rem] overflow-hidden rounded-xl',
          'bg-surface',
          'border border-gray-200 dark:border-gray-700 shadow-md',
          'animate-in fade-in-0 zoom-in-95',
          side === 'top' ? 'slide-in-from-bottom-2' : 'slide-in-from-top-2',
          className
        )}
        style={fixedStyle}
        {...props}
      >
        <div className="py-1">{children}</div>
      </div>
    );

    if (typeof document === 'undefined') return menu;
    return createPortal(menu, document.body);
  }
);

DropdownMenuContent.displayName = 'DropdownMenuContent';

interface DropdownMenuItemProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  inset?: boolean;
}

const DropdownMenuItem = forwardRef<HTMLButtonElement, DropdownMenuItemProps>(
  ({ className, children, inset, disabled, onClick, ...props }, ref) => {
    const { onOpenChange } = useDropdownContext();

    const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
      if (disabled) return;
      onClick?.(e);
      onOpenChange(false);
    };

    return (
      <button
        ref={ref}
        role="menuitem"
        type="button"
        disabled={disabled}
        className={cn(
          'relative flex w-full cursor-pointer select-none items-center whitespace-nowrap',
          'px-3 py-2 text-sm text-gray-700 dark:text-gray-300',
          'hover:bg-gray-100 dark:hover:bg-gray-800',
          'focus:bg-gray-100 dark:focus:bg-gray-800 focus:outline-none',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          inset && 'pl-8',
          className
        )}
        onClick={handleClick}
        {...props}
      >
        {children}
      </button>
    );
  }
);

DropdownMenuItem.displayName = 'DropdownMenuItem';

interface DropdownMenuLabelProps extends HTMLAttributes<HTMLDivElement> {
  inset?: boolean;
}

const DropdownMenuLabel = forwardRef<HTMLDivElement, DropdownMenuLabelProps>(
  ({ className, inset, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        'px-3 py-2 text-xs font-semibold text-gray-500 dark:text-gray-400',
        inset && 'pl-8',
        className
      )}
      {...props}
    />
  )
);

DropdownMenuLabel.displayName = 'DropdownMenuLabel';

interface DropdownMenuSeparatorProps extends HTMLAttributes<HTMLDivElement> {}

const DropdownMenuSeparator = forwardRef<HTMLDivElement, DropdownMenuSeparatorProps>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      role="separator"
      className={cn('my-1 h-px bg-gray-200 dark:bg-gray-700', className)}
      {...props}
    />
  )
);

DropdownMenuSeparator.displayName = 'DropdownMenuSeparator';

interface DropdownMenuShortcutProps extends HTMLAttributes<HTMLSpanElement> {}

const DropdownMenuShortcut = ({ className, ...props }: DropdownMenuShortcutProps) => (
  <span
    className={cn('ml-auto text-xs tracking-widest text-gray-400 dark:text-gray-500', className)}
    {...props}
  />
);

DropdownMenuShortcut.displayName = 'DropdownMenuShortcut';

export {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
};
