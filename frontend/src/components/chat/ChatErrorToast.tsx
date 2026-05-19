import { X, AlertTriangle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

interface ChatErrorToastProps {
  message: string;
  onDismiss: () => void;
  className?: string;
}

export function ChatErrorToast({
  message,
  onDismiss,
  className,
}: ChatErrorToastProps) {
  const { t } = useTranslation();

  return (
    <div
      className={cn(
        'flex items-center gap-2 px-3 py-2 rounded-xl',
        'bg-red-50 dark:bg-red-900/20',
        'border border-red-200 dark:border-red-800',
        'shadow-soft',
        'animate-fade-in',
        className,
      )}
      role="alert"
    >
      <AlertTriangle className="w-4 h-4 text-red-500 flex-shrink-0" />
      <p className="text-xs text-red-600 dark:text-red-400 flex-1 min-w-0 truncate">
        {message}
      </p>
      <button
        type="button"
        onClick={onDismiss}
        className="p-1 rounded-md text-red-400 hover:text-red-600 dark:hover:text-red-300 hover:bg-red-100 dark:hover:bg-red-800/30 transition-colors flex-shrink-0"
        aria-label={t('common.dismiss', { defaultValue: 'Dismiss' })}
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
