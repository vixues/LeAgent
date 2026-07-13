import { ChevronRight, Home } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

export interface BreadcrumbItem {
  id: string | null;
  name: string;
}

interface FolderBreadcrumbProps {
  items: BreadcrumbItem[];
  onNavigate: (id: string | null) => void;
  /** Root crumb label. Defaults to `folders.root`. */
  rootLabel?: string;
  /** Nav aria-label. Defaults to `folders.breadcrumbAria`. */
  ariaLabel?: string;
}

/** Inline breadcrumb for folder navigation (Folders / Knowledge pages). */
export default function FolderBreadcrumb({
  items,
  onNavigate,
  rootLabel,
  ariaLabel,
}: FolderBreadcrumbProps) {
  const { t } = useTranslation();
  return (
    <nav
      className="flex items-center gap-1.5 text-xs text-muted-foreground overflow-x-auto"
      aria-label={ariaLabel ?? t('folders.breadcrumbAria')}
    >
      <button
        type="button"
        className="flex items-center gap-1 px-1.5 py-1 rounded hover:text-foreground hover:bg-surface-sunken transition-colors flex-shrink-0"
        onClick={() => onNavigate(null)}
      >
        <Home className="w-3.5 h-3.5" />
        <span>{rootLabel ?? t('folders.root')}</span>
      </button>

      {items.map((item, idx) => (
        <div
          key={item.id ?? 'root'}
          className="flex items-center gap-1.5 flex-shrink-0"
        >
          <ChevronRight className="w-3.5 h-3.5 text-muted-foreground-tertiary" />
          <button
            type="button"
            className={cn(
              'px-1.5 py-1 rounded truncate max-w-[180px] transition-colors hover:bg-surface-sunken',
              idx === items.length - 1
                ? 'text-foreground font-medium'
                : 'hover:text-foreground',
            )}
            onClick={() => onNavigate(item.id)}
          >
            {item.name}
          </button>
        </div>
      ))}
    </nav>
  );
}
