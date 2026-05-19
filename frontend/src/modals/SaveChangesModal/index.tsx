import { useTranslation } from 'react-i18next';
import { BaseModal } from '../BaseModal';
import { Button } from '@/components/ui/Button';


interface SaveChangesModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: () => void;
  onDiscard: () => void;
  title?: string;
  message?: string;
  saveText?: string;
  discardText?: string;
  cancelText?: string;
  saving?: boolean;
}

export const SaveChangesModal = ({
  isOpen,
  onClose,
  onSave,
  onDiscard,
  title,
  message,
  saveText,
  discardText,
  cancelText,
  saving = false,
}: SaveChangesModalProps) => {
  const { t } = useTranslation();

  const footer = (
    <>
      <Button variant="outline" onClick={onClose} disabled={saving}>
        {cancelText || t('common.cancel')}
      </Button>
      <Button
        variant="danger"
        onClick={onDiscard}
        disabled={saving}
      >
        {discardText || t('modals.saveChanges.discard')}
      </Button>
      <Button onClick={onSave} loading={saving}>
        {saveText || t('common.save')}
      </Button>
    </>
  );

  return (
    <BaseModal
      isOpen={isOpen}
      onClose={onClose}
      size="sm"
      footer={footer}
      closeOnOverlay={!saving}
      closeOnEscape={!saving}
    >
      <div className="flex flex-col items-center text-center py-4">
        <div className="w-12 h-12 rounded-full flex items-center justify-center mb-4 bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
          </svg>
        </div>

        <h3 className="text-lg font-semibold text-foreground mb-2">
          {title || t('modals.saveChanges.title')}
        </h3>

        <p className="text-muted-foreground">
          {message || t('modals.saveChanges.message')}
        </p>

        <div className="mt-4 p-3 bg-surface-sunken rounded-lg w-full">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <span>{t('modals.saveChanges.hint')}</span>
          </div>
        </div>
      </div>
    </BaseModal>
  );
};

export default SaveChangesModal;
