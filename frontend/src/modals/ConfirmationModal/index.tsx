import { useTranslation } from 'react-i18next';
import { BaseModal } from '../BaseModal';
import { Button } from '@/components/ui/Button';
import { cn } from '@/lib/utils';

type ConfirmationType = 'info' | 'warning' | 'danger';

interface ConfirmationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title?: string;
  message: string;
  type?: ConfirmationType;
  confirmText?: string;
  cancelText?: string;
  loading?: boolean;
}

const typeStyles: Record<ConfirmationType, { icon: string; iconClass: string; buttonVariant: 'primary' | 'danger' }> = {
  info: {
    icon: 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
    iconClass: 'text-primary-600 dark:text-primary-400 bg-primary-100 dark:bg-primary-900/30',
    buttonVariant: 'primary',
  },
  warning: {
    icon: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z',
    iconClass: 'text-amber-600 dark:text-amber-400 bg-amber-100 dark:bg-amber-900/30',
    buttonVariant: 'primary',
  },
  danger: {
    icon: 'M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16',
    iconClass: 'text-red-600 dark:text-red-400 bg-red-100 dark:bg-red-900/30',
    buttonVariant: 'danger',
  },
};

export const ConfirmationModal = ({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  type = 'info',
  confirmText,
  cancelText,
  loading = false,
}: ConfirmationModalProps) => {
  const { t } = useTranslation();
  const styles = typeStyles[type];

  const handleConfirm = () => {
    onConfirm();
  };

  const footer = (
    <>
      <Button variant="outline" onClick={onClose} disabled={loading}>
        {cancelText || t('common.cancel')}
      </Button>
      <Button
        variant={styles.buttonVariant}
        onClick={handleConfirm}
        loading={loading}
      >
        {confirmText || t('common.confirm')}
      </Button>
    </>
  );

  return (
    <BaseModal
      isOpen={isOpen}
      onClose={onClose}
      size="sm"
      footer={footer}
      closeOnOverlay={!loading}
      closeOnEscape={!loading}
    >
      <div className="flex flex-col items-center text-center py-4">
        <div className={cn('w-12 h-12 rounded-full flex items-center justify-center mb-4', styles.iconClass)}>
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={styles.icon} />
          </svg>
        </div>

        {title && (
          <h3 className="text-lg font-semibold text-foreground mb-2">
            {title}
          </h3>
        )}

        <p className="text-muted-foreground">{message}</p>
      </div>
    </BaseModal>
  );
};

export default ConfirmationModal;
