import { useEffect, useRef } from 'react';
import { FolderPlus, Pencil, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface FolderContextMenuProps {
  x: number;
  y: number;
  folderId: string;
  onClose: () => void;
  onNewSubfolder: (parentId: string) => void;
  onRename: (folderId: string) => void;
  onDelete: (folderId: string) => void;
}

/** Simple right-click menu rendered in a portal-less fixed positioning. */
export default function FolderContextMenu({
  x,
  y,
  folderId,
  onClose,
  onNewSubfolder,
  onRename,
  onDelete,
}: FolderContextMenuProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [onClose]);

  const items = [
    {
      icon: FolderPlus,
      label: 'New subfolder',
      onClick: () => {
        onNewSubfolder(folderId);
        onClose();
      },
    },
    {
      icon: Pencil,
      label: 'Rename',
      onClick: () => {
        onRename(folderId);
        onClose();
      },
    },
    { divider: true as const },
    {
      icon: Trash2,
      label: 'Delete',
      danger: true,
      onClick: () => {
        onDelete(folderId);
        onClose();
      },
    },
  ];

  return (
    <div
      ref={ref}
      role="menu"
      className="fixed z-50 min-w-[180px] py-1 bg-surface border border-border rounded-xl shadow-lg"
      style={{ left: x, top: y }}
    >
      {items.map((item, idx) => {
        if ('divider' in item) {
          return (
            <div
              key={`div-${idx}`}
              role="separator"
              className="my-1 border-t border-border-subtle"
            />
          );
        }
        const Icon = item.icon;
        return (
          <button
            key={item.label}
            type="button"
            role="menuitem"
            className={cn(
              'flex items-center gap-2 w-full px-3 py-1.5 text-sm transition-colors',
              'focus-visible:outline-none focus-visible:bg-surface-sunken',
              item.danger
                ? 'text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20'
                : 'text-foreground hover:bg-surface-sunken'
            )}
            onClick={item.onClick}
          >
            <Icon className="w-4 h-4" />
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
