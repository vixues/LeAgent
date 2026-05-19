import { Camera, ChevronDown, ChevronUp, FileDown, Maximize2, Video } from 'lucide-react';
import { cn } from '@/lib/utils';

export function GenUiInlineToolbar({
  showEnlarge = true,
  showExpandToggle = true,
  onEnlarge,
  onExportPdf,
  pdfExporting,
  onScreenshot,
  screenshotting,
  onCameraOpen,
  expanded = false,
  onToggleExpanded = () => {},
  expandAriaLabel,
}: {
  showEnlarge?: boolean;
  /** Inline card: show expand/chevron. Floating modal: false — shell is already full-height. */
  showExpandToggle?: boolean;
  onEnlarge?: () => void;
  onExportPdf: () => void;
  pdfExporting: boolean;
  onScreenshot: () => void;
  screenshotting: boolean;
  onCameraOpen: () => void;
  expanded?: boolean;
  onToggleExpanded?: () => void;
  expandAriaLabel?: string;
}) {
  return (
    <div className="flex items-center gap-0.5">
      {showEnlarge && onEnlarge ? (
        <button
          type="button"
          onClick={onEnlarge}
          className="p-0.5 rounded text-muted-foreground hover:text-foreground hover:bg-surface-sunken transition-colors"
          aria-label="Open enlarged floating view"
          title="Enlarge"
        >
          <Maximize2 className="w-3.5 h-3.5" />
        </button>
      ) : null}
      <button
        type="button"
        onClick={() => void onExportPdf()}
        disabled={pdfExporting}
        className={cn(
          'p-0.5 rounded text-muted-foreground hover:text-foreground hover:bg-surface-sunken transition-colors',
          pdfExporting && 'opacity-50 cursor-wait',
        )}
        aria-label="Export PDF"
        title="Export PDF"
      >
        <FileDown className="w-3.5 h-3.5" />
      </button>
      <button
        type="button"
        onClick={onScreenshot}
        disabled={screenshotting}
        className={cn(
          'p-0.5 rounded text-muted-foreground hover:text-foreground hover:bg-surface-sunken transition-colors',
          screenshotting && 'opacity-50 cursor-wait',
        )}
        aria-label="Download card screenshot"
        title="Download screenshot"
      >
        <Camera className="w-3.5 h-3.5" />
      </button>
      <button
        type="button"
        onClick={onCameraOpen}
        className="p-0.5 rounded text-muted-foreground hover:text-foreground hover:bg-surface-sunken transition-colors"
        aria-label="Take photo with camera"
        title="Camera"
      >
        <Video className="w-3.5 h-3.5" />
      </button>
      {showExpandToggle ? (
        <button
          type="button"
          onClick={onToggleExpanded}
          className="p-0.5 rounded text-muted-foreground hover:text-foreground hover:bg-surface-sunken transition-colors"
          aria-label={expandAriaLabel ?? (expanded ? 'Collapse' : 'Expand')}
        >
          {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </button>
      ) : null}
    </div>
  );
}
