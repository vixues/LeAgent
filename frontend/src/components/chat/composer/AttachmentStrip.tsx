import { useMemo, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X, FileText, Image as ImageIcon, File as FileIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

interface AttachmentStripProps {
  files: File[];
  onRemove: (index: number) => void;
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
 * Strip of pending attachments shown above the composer textarea.
 * Images are rendered as 56×56 thumbnails in a tight grid; other files
 * show as inline chips. Object URLs are reused (via WeakMap) and revoked
 * when a file is removed or the composer unmounts.
 */
export function AttachmentStrip({
  files,
  onRemove,
  className,
}: AttachmentStripProps) {
  const { t } = useTranslation();
  const previewCache = useRef(new WeakMap<File, string>());

  const previews = useMemo(
    () =>
      files.map((file) => {
        if (!file.type.startsWith('image/')) return null;
        let url = previewCache.current.get(file);
        if (!url) {
          url = URL.createObjectURL(file);
          previewCache.current.set(file, url);
        }
        return url;
      }),
    [files],
  );

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

  useEffect(() => {
    return () => {
      for (const file of prevFilesRef.current) {
        const url = previewCache.current.get(file);
        if (url) URL.revokeObjectURL(url);
      }
    };
  }, []);

  if (files.length === 0) return null;

  const images = files
    .map((file, idx) => ({ file, idx, preview: previews[idx] }))
    .filter((entry) => entry.preview);
  const others = files
    .map((file, idx) => ({ file, idx, preview: previews[idx] }))
    .filter((entry) => !entry.preview);

  return (
    <div className={cn('px-3 pt-3 pb-1 space-y-2', className)}>
      {images.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {images.map(({ file, idx, preview }) => (
            <div
              key={`${file.name}-${file.lastModified}-${idx}`}
              className="group/att relative w-16 h-16 rounded-lg overflow-hidden border border-border-subtle bg-surface-sunken"
              title={`${file.name} · ${formatSize(file.size)}`}
            >
              <img
                src={preview!}
                alt={file.name}
                className="w-full h-full object-cover"
              />
              <button
                type="button"
                onClick={() => onRemove(idx)}
                className="absolute top-0.5 right-0.5 w-5 h-5 rounded-full bg-foreground/80 text-background hover:bg-foreground flex items-center justify-center opacity-0 group-hover/att:opacity-100 focus-visible:opacity-100 transition-opacity"
                aria-label={t('chat.attachments.remove', {
                  defaultValue: `Remove ${file.name}`,
                  name: file.name,
                })}
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {others.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {others.map(({ file, idx }) => (
            <div
              key={`${file.name}-${file.lastModified}-${idx}`}
              className="group/att relative flex items-center gap-1.5 rounded-lg border border-border-subtle bg-surface-sunken/60 px-2 py-1 text-xs"
            >
              <span className="text-muted-foreground-tertiary flex-shrink-0">
                {getFileIcon(file.type)}
              </span>
              <span className="max-w-[160px] truncate text-muted-foreground font-medium">
                {file.name}
              </span>
              <span className="text-muted-foreground-tertiary tabular-nums">
                {formatSize(file.size)}
              </span>
              <button
                type="button"
                onClick={() => onRemove(idx)}
                className="p-0.5 rounded-full text-muted-foreground-tertiary hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                aria-label={t('chat.attachments.remove', {
                  defaultValue: `Remove ${file.name}`,
                  name: file.name,
                })}
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
