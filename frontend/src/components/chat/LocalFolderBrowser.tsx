import { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Folder,
  FileText,
  ChevronRight,
  Home,
  Monitor,
  FileDown,
  FolderOpen,
  ArrowUp,
  Loader2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  useBrowseDirectories,
  type BrowseDirEntry,
} from '@/hooks/useChat';

interface LocalFolderBrowserProps {
  onSelect: (path: string) => void;
}

const QUICK_ACCESS_ICONS: Record<string, typeof Home> = {
  Home: Home,
  Desktop: Monitor,
  Documents: FileText,
  Downloads: FileDown,
};

export function LocalFolderBrowser({ onSelect }: LocalFolderBrowserProps) {
  const { t } = useTranslation();
  const [browsePath, setBrowsePath] = useState<string | null>(null);
  const { data, isLoading, isFetching, isError, isPlaceholderData } =
    useBrowseDirectories(browsePath);
  const showStaleOverlay = isFetching && isPlaceholderData;

  const handleEntryClick = useCallback(
    (entry: BrowseDirEntry) => {
      if (entry.is_dir) {
        setBrowsePath(entry.path);
      }
    },
    [],
  );

  const handleSelectCurrent = useCallback(() => {
    if (data?.path) {
      onSelect(data.path);
    }
  }, [data?.path, onSelect]);

  const handleGoUp = useCallback(() => {
    if (data?.parent) {
      setBrowsePath(data.parent);
    }
  }, [data?.parent]);

  const quickAccess = data?.quick_access ?? [];
  const entries = data?.entries ?? [];
  const dirs = entries.filter((e) => e.is_dir);
  const files = entries.filter((e) => !e.is_dir);

  const breadcrumbParts = data?.path
    ? data.path.split('/').filter(Boolean)
    : [];

  return (
    <div className="rounded-xl border border-border bg-surface-sunken overflow-hidden">
      {/* Quick access bar */}
      {quickAccess.length > 0 && (
        <div className="flex items-center gap-1 px-3 py-2 border-b border-border bg-surface overflow-x-auto no-scrollbar">
          {quickAccess.map((qa) => {
            const Icon = QUICK_ACCESS_ICONS[qa.name] ?? Folder;
            const isActive = data?.path === qa.path;
            return (
              <button
                key={qa.path}
                type="button"
                onClick={() => setBrowsePath(qa.path)}
                className={cn(
                  'flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium whitespace-nowrap transition-colors',
                  isActive
                    ? 'bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300'
                    : 'text-muted-foreground hover:text-foreground hover:bg-surface-sunken',
                )}
              >
                <Icon className="w-3.5 h-3.5 flex-shrink-0" />
                {qa.name}
              </button>
            );
          })}
        </div>
      )}

      {/* Breadcrumb + current path */}
      {data?.path && (
        <div className="flex items-center gap-1 px-3 py-2 border-b border-border">
          {data.parent && (
            <button
              type="button"
              onClick={handleGoUp}
              className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-surface transition-colors flex-shrink-0"
              title={t('chat.authorizedFolders.browser.goUp', {
                defaultValue: 'Go up',
              })}
            >
              <ArrowUp className="w-3.5 h-3.5" />
            </button>
          )}
          <div className="flex items-center gap-0.5 min-w-0 overflow-x-auto no-scrollbar text-xs text-muted-foreground">
            <span className="text-muted-foreground-tertiary">/</span>
            {breadcrumbParts.map((part, i) => {
              const segmentPath = '/' + breadcrumbParts.slice(0, i + 1).join('/');
              const isLast = i === breadcrumbParts.length - 1;
              return (
                <span key={segmentPath} className="flex items-center gap-0.5 whitespace-nowrap">
                  {i > 0 && <ChevronRight className="w-3 h-3 text-muted-foreground-tertiary flex-shrink-0" />}
                  <button
                    type="button"
                    onClick={() => setBrowsePath(segmentPath)}
                    className={cn(
                      'hover:text-foreground transition-colors',
                      isLast ? 'font-medium text-foreground' : '',
                    )}
                  >
                    {part}
                  </button>
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* File list — fixed height to prevent modal resize */}
      <div className="relative h-56 overflow-y-auto">
        {isLoading && !isPlaceholderData && (
          <div className="absolute inset-0 flex items-center justify-center text-muted-foreground">
            <Loader2 className="w-4 h-4 animate-spin" />
          </div>
        )}

        {isError && (
          <div className="absolute inset-0 flex items-center justify-center px-3 text-sm text-muted-foreground">
            {t('chat.authorizedFolders.browser.error', {
              defaultValue: 'Could not read this directory.',
            })}
          </div>
        )}

        {!isError && dirs.length === 0 && files.length === 0 && !isLoading && (
          <div className="absolute inset-0 flex items-center justify-center px-3 text-xs text-muted-foreground-tertiary">
            {t('chat.authorizedFolders.browser.empty', {
              defaultValue: 'This folder is empty.',
            })}
          </div>
        )}

        {!isError && (dirs.length > 0 || files.length > 0) && (
          <div className={cn('transition-opacity duration-150', showStaleOverlay && 'opacity-60')}>
            {dirs.map((entry) => (
              <button
                key={entry.path}
                type="button"
                onClick={() => handleEntryClick(entry)}
                className="w-full flex items-center gap-2.5 px-3 py-1.5 text-left text-sm hover:bg-surface transition-colors group"
              >
                <Folder className="w-4 h-4 text-primary-500 flex-shrink-0" />
                <span className="truncate text-foreground">{entry.name}</span>
                <ChevronRight className="w-3 h-3 ml-auto text-muted-foreground-tertiary opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
              </button>
            ))}
            {files.map((entry) => (
              <div
                key={entry.path}
                className="w-full flex items-center gap-2.5 px-3 py-1.5 text-sm text-muted-foreground"
              >
                <FileText className="w-4 h-4 text-muted-foreground-tertiary flex-shrink-0" />
                <span className="truncate">{entry.name}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Select-current-folder bar */}
      {data?.path && (
        <div className="flex items-center justify-between gap-2 px-3 py-2 border-t border-border bg-surface">
          <div className="flex items-center gap-2 min-w-0">
            <FolderOpen className="w-4 h-4 text-primary-500 flex-shrink-0" />
            <span className="text-xs text-foreground font-medium truncate">
              {data.path.split('/').filter(Boolean).pop() ?? data.path}
            </span>
          </div>
          <button
            type="button"
            onClick={handleSelectCurrent}
            className="flex-shrink-0 px-3 py-1 rounded-lg text-xs font-medium bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400 hover:bg-primary-100 dark:hover:bg-primary-900/40 transition-colors"
          >
            {t('chat.authorizedFolders.browser.selectThis', {
              defaultValue: 'Select this folder',
            })}
          </button>
        </div>
      )}
    </div>
  );
}
