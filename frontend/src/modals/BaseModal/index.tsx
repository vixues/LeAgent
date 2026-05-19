import { Fragment, useEffect, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

export interface BaseModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  className?: string;
  size?: 'sm' | 'md' | 'lg' | 'xl' | 'full';
  showCloseButton?: boolean;
  closeOnOverlay?: boolean;
  closeOnEscape?: boolean;
  footer?: ReactNode;
}

const sizeStyles = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
  full: 'max-w-4xl',
};

export const BaseModal = ({
  isOpen,
  onClose,
  title,
  children,
  className,
  size = 'md',
  showCloseButton = true,
  closeOnOverlay = true,
  closeOnEscape = true,
  footer,
}: BaseModalProps) => {
  const { t } = useTranslation();

  useEffect(() => {
    if (!closeOnEscape) return;

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose, closeOnEscape]);

  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <Fragment>
      <div
        className={cn(
          'fixed inset-0 z-50 bg-black/50 backdrop-blur-sm',
          'animate-in fade-in duration-200'
        )}
        onClick={closeOnOverlay ? onClose : undefined}
        aria-hidden="true"
      />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
        <div
          className={cn(
            'w-full bg-surface rounded-xl shadow-xl pointer-events-auto',
            'border border-border',
            'animate-in zoom-in-95 slide-in-from-bottom-4 duration-200',
            'max-h-[90vh] flex flex-col',
            sizeStyles[size],
            className
          )}
          onClick={(e) => e.stopPropagation()}
          role="dialog"
          aria-modal="true"
          aria-labelledby={title ? 'modal-title' : undefined}
        >
          {(title || showCloseButton) && (
            <div className="flex items-center justify-between px-6 py-4 border-b border-border shrink-0">
              {title && (
                <h2
                  id="modal-title"
                  className="text-lg font-semibold text-foreground"
                >
                  {title}
                </h2>
              )}
              {showCloseButton && (
                <button
                  onClick={onClose}
                  className={cn(
                    'p-1.5 text-muted-foreground-tertiary hover:text-foreground',
                    'rounded-lg hover:bg-surface-sunken transition-colors',
                    !title && 'ml-auto'
                  )}
                  aria-label={t('common.close')}
                >
                  <svg
                    className="w-5 h-5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                </button>
              )}
            </div>
          )}
          <div className="px-6 py-4 overflow-auto flex-1">{children}</div>
          {footer && (
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-border bg-surface-sunken/50 rounded-b-xl shrink-0">
              {footer}
            </div>
          )}
        </div>
      </div>
    </Fragment>
  );
};

export default BaseModal;
