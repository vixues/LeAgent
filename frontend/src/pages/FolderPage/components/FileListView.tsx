import { useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import {
  FileText,
  FileSpreadsheet,
  FileImage,
  FileArchive,
  FileCode,
  File,
  LayoutGrid,
  List,
  Upload,
  Trash2,
  ArrowUpDown,
  Eye,
  Search,
} from 'lucide-react';
import { Button, Input } from '@/components/ui';
import { PageLoader } from '@/components/common/PageLoader';
import type { FolderFileItem } from '@/hooks/useFolders';

interface FileListViewProps {
  files: FolderFileItem[];
  isLoading: boolean;
  onPreview: (file: FolderFileItem) => void;
  onRemove: (fileId: string) => void;
  onUpload: (files: FileList) => void;
}

type SortKey = 'file_name' | 'file_type' | 'size';
type ViewMode = 'grid' | 'list';

const FILE_TYPE_ICONS: Record<string, typeof FileText> = {
  document: FileText,
  data: FileSpreadsheet,
  image: FileImage,
  archive: FileArchive,
  code: FileCode,
};

function getFileIcon(fileType: string) {
  return FILE_TYPE_ICONS[fileType] || File;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

export default function FileListView({
  files,
  isLoading,
  onPreview,
  onRemove,
  onUpload,
}: FileListViewProps) {
  const { t } = useTranslation();
  const [viewMode, setViewMode] = useState<ViewMode>('list');
  const [sortKey, setSortKey] = useState<SortKey>('file_name');
  const [sortAsc, setSortAsc] = useState(true);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [dragOver, setDragOver] = useState(false);
  const [query, setQuery] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const sorted = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = q
      ? files.filter((f) => f.file_name.toLowerCase().includes(q))
      : files;
    return [...filtered].sort((a, b) => {
      const dir = sortAsc ? 1 : -1;
      if (sortKey === 'size') return (a.size - b.size) * dir;
      const va = a[sortKey] ?? '';
      const vb = b[sortKey] ?? '';
      return va.localeCompare(vb) * dir;
    });
  }, [files, query, sortKey, sortAsc]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc(!sortAsc);
    else {
      setSortKey(key);
      setSortAsc(true);
    }
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files.length) onUpload(e.dataTransfer.files);
  };

  return (
    <div
      className={cn(
        'flex flex-col flex-1 min-h-0 transition-colors',
        dragOver && 'bg-primary-50/60 dark:bg-primary-900/10'
      )}
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
    >
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3 px-4 sm:px-5 py-3 border-b border-border">
        <div className="min-w-[180px] flex-1 max-w-sm">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('folders.searchFilesPlaceholder')}
            leftIcon={<Search className="w-4 h-4" />}
          />
        </div>

        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span className="tabular-nums">
            {t('folders.fileList.filesCount', { count: sorted.length })}
          </span>
          {selectedIds.size > 0 && (
            <span className="text-xs text-primary-600 dark:text-primary-400">
              ({t('folders.fileList.selectedCount', { count: selectedIds.size })})
            </span>
          )}
        </div>

        <div className="ml-auto flex items-center gap-2">
          {/* View toggle (rounded-lg matches the rest of the toolbar buttons) */}
          <div className="flex items-center rounded-lg border border-border bg-surface overflow-hidden">
            <button
              type="button"
              className={cn(
                'p-1.5 transition-colors',
                viewMode === 'list'
                  ? 'bg-surface-sunken text-foreground'
                  : 'text-muted-foreground hover:text-foreground hover:bg-surface-sunken'
              )}
              onClick={() => setViewMode('list')}
              aria-label={t('folders.listViewAria')}
              aria-pressed={viewMode === 'list'}
            >
              <List className="w-4 h-4" />
            </button>
            <button
              type="button"
              className={cn(
                'p-1.5 transition-colors',
                viewMode === 'grid'
                  ? 'bg-surface-sunken text-foreground'
                  : 'text-muted-foreground hover:text-foreground hover:bg-surface-sunken'
              )}
              onClick={() => setViewMode('grid')}
              aria-label={t('folders.gridViewAria')}
              aria-pressed={viewMode === 'grid'}
            >
              <LayoutGrid className="w-4 h-4" />
            </button>
          </div>

          <Button
            variant="secondary"
            size="sm"
            onClick={() => fileInputRef.current?.click()}
            leftIcon={<Upload className="w-4 h-4" />}
          >
            {t('folders.fileList.upload')}
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => e.target.files && onUpload(e.target.files)}
          />
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <PageLoader size="sm" message={t('folders.fileList.loading')} />
          </div>
        ) : sorted.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 px-4 text-center text-muted-foreground">
            <div className="w-14 h-14 rounded-2xl bg-surface-sunken flex items-center justify-center mb-3">
              <Upload className="w-6 h-6 text-muted-foreground-tertiary" />
            </div>
            <p className="text-sm font-medium text-foreground">
              {query ? t('folders.fileList.emptyNoMatch') : t('folders.fileList.emptyFolder')}
            </p>
            <p className="text-xs mt-1 text-muted-foreground-tertiary">
              {t('folders.fileList.emptyHint')}
            </p>
          </div>
        ) : viewMode === 'list' ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground uppercase tracking-wider">
                <th className="px-4 py-2 w-8">
                  <input
                    type="checkbox"
                    className="rounded border-border"
                    checked={
                      selectedIds.size === sorted.length && sorted.length > 0
                    }
                    onChange={() => {
                      if (selectedIds.size === sorted.length)
                        setSelectedIds(new Set());
                      else setSelectedIds(new Set(sorted.map((f) => f.file_id)));
                    }}
                    aria-label={t('folders.selectAllAria')}
                  />
                </th>
                <th
                  className="px-2 py-2 cursor-pointer hover:text-foreground"
                  onClick={() => toggleSort('file_name')}
                >
                  <span className="inline-flex items-center gap-1">
                    {t('folders.fileList.columnName')} <ArrowUpDown className="w-3 h-3" />
                  </span>
                </th>
                <th
                  className="px-2 py-2 cursor-pointer hover:text-foreground"
                  onClick={() => toggleSort('file_type')}
                >
                  {t('folders.fileList.columnType')}
                </th>
                <th
                  className="px-2 py-2 cursor-pointer hover:text-foreground text-right"
                  onClick={() => toggleSort('size')}
                >
                  {t('folders.fileList.columnSize')}
                </th>
                <th className="px-2 py-2 w-24">{t('folders.fileList.columnActions')}</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((file) => {
                const Icon = getFileIcon(file.file_type);
                const isSelected = selectedIds.has(file.file_id);
                return (
                  <tr
                    key={file.file_id}
                    className={cn(
                      'border-b border-border-subtle hover:bg-surface-sunken/60 transition-colors cursor-pointer',
                      isSelected && 'bg-primary-50 dark:bg-primary-900/10'
                    )}
                    onClick={() => onPreview(file)}
                  >
                    <td className="px-4 py-2">
                      <input
                        type="checkbox"
                        className="rounded border-border"
                        checked={isSelected}
                        onChange={(e) => {
                          e.stopPropagation();
                          toggleSelect(file.file_id);
                        }}
                        onClick={(e) => e.stopPropagation()}
                        aria-label={t('folders.fileList.selectFile', { name: file.file_name })}
                      />
                    </td>
                    <td className="px-2 py-2">
                      <div className="flex items-center gap-2">
                        <Icon className="w-4 h-4 text-muted-foreground-tertiary flex-shrink-0" />
                        <span className="truncate max-w-[320px] text-foreground">
                          {file.file_name}
                        </span>
                      </div>
                    </td>
                    <td className="px-2 py-2 text-muted-foreground capitalize">
                      {file.file_type}
                    </td>
                    <td className="px-2 py-2 text-right text-muted-foreground tabular-nums">
                      {formatSize(file.size)}
                    </td>
                    <td className="px-2 py-2">
                      <div className="flex items-center gap-1">
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          onClick={(e) => {
                            e.stopPropagation();
                            onPreview(file);
                          }}
                          aria-label={t('folders.previewAria')}
                        >
                          <Eye className="w-3.5 h-3.5" />
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-muted-foreground hover:text-red-600 dark:hover:text-red-400"
                          onClick={(e) => {
                            e.stopPropagation();
                            onRemove(file.file_id);
                          }}
                          aria-label={t('folders.removeAria')}
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4 p-4 sm:p-5">
            {sorted.map((file) => {
              const Icon = getFileIcon(file.file_type);
              const isSelected = selectedIds.has(file.file_id);
              return (
                <button
                  type="button"
                  key={file.file_id}
                  className={cn(
                    // rounded-xl + proper padding to match Card rhythm.
                    'group flex flex-col items-center text-center p-4 rounded-xl border transition-colors hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500',
                    isSelected
                      ? 'border-primary-400 bg-primary-50 dark:bg-primary-900/10'
                      : 'border-border bg-surface hover:border-primary-300 dark:hover:border-primary-700'
                  )}
                  onClick={() => onPreview(file)}
                >
                  <Icon className="w-10 h-10 text-muted-foreground-tertiary mb-3" />
                  <span className="text-xs font-medium text-foreground line-clamp-2 break-all w-full">
                    {file.file_name}
                  </span>
                  <span className="text-xs text-muted-foreground-tertiary mt-1 tabular-nums">
                    {formatSize(file.size)}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
