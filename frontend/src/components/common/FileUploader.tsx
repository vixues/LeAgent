import {
  forwardRef,
  useState,
  useRef,
  useCallback,
  type HTMLAttributes,
  type DragEvent,
} from 'react';
import { cn } from '@/lib/utils';
import { Upload, File, X, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { Button } from '../ui/Button';
import { Progress } from '../ui/Progress';
import { useTranslation } from 'react-i18next';

interface FileItem {
  id: string;
  file: File;
  status: 'pending' | 'uploading' | 'success' | 'error';
  progress: number;
  error?: string;
}

interface FileUploaderProps extends Omit<HTMLAttributes<HTMLDivElement>, 'onDrop'> {
  accept?: string;
  maxSize?: number;
  maxFiles?: number;
  multiple?: boolean;
  disabled?: boolean;
  onUpload?: (files: File[]) => Promise<void>;
  onRemove?: (fileId: string) => void;
  showFileList?: boolean;
  compact?: boolean;
}

const FileUploader = forwardRef<HTMLDivElement, FileUploaderProps>(
  (
    {
      className,
      accept,
      maxSize = 10 * 1024 * 1024,
      maxFiles = 10,
      multiple = true,
      disabled = false,
      onUpload,
      onRemove,
      showFileList = true,
      compact = false,
      ...props
    },
    ref
  ) => {
    const { t } = useTranslation();
    const [isDragging, setIsDragging] = useState(false);
    const [files, setFiles] = useState<FileItem[]>([]);
    const inputRef = useRef<HTMLInputElement>(null);

    const formatFileSize = (bytes: number) => {
      if (bytes < 1024) return `${bytes} B`;
      if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
      return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    };

    const validateFile = (file: File): string | null => {
      if (maxSize && file.size > maxSize) {
        return t('fileUploader.fileTooLarge', {
          size: formatFileSize(maxSize),
        });
      }
      if (accept) {
        const acceptedTypes = accept.split(',').map((t) => t.trim().toLowerCase());
        const fileType = file.type.toLowerCase();
        const fileExtension = `.${file.name.split('.').pop()?.toLowerCase()}`;
        const isAccepted = acceptedTypes.some(
          (type) =>
            type === fileType ||
            type === fileExtension ||
            (type.endsWith('/*') && fileType.startsWith(type.slice(0, -1)))
        );
        if (!isAccepted) {
          return t('fileUploader.invalidType');
        }
      }
      return null;
    };

    const processFiles = useCallback(
      async (newFiles: FileList | File[]) => {
        const fileArray = Array.from(newFiles);
        const validFiles: FileItem[] = [];
        const errors: string[] = [];

        for (const file of fileArray) {
          if (files.length + validFiles.length >= maxFiles) {
            errors.push(t('fileUploader.maxFilesExceeded'));
            break;
          }

          const error = validateFile(file);
          if (error) {
            errors.push(`${file.name}: ${error}`);
          } else {
            validFiles.push({
              id: Math.random().toString(36).substring(2, 11),
              file,
              status: 'pending',
              progress: 0,
            });
          }
        }

        if (validFiles.length > 0) {
          setFiles((prev) => [...prev, ...validFiles]);

          if (onUpload) {
            for (const fileItem of validFiles) {
              setFiles((prev) =>
                prev.map((f) =>
                  f.id === fileItem.id ? { ...f, status: 'uploading' } : f
                )
              );

              try {
                await onUpload([fileItem.file]);
                setFiles((prev) =>
                  prev.map((f) =>
                    f.id === fileItem.id ? { ...f, status: 'success', progress: 100 } : f
                  )
                );
              } catch (err) {
                const errorMessage = err instanceof Error ? err.message : t('common.fileUploader.uploadFailed');
                setFiles((prev) =>
                  prev.map((f) =>
                    f.id === fileItem.id ? { ...f, status: 'error', error: errorMessage } : f
                  )
                );
              }
            }
          }
        }
      },
      [files.length, maxFiles, onUpload, t]
    );

    const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      if (!disabled) {
        setIsDragging(true);
      }
    };

    const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(false);
    };

    const handleDrop = (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(false);

      if (!disabled && e.dataTransfer.files.length > 0) {
        processFiles(e.dataTransfer.files);
      }
    };

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files && e.target.files.length > 0) {
        processFiles(e.target.files);
        e.target.value = '';
      }
    };

    const handleRemove = (fileId: string) => {
      setFiles((prev) => prev.filter((f) => f.id !== fileId));
      onRemove?.(fileId);
    };

    const openFileDialog = () => {
      inputRef.current?.click();
    };

    return (
      <div ref={ref} className={cn('space-y-4', className)} {...props}>
        <div
          onClick={openFileDialog}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={cn(
            'relative border-2 border-dashed rounded-lg transition-colors cursor-pointer',
            'hover:border-primary-400 hover:bg-primary-50/50 dark:hover:bg-primary-900/10',
            isDragging && 'border-primary-500 bg-primary-50 dark:bg-primary-900/20',
            disabled && 'opacity-50 cursor-not-allowed',
            !isDragging && 'border-gray-300 dark:border-gray-600',
            compact ? 'p-4' : 'p-8'
          )}
        >
          <input
            ref={inputRef}
            type="file"
            accept={accept}
            multiple={multiple}
            disabled={disabled}
            onChange={handleFileSelect}
            className="hidden"
          />
          <div className="flex flex-col items-center justify-center text-center">
            <div
              className={cn(
                'rounded-full p-3 mb-3',
                'bg-gray-100 dark:bg-surface',
                'text-gray-400 dark:text-gray-500'
              )}
            >
              <Upload className={compact ? 'w-5 h-5' : 'w-8 h-8'} />
            </div>
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('fileUploader.dragOrClick')}
            </p>
            {!compact && (
              <>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                  {accept
                    ? t('fileUploader.acceptedTypes', { types: accept })
                    : t('fileUploader.allTypes')}
                </p>
                <Button type="button" variant="outline" size="sm" disabled={disabled}>
                  {t('fileUploader.selectFiles')}
                </Button>
              </>
            )}
          </div>
        </div>

        {showFileList && files.length > 0 && (
          <div className="space-y-2">
            {files.map((fileItem) => (
              <div
                key={fileItem.id}
                className={cn(
                  'flex items-center gap-3 p-3 rounded-lg',
                  'bg-gray-50 dark:bg-surface/50',
                  'border border-gray-200 dark:border-gray-700'
                )}
              >
                <div className="flex-shrink-0">
                  {fileItem.status === 'uploading' && (
                    <Loader2 className="w-5 h-5 text-primary-500 animate-spin" />
                  )}
                  {fileItem.status === 'success' && (
                    <CheckCircle className="w-5 h-5 text-green-500" />
                  )}
                  {fileItem.status === 'error' && (
                    <AlertCircle className="w-5 h-5 text-red-500" />
                  )}
                  {fileItem.status === 'pending' && (
                    <File className="w-5 h-5 text-gray-400" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-700 dark:text-gray-300 truncate">
                    {fileItem.file.name}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {formatFileSize(fileItem.file.size)}
                    {fileItem.error && (
                      <span className="text-red-500 ml-2">{fileItem.error}</span>
                    )}
                  </p>
                  {fileItem.status === 'uploading' && (
                    <Progress value={fileItem.progress} size="sm" className="mt-1" />
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => handleRemove(fileItem.id)}
                  className={cn(
                    'p-1 rounded-md',
                    'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300',
                    'hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors'
                  )}
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }
);

FileUploader.displayName = 'FileUploader';

export { FileUploader, type FileItem };
