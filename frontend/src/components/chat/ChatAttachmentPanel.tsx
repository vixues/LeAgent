import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ChevronDown,
  ChevronUp,
  File as FileIcon,
  FileText,
  Image as ImageIcon,
  Paperclip,
  Trash2,
  UploadCloud,
  X,
} from 'lucide-react';
import { cn } from '@/lib/utils';

interface ChatAttachmentPanelProps {
  files: File[];
  onRemove: (index: number) => void;
  onClear: () => void;
  onAdd: (files: File[]) => void;
  className?: string;
}

function getFileIcon(type: string) {
  if (type.startsWith('image/')) return <ImageIcon className="w-3.5 h-3.5" />;
  if (type.includes('pdf') || type.includes('document'))
    return <FileText className="w-3.5 h-3.5" />;
  return <FileIcon className="w-3.5 h-3.5" />;
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Dedicated drawer rendered directly above the ChatInput composer that owns
 * the display and management of files the user has queued for upload.
 *
 * Features:
 * - Previews images via object URLs (revoked on unmount / removal).
 * - Drag-and-drop zone so users can drop files onto the panel directly.
 * - Collapsible into a one-line summary when many files are attached so the
 *   composer stays compact.
 */
export function ChatAttachmentPanel({
  files,
  onRemove,
  onClear,
  onAdd,
  className,
}: ChatAttachmentPanelProps) {
  const { t } = useTranslation();
  const [collapsed, setCollapsed] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const dragCounter = useRef(0);

  // Map each File to a stable preview URL for images. We track URLs per-File
  // via WeakMap so re-renders don't recreate URLs (and trigger flicker).
  const previewCache = useRef(new WeakMap<File, string>());
  const previews = useMemo(() => {
    return files.map((file) => {
      if (!file.type.startsWith('image/')) return null;
      let url = previewCache.current.get(file);
      if (!url) {
        url = URL.createObjectURL(file);
        previewCache.current.set(file, url);
      }
      return url;
    });
  }, [files]);

  // Revoke object URLs for files that have been removed from the list.
  const prevFilesRef = useRef<File[]>([]);
  useEffect(() => {
    const current = new Set(files);
    for (const prev of prevFilesRef.current) {
      if (!current.has(prev)) {
        const url = previewCache.current.get(prev);
        if (url) {
          URL.revokeObjectURL(url);
          previewCache.current.delete(prev);
        }
      }
    }
    prevFilesRef.current = files;
  }, [files]);

  // Revoke all URLs on unmount.
  useEffect(() => {
    return () => {
      for (const file of prevFilesRef.current) {
        const url = previewCache.current.get(file);
        if (url) URL.revokeObjectURL(url);
      }
    };
  }, []);

  if (files.length === 0) return null;

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current += 1;
    if (e.dataTransfer?.types?.includes('Files')) setIsDragging(true);
  };
  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current -= 1;
    if (dragCounter.current <= 0) {
      dragCounter.current = 0;
      setIsDragging(false);
    }
  };
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current = 0;
    setIsDragging(false);
    const dropped = Array.from(e.dataTransfer?.files ?? []);
    if (dropped.length > 0) onAdd(dropped);
  };

  return (
    <div
      className={cn(
        'mb-2 rounded-2xl border bg-surface/90 backdrop-blur-sm',
        'shadow-soft dark:shadow-black/25',
        'transition-colors duration-200',
        isDragging
          ? 'border-primary-400 bg-primary-50/40 dark:border-primary-500 dark:bg-primary-900/20'
          : 'border-border',
        className
      )}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border-subtle">
        <div className="flex items-center gap-2 min-w-0">
          <Paperclip className="w-3.5 h-3.5 text-muted-foreground" aria-hidden="true" />
          <span className="text-xs font-medium text-foreground truncate">
            {t('chat.attachments.title', {
              count: files.length,
              defaultValue_one: '{{count}} attachment',
              defaultValue_other: '{{count}} attachments',
              defaultValue: `${files.length} attachments`,
            })}
          </span>
          {isDragging && (
            <span className="flex items-center gap-1 text-xs text-primary-600 dark:text-primary-400">
              <UploadCloud className="w-3.5 h-3.5" />
              {t('chat.attachments.dropHint', { defaultValue: 'Drop to add' })}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onClear}
            className="flex items-center gap-1 px-2 py-1 rounded-md text-xs text-muted-foreground hover:text-red-600 dark:hover:text-red-400 hover:bg-surface-sunken transition-colors"
            aria-label={t('chat.attachments.clearAll', { defaultValue: 'Clear all' })}
          >
            <Trash2 className="w-3 h-3" />
            <span>{t('chat.attachments.clearAll', { defaultValue: 'Clear all' })}</span>
          </button>
          <button
            type="button"
            onClick={() => setCollapsed((c) => !c)}
            className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-surface-sunken transition-colors"
            aria-label={
              collapsed
                ? t('chat.attachments.expand', { defaultValue: 'Expand' })
                : t('chat.attachments.collapse', { defaultValue: 'Collapse' })
            }
          >
            {collapsed ? (
              <ChevronDown className="w-3.5 h-3.5" />
            ) : (
              <ChevronUp className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
      </div>

      {/* Body */}
      {!collapsed && (
        <div className="p-2 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
          {files.map((file, idx) => {
            const preview = previews[idx];
            return (
              <div
                key={`${file.name}-${file.lastModified}-${idx}`}
                className="group relative flex items-center gap-2 rounded-xl border border-border-subtle bg-surface-sunken px-2 py-2"
              >
                {preview ? (
                  <img
                    src={preview}
                    alt={file.name}
                    className="w-10 h-10 rounded-lg object-cover flex-shrink-0 border border-border-subtle"
                  />
                ) : (
                  <div className="w-10 h-10 rounded-lg bg-surface flex items-center justify-center flex-shrink-0 text-muted-foreground">
                    {getFileIcon(file.type)}
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-medium text-foreground truncate">
                    {file.name}
                  </p>
                  <p className="text-[11px] text-muted-foreground-tertiary">
                    {formatSize(file.size)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => onRemove(idx)}
                  className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 p-1 rounded-md text-muted-foreground hover:text-red-600 dark:hover:text-red-400 hover:bg-surface transition-all"
                  aria-label={t('chat.attachments.remove', {
                    defaultValue: `Remove ${file.name}`,
                    name: file.name,
                  })}
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
