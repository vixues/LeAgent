import { useTranslation } from 'react-i18next';
import {
  Camera,
  ChevronLeft,
  ChevronRight,
  Download,
  GraduationCap,
  List,
  Maximize2,
  RotateCw,
  Search,
  SquareDashedMousePointer,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { PdfReaderMode } from './types';

interface PdfToolbarProps {
  fileName: string;
  page: number;
  numPages: number;
  scale: number;
  mode: PdfReaderMode;
  sidebarOpen: boolean;
  thumbnailsOpen: boolean;
  areaMode: boolean;
  searchOpen: boolean;
  /** Hide the inline outline toggle when the sidebar lives in its own panel. */
  showSidebarToggle?: boolean;
  /** Hide the research-mode toggle when mode is owned externally. */
  showModeToggle?: boolean;
  onPageChange: (page: number) => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFitWidth: () => void;
  onRotate: () => void;
  onToggleSidebar: () => void;
  onToggleThumbnails: () => void;
  onToggleArea: () => void;
  onToggleSearch: () => void;
  onScreenshot: () => void;
  onToggleMode: () => void;
  onDownload: () => void;
  onClose: () => void;
}

export function PdfToolbar({
  fileName,
  page,
  numPages,
  scale,
  mode,
  sidebarOpen,
  thumbnailsOpen,
  areaMode,
  searchOpen,
  showSidebarToggle = true,
  showModeToggle = true,
  onPageChange,
  onZoomIn,
  onZoomOut,
  onFitWidth,
  onRotate,
  onToggleSidebar,
  onToggleThumbnails,
  onToggleArea,
  onToggleSearch,
  onScreenshot,
  onToggleMode,
  onDownload,
  onClose,
}: PdfToolbarProps) {
  const { t } = useTranslation();

  return (
    <div className="flex h-12 flex-shrink-0 items-center gap-1 overflow-x-auto border-b border-border bg-surface px-2 no-scrollbar">
      <ToolButton
        active={thumbnailsOpen}
        onClick={onToggleThumbnails}
        label={t('pdfReader.toolbar.thumbnails', { defaultValue: 'Thumbnails' })}
      >
        <List className="h-4 w-4" />
      </ToolButton>
      {showSidebarToggle && (
        <ToolButton
          active={sidebarOpen}
          onClick={onToggleSidebar}
          label={t('pdfReader.toolbar.outline', { defaultValue: 'Outline' })}
        >
          <GraduationCap className="h-4 w-4" />
        </ToolButton>
      )}

      <Divider />

      <ToolButton
        onClick={() => onPageChange(page - 1)}
        disabled={page <= 1}
        label={t('pdfReader.toolbar.prevPage', { defaultValue: 'Previous page' })}
      >
        <ChevronLeft className="h-4 w-4" />
      </ToolButton>
      <div className="flex flex-shrink-0 items-center gap-1 text-xs text-muted-foreground">
        <input
          type="number"
          value={page}
          min={1}
          max={numPages || 1}
          onChange={(e) => {
            const v = Number(e.target.value);
            if (!Number.isNaN(v)) onPageChange(v);
          }}
          className="h-7 w-12 rounded border border-border bg-background px-1 text-center text-xs text-foreground tabular-nums"
        />
        <span className="tabular-nums">/ {numPages || '–'}</span>
      </div>
      <ToolButton
        onClick={() => onPageChange(page + 1)}
        disabled={numPages > 0 && page >= numPages}
        label={t('pdfReader.toolbar.nextPage', { defaultValue: 'Next page' })}
      >
        <ChevronRight className="h-4 w-4" />
      </ToolButton>

      <Divider />

      <ToolButton
        onClick={onZoomOut}
        label={t('pdfReader.toolbar.zoomOut', { defaultValue: 'Zoom out' })}
      >
        <ZoomOut className="h-4 w-4" />
      </ToolButton>
      <span className="min-w-[3.2ch] flex-shrink-0 text-center text-xs tabular-nums text-muted-foreground">
        {Math.round(scale * 100)}%
      </span>
      <ToolButton
        onClick={onZoomIn}
        label={t('pdfReader.toolbar.zoomIn', { defaultValue: 'Zoom in' })}
      >
        <ZoomIn className="h-4 w-4" />
      </ToolButton>
      <ToolButton
        onClick={onFitWidth}
        label={t('pdfReader.toolbar.fitWidth', { defaultValue: 'Fit width' })}
      >
        <Maximize2 className="h-4 w-4" />
      </ToolButton>
      <ToolButton
        onClick={onRotate}
        label={t('pdfReader.toolbar.rotate', { defaultValue: 'Rotate' })}
      >
        <RotateCw className="h-4 w-4" />
      </ToolButton>

      <Divider />

      <ToolButton
        active={searchOpen}
        onClick={onToggleSearch}
        label={t('pdfReader.toolbar.search', { defaultValue: 'Search' })}
      >
        <Search className="h-4 w-4" />
      </ToolButton>
      <ToolButton
        active={areaMode}
        onClick={onToggleArea}
        label={t('pdfReader.toolbar.areaSelect', { defaultValue: 'Area select' })}
      >
        <SquareDashedMousePointer className="h-4 w-4" />
      </ToolButton>
      <ToolButton
        onClick={onScreenshot}
        label={t('pdfReader.toolbar.screenshot', { defaultValue: 'Screenshot' })}
      >
        <Camera className="h-4 w-4" />
      </ToolButton>

      <div className="mx-2 min-w-[2rem] flex-1 truncate text-center text-xs font-medium text-foreground">
        {fileName}
      </div>

      {showModeToggle && (
        <button
          type="button"
          onClick={onToggleMode}
          className={cn(
            'flex flex-shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors',
            mode === 'research'
              ? 'bg-primary-600 text-white hover:bg-primary-700'
              : 'bg-surface-sunken text-foreground hover:bg-surface-sunken/70',
          )}
        >
          <GraduationCap className="h-3.5 w-3.5" />
          {mode === 'research'
            ? t('pdfReader.toolbar.researchOn', { defaultValue: 'Research Mode' })
            : t('pdfReader.toolbar.researchOff', { defaultValue: 'Research Mode' })}
        </button>
      )}

      <Divider />

      <ToolButton
        onClick={onDownload}
        label={t('pdfReader.toolbar.download', { defaultValue: 'Download' })}
      >
        <Download className="h-4 w-4" />
      </ToolButton>
      <ToolButton
        onClick={onClose}
        label={t('common.close', { defaultValue: 'Close' })}
      >
        <X className="h-4 w-4" />
      </ToolButton>
    </div>
  );
}

function ToolButton({
  children,
  onClick,
  label,
  active,
  disabled,
}: {
  children: React.ReactNode;
  onClick: () => void;
  label: string;
  active?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      className={cn(
        'flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg transition-colors',
        'text-muted-foreground hover:bg-surface-sunken hover:text-foreground',
        active && 'bg-primary-50 text-primary-600 dark:bg-primary-900/20 dark:text-primary-400',
        disabled && 'cursor-not-allowed opacity-40 hover:bg-transparent hover:text-muted-foreground',
      )}
    >
      {children}
    </button>
  );
}

function Divider() {
  return <div className="mx-1 h-5 w-px flex-shrink-0 bg-border" />;
}
