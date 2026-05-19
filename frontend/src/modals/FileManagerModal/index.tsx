import { useState, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { BaseModal } from '../BaseModal';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { cn } from '@/lib/utils';

export interface FileItem {
  id: string;
  name: string;
  type: 'file' | 'folder';
  size?: number;
  mimeType?: string;
  createdAt: Date;
  updatedAt: Date;
}

interface FileManagerModalProps {
  isOpen: boolean;
  onClose: () => void;
  files: FileItem[];
  onUpload: (files: File[]) => Promise<void>;
  onDelete: (fileId: string) => Promise<void>;
  onSelect?: (file: FileItem) => void;
  title?: string;
  acceptedTypes?: string;
  maxSize?: number;
}

const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

const getFileIcon = (mimeType?: string): string => {
  if (!mimeType) return 'M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z';
  if (mimeType.startsWith('image/')) return 'M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z';
  if (mimeType.includes('pdf')) return 'M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z';
  if (mimeType.includes('spreadsheet') || mimeType.includes('excel')) return 'M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z';
  return 'M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z';
};

export const FileManagerModal = ({
  isOpen,
  onClose,
  files,
  onUpload,
  onDelete,
  onSelect,
  title,
  acceptedTypes = '*',
  maxSize = 10 * 1024 * 1024,
}: FileManagerModalProps) => {
  const { t } = useTranslation();
  const [searchQuery, setSearchQuery] = useState('');
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const filteredFiles = files.filter((file) =>
    file.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const handleFileSelect = useCallback(
    async (selectedFiles: FileList | null) => {
      if (!selectedFiles || selectedFiles.length === 0) return;

      const validFiles: File[] = [];
      for (const file of Array.from(selectedFiles)) {
        if (file.size > maxSize) {
          console.warn(t('modals.fileManager.warnOversized', { name: file.name }));
          continue;
        }
        validFiles.push(file);
      }

      if (validFiles.length === 0) return;

      setUploading(true);
      try {
        await onUpload(validFiles);
      } finally {
        setUploading(false);
      }
    },
    [maxSize, onUpload, t]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      handleFileSelect(e.dataTransfer.files);
    },
    [handleFileSelect]
  );

  const handleDelete = async (fileId: string) => {
    if (deleteConfirm !== fileId) {
      setDeleteConfirm(fileId);
      setTimeout(() => setDeleteConfirm(null), 3000);
      return;
    }

    setDeleting(fileId);
    try {
      await onDelete(fileId);
    } finally {
      setDeleting(null);
      setDeleteConfirm(null);
    }
  };

  return (
    <BaseModal
      isOpen={isOpen}
      onClose={onClose}
      title={title || t('modals.fileManager.title')}
      size="lg"
    >
      <div className="space-y-4">
        <div className="flex gap-3">
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t('modals.fileManager.searchPlaceholder')}
            className="flex-1"
            leftIcon={
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            }
          />
          <Button onClick={() => fileInputRef.current?.click()} loading={uploading}>
            {t('modals.fileManager.upload')}
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept={acceptedTypes}
            multiple
            onChange={(e) => handleFileSelect(e.target.files)}
            className="hidden"
          />
        </div>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          className={cn(
            'border-2 border-dashed rounded-lg p-4 transition-colors',
            dragOver
              ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
              : 'border-border'
          )}
        >
          <div className="text-center py-4">
            <svg
              className="w-10 h-10 mx-auto mb-2 text-muted-foreground-tertiary"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
              />
            </svg>
            <p className="text-sm text-muted-foreground">
              {t('modals.fileManager.dragOrClick')}
            </p>
            <p className="text-xs text-muted-foreground-tertiary mt-1">
              {t('modals.fileManager.maxSize', { size: formatFileSize(maxSize) })}
            </p>
          </div>
        </div>

        <div className="border rounded-lg border-border overflow-hidden">
          {filteredFiles.length === 0 ? (
            <div className="py-12 text-center text-muted-foreground">
              {searchQuery ? t('modals.fileManager.noSearchResults') : t('modals.fileManager.empty')}
            </div>
          ) : (
            <div className="divide-y divide-border max-h-80 overflow-auto">
              {filteredFiles.map((file) => (
                <div
                  key={file.id}
                  className={cn(
                    'flex items-center gap-4 p-3 hover:bg-surface-sunken transition-colors',
                    onSelect && 'cursor-pointer'
                  )}
                  onClick={() => onSelect?.(file)}
                >
                  <div className="w-10 h-10 rounded-lg bg-surface-sunken flex items-center justify-center text-muted-foreground">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d={getFileIcon(file.mimeType)} />
                    </svg>
                  </div>

                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-foreground truncate">
                      {file.name}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {file.size && formatFileSize(file.size)} •{' '}
                      {new Date(file.updatedAt).toLocaleDateString()}
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(file.id);
                      }}
                      loading={deleting === file.id}
                      className={cn(
                        deleteConfirm === file.id
                          ? 'text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20'
                          : 'text-muted-foreground-tertiary hover:text-foreground'
                      )}
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="text-sm text-muted-foreground">
          {t('modals.fileManager.fileCount', { count: files.length })}
        </div>
      </div>
    </BaseModal>
  );
};

export default FileManagerModal;
