import {
  forwardRef,
  createContext,
  useContext,
  useState,
  useRef,
  useCallback,
  useLayoutEffect,
  type CSSProperties,
  type ReactNode,
  type HTMLAttributes,
} from 'react';
import { createPortal } from 'react-dom';
import { cn } from '@/lib/utils';

interface TooltipContextValue {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  triggerRef: React.RefObject<HTMLElement | null>;
}

const TooltipContext = createContext<TooltipContextValue | undefined>(undefined);

const useTooltipContext = () => {
  const context = useContext(TooltipContext);
  if (!context) {
    throw new Error('Tooltip components must be used within a TooltipProvider');
  }
  return context;
};

interface TooltipProviderProps {
  children: ReactNode;
  delayDuration?: number;
  skipDelayDuration?: number;
}

const TooltipProvider = ({ children }: TooltipProviderProps) => {
  return <>{children}</>;
};

interface TooltipProps {
  children: ReactNode;
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  delayDuration?: number;
}

const Tooltip = ({
  children,
  open: controlledOpen,
  defaultOpen = false,
  onOpenChange,
  delayDuration = 200,
}: TooltipProps) => {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(defaultOpen);
  const triggerRef = useRef<HTMLElement>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const isControlled = controlledOpen !== undefined;
  const open = isControlled ? controlledOpen : uncontrolledOpen;

  const handleOpenChange = useCallback(
    (newOpen: boolean) => {
      clearTimeout(timeoutRef.current);

      if (newOpen) {
        timeoutRef.current = setTimeout(() => {
          if (!isControlled) {
            setUncontrolledOpen(true);
          }
          onOpenChange?.(true);
        }, delayDuration);
      } else {
        if (!isControlled) {
          setUncontrolledOpen(false);
        }
        onOpenChange?.(false);
      }
    },
    [isControlled, onOpenChange, delayDuration]
  );

  return (
    <TooltipContext.Provider value={{ open, onOpenChange: handleOpenChange, triggerRef }}>
      <div className="relative inline-flex">{children}</div>
    </TooltipContext.Provider>
  );
};

interface TooltipTriggerProps extends HTMLAttributes<HTMLDivElement> {
  asChild?: boolean;
}

const TooltipTrigger = forwardRef<HTMLDivElement, TooltipTriggerProps>(
  ({ children, asChild, ...props }, ref) => {
    const { onOpenChange, triggerRef } = useTooltipContext();

    return (
      <div
        ref={(node) => {
          (triggerRef as React.MutableRefObject<HTMLElement | null>).current = node;
          if (typeof ref === 'function') ref(node);
          else if (ref) ref.current = node;
        }}
        onMouseEnter={() => onOpenChange(true)}
        onMouseLeave={() => onOpenChange(false)}
        onFocus={() => onOpenChange(true)}
        onBlur={() => onOpenChange(false)}
        {...props}
      >
        {children}
      </div>
    );
  }
);

TooltipTrigger.displayName = 'TooltipTrigger';

interface TooltipContentProps extends HTMLAttributes<HTMLDivElement> {
  side?: 'top' | 'right' | 'bottom' | 'left';
  align?: 'start' | 'center' | 'end';
  sideOffset?: number;
}

function computeFloatingStyle(
  rect: DOMRect,
  side: NonNullable<TooltipContentProps['side']>,
  align: NonNullable<TooltipContentProps['align']>,
  sideOffset: number
): CSSProperties {
  const base: CSSProperties = { position: 'fixed', zIndex: 9999 };

  switch (side) {
    case 'right':
      return {
        ...base,
        left: rect.right + sideOffset,
        top:
          align === 'start' ? rect.top : align === 'end' ? rect.bottom : rect.top + rect.height / 2,
        transform:
          align === 'center' ? 'translateY(-50%)' : align === 'end' ? 'translateY(-100%)' : undefined,
      };
    case 'left':
      return {
        ...base,
        left: rect.left - sideOffset,
        top:
          align === 'start' ? rect.top : align === 'end' ? rect.bottom : rect.top + rect.height / 2,
        transform:
          align === 'center'
            ? 'translate(-100%, -50%)'
            : align === 'end'
              ? 'translate(-100%, -100%)'
              : 'translateX(-100%)',
      };
    case 'top':
      return {
        ...base,
        left:
          align === 'start' ? rect.left : align === 'end' ? rect.right : rect.left + rect.width / 2,
        top: rect.top - sideOffset,
        transform:
          align === 'center'
            ? 'translate(-50%, -100%)'
            : align === 'end'
              ? 'translate(-100%, -100%)'
              : 'translateY(-100%)',
      };
    case 'bottom':
    default:
      return {
        ...base,
        left:
          align === 'start' ? rect.left : align === 'end' ? rect.right : rect.left + rect.width / 2,
        top: rect.bottom + sideOffset,
        transform:
          align === 'center' ? 'translateX(-50%)' : align === 'end' ? 'translateX(-100%)' : undefined,
      };
  }
}

const TooltipContent = forwardRef<HTMLDivElement, TooltipContentProps>(
  ({ className, children, side = 'top', align = 'center', sideOffset = 4, style, ...props }, ref) => {
    const { open, triggerRef } = useTooltipContext();
    const [floatingStyle, setFloatingStyle] = useState<CSSProperties>({});

    useLayoutEffect(() => {
      if (!open) return;

      const update = () => {
        const el = triggerRef.current;
        if (!el) return;
        setFloatingStyle(computeFloatingStyle(el.getBoundingClientRect(), side, align, sideOffset));
      };

      update();
      window.addEventListener('scroll', update, true);
      window.addEventListener('resize', update);
      return () => {
        window.removeEventListener('scroll', update, true);
        window.removeEventListener('resize', update);
      };
    }, [open, side, align, sideOffset, triggerRef]);

    if (!open || typeof document === 'undefined') return null;

    return createPortal(
      <div
        ref={ref}
        role="tooltip"
        className={cn(
          'overflow-hidden rounded-md px-3 py-1.5',
          'bg-gray-900 dark:bg-gray-100 text-white dark:text-gray-900',
          'text-xs font-medium shadow-md',
          'animate-in fade-in-0 zoom-in-95',
          className
        )}
        style={{ ...floatingStyle, ...style }}
        {...props}
      >
        {children}
      </div>,
      document.body
    );
  }
);

TooltipContent.displayName = 'TooltipContent';

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider };
