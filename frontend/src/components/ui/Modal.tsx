import { Fragment, forwardRef, useMemo, type ReactNode, type HTMLAttributes } from 'react';
import { createPortal } from 'react-dom';
import { cn } from '@/lib/utils';
import { NAV_RAIL_FLOAT_CLASSES } from '@/components/layout/navRailLayout';
import { useLayoutStore } from '@/stores/layout';
import { useMobile } from '@/hooks/useMobile';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  children: ReactNode;
  className?: string;
  size?: 'sm' | 'md' | 'lg' | 'xl' | '2xl';
  /**
   * When true, the backdrop and dialog use the full viewport. Default matches the main work area
   * (to the right of the nav rail) so modals are not covered by the sidebar and are centered
   * over page content. Main-column positioning is disabled on small screens where the rail is a drawer.
   */
  fullViewport?: boolean;
}

const sizeMap = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
  '2xl': 'max-w-4xl',
};

const Modal = ({
  isOpen,
  onClose,
  children,
  className,
  size = 'md',
  fullViewport = false,
}: ModalProps) => {
  const { isMobile } = useMobile();
  const sidebarCollapsed = useLayoutStore((s) => s.sidebarCollapsed);

  const mainAreaClasses = useMemo(() => {
    if (fullViewport || isMobile) {
      return 'inset-0';
    }
    return cn(
      'top-0 right-0 bottom-0',
      sidebarCollapsed ? NAV_RAIL_FLOAT_CLASSES.modalLeftCollapsed : NAV_RAIL_FLOAT_CLASSES.modalLeftExpanded
    );
  }, [fullViewport, isMobile, sidebarCollapsed]);

  if (!isOpen) return null;

  const tree = (
    <Fragment>
      <div
        className={cn(
          'fixed z-[100] bg-black/50 backdrop-blur-sm animate-in',
          mainAreaClasses
        )}
        onClick={onClose}
        aria-hidden
      />
      <div className={cn('fixed z-[100] flex items-center justify-center p-4', mainAreaClasses)}>
        <div
          className={cn(
            'w-full bg-surface rounded-xl shadow-xl',
            'border border-border',
            'slide-in-up max-h-[90vh] overflow-auto',
            sizeMap[size],
            className
          )}
          onClick={(e) => e.stopPropagation()}
        >
          {children}
        </div>
      </div>
    </Fragment>
  );

  if (typeof document === 'undefined') {
    return null;
  }
  return createPortal(tree, document.body);
};
Modal.displayName = 'Modal';

const ModalHeader = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement> & { onClose?: () => void }>(
  ({ children, className, onClose, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        'flex items-center justify-between px-6 py-4 border-b border-border',
        className
      )}
      {...props}
    >
      <h2 className="text-lg font-semibold text-foreground">{children}</h2>
      {onClose && (
        <button
          onClick={onClose}
          className="p-1 text-muted-foreground-tertiary hover:text-foreground rounded-lg hover:bg-surface-sunken dark:hover:bg-surface-elevated transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      )}
    </div>
  )
);
ModalHeader.displayName = 'ModalHeader';

const ModalBody = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ children, className, ...props }, ref) => (
    <div ref={ref} className={cn('px-6 py-4', className)} {...props}>{children}</div>
  )
);
ModalBody.displayName = 'ModalBody';

const ModalFooter = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ children, className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        'flex items-center justify-end gap-3 px-6 py-4 border-t border-border bg-surface-sunken rounded-b-xl',
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
);
ModalFooter.displayName = 'ModalFooter';

export { Modal, ModalHeader, ModalBody, ModalFooter };
