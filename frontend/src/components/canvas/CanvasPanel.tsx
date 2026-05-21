import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toPng } from 'html-to-image';
import {
  AlertCircle,
  Camera,
  ExternalLink,
  Maximize2,
  Minimize2,
  RefreshCw,
  Video,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Artifact } from '@/types/artifact';
import { useGenUiStore, genUiTreeKey } from '@/stores/genUi';
import { useChatStore } from '@/stores/chat';
import {
  pickCanvasPreviewPathFromMetadata,
  resolveCanvasPreviewUrl,
} from '@/lib/previewUrl';
import {
  downloadImageBlob,
  extractCanvasPreviewToken,
  fetchCanvasPreviewScreenshot,
  refreshCanvasPreviewToken,
} from '@/lib/canvasScreenshot';
import {
  deckScreenshotDimensions,
  documentScreenshotDimensions,
} from '@/components/canvas/genUi/genUiExportDimensions';
import {
  expandScrollContainersForCapture,
  flushLayout,
  nextDoubleFrame,
} from '@/components/canvas/genUi/genUiCaptureDom';
import { useToast } from '@/components/ui/Toaster';
import { GenUiTreeView } from './GenUiRegistry';
import { CameraCaptureModal } from '@/components/chat/CameraCaptureModal';

const SandboxedPreview = lazy(() => import('../workspace/SandboxedPreview'));

type CanvasTab = 'preview' | 'genui';

interface CanvasPanelProps {
  artifact: Artifact;
  className?: string;
}

function CanvasMissingHostedPreview() {
  return (
    <div className="flex flex-1 min-h-0 flex-col items-center justify-center gap-3 px-6 text-center">
      <AlertCircle
        className="h-9 w-9 text-muted-foreground-tertiary shrink-0"
        aria-hidden
      />
      <div className="space-y-1 max-w-sm">
        <p className="text-sm font-medium text-foreground">No preview URL for this canvas</p>
        <p className="text-xs text-muted-foreground leading-relaxed">
          This artifact has no hosted preview link (for example after restoring from storage with an
          older shape). Publish the canvas again from chat, or refresh the page.
        </p>
      </div>
    </div>
  );
}

function CanvasPanel({ artifact, className }: CanvasPanelProps) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const [tab, setTab] = useState<CanvasTab>('preview');
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [iframeKey, setIframeKey] = useState(0);
  const [screenshotting, setScreenshotting] = useState(false);
  const [previewFrameError, setPreviewFrameError] = useState(false);
  const [cameraOpen, setCameraOpen] = useState(false);
  const genuiBodyRef = useRef<HTMLDivElement>(null);
  const currentSessionId = useChatStore((s) => s.currentSessionId);
  const sessionId = artifact.sessionId || currentSessionId || '';
  const messageId = artifact.messageId || '';
  const treeKey = sessionId && messageId ? genUiTreeKey(sessionId, messageId) : '';
  const tree = useGenUiStore((s) => (treeKey ? s.trees[treeKey] : null));
  const meta = artifact.metadata as Record<string, unknown> | undefined;
  const resolvedPreviewPath = useMemo(
    () => pickCanvasPreviewPathFromMetadata(meta),
    [meta],
  );
  const hostedSrc = resolvedPreviewPath
    ? resolveCanvasPreviewUrl(resolvedPreviewPath)
    : '';
  const showGenTab = Boolean(tree);
  const effectiveTab: CanvasTab = showGenTab ? tab : 'preview';

  const isApiCanvasPreview =
    Boolean(hostedSrc) &&
    (hostedSrc.includes('/canvas/preview') || hostedSrc.includes('canvas%2Fpreview'));
  const iframeSandbox =
    isApiCanvasPreview || ((meta?.trust as string) === 'hosted' && hostedSrc)
      ? 'allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox'
      : 'allow-scripts';

  useEffect(() => {
    setPreviewFrameError(false);
  }, [hostedSrc, iframeKey]);

  const handleRefresh = useCallback(() => {
    setPreviewFrameError(false);
    setIframeKey((k) => k + 1);
  }, []);

  const handleOpenExternal = useCallback(() => {
    if (hostedSrc) {
      window.open(hostedSrc, '_blank');
    }
  }, [hostedSrc]);

  const captureGenUiScreenshot = useCallback(async () => {
    const el = genuiBodyRef.current;
    if (!el || screenshotting) return;
    const isDeck = tree?.root?.kind === 'SlideDeck';
    setScreenshotting(true);
    const restoreDom = expandScrollContainersForCapture(el);
    try {
      flushLayout(el);
      await nextDoubleFrame();
      let bg = window.getComputedStyle(el).backgroundColor;
      if (!bg || bg === 'rgba(0, 0, 0, 0)' || bg === 'transparent') {
        bg = window.getComputedStyle(document.documentElement).backgroundColor;
      }
      const bgOpt =
        bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent' ? bg : undefined;
      const dims = isDeck ? deckScreenshotDimensions(el) : documentScreenshotDimensions(el);
      const dataUrl = await toPng(el, {
        pixelRatio: 2,
        cacheBust: true,
        backgroundColor: bgOpt,
        width: dims.width,
        height: dims.height,
      });
      const res = await fetch(dataUrl);
      const blob = await res.blob();
      downloadImageBlob(blob, `${artifact.title || 'genui'}.png`);
      toast({
        variant: 'success',
        title: t('chat.canvas.screenshotSaved', { defaultValue: 'Screenshot saved' }),
      });
    } catch {
      toast({
        variant: 'error',
        title: t('chat.canvas.screenshotFailed', {
          defaultValue: 'Could not capture screenshot',
        }),
      });
    } finally {
      restoreDom();
      setScreenshotting(false);
    }
  }, [artifact.title, screenshotting, t, toast, tree?.root?.kind]);

  const handleScreenshot = useCallback(async () => {
    if (screenshotting) return;

    if (showGenTab && effectiveTab === 'genui') {
      await captureGenUiScreenshot();
      return;
    }

    if (!resolvedPreviewPath || !hostedSrc) {
      toast({
        variant: 'error',
        title: t('chat.canvas.screenshotUnavailable', {
          defaultValue: 'Screenshot is not available for this canvas',
        }),
      });
      return;
    }

    setScreenshotting(true);
    try {
      const canvasIdRaw = meta?.canvasId ?? meta?.canvas_id;
      const canvasId = typeof canvasIdRaw === 'string' ? canvasIdRaw : '';
      let token =
        extractCanvasPreviewToken(hostedSrc) ??
        extractCanvasPreviewToken(resolvedPreviewPath);
      if (!token && sessionId && canvasId) {
        token = await refreshCanvasPreviewToken(sessionId, canvasId);
      }
      if (!token) {
        toast({
          variant: 'error',
          title: t('chat.canvas.screenshotNoToken', {
            defaultValue: 'Preview link expired — refresh the canvas or open it again from chat',
          }),
        });
        return;
      }
      const blob = await fetchCanvasPreviewScreenshot(token);
      downloadImageBlob(blob, `${artifact.title || 'canvas'}.png`);
      toast({
        variant: 'success',
        title: t('chat.canvas.screenshotSaved', { defaultValue: 'Screenshot saved' }),
      });
    } catch (err) {
      const detail = err instanceof Error ? err.message : '';
      toast({
        variant: 'error',
        title: t('chat.canvas.screenshotFailed', {
          defaultValue: 'Could not capture screenshot',
        }),
        description: detail || undefined,
      });
    } finally {
      setScreenshotting(false);
    }
  }, [
    captureGenUiScreenshot,
    effectiveTab,
    hostedSrc,
    meta,
    resolvedPreviewPath,
    screenshotting,
    sessionId,
    showGenTab,
    artifact.title,
    t,
    toast,
  ]);

  const handleToggleFullscreen = useCallback(() => setIsFullscreen((f) => !f), []);

  const isHostedHtmlCanvas =
    artifact.type === 'html' && !(artifact.content && artifact.content.trim());

  if (hostedSrc) {
    return (
      <div
        className={cn(
          'flex min-h-0 min-w-0 flex-1 basis-0 flex-col',
          isFullscreen && 'fixed inset-0 z-50 bg-background',
          className,
        )}
      >
        {/* Toolbar */}
        <div className="flex items-center gap-1 px-3 py-1.5 border-b border-border flex-shrink-0 bg-surface">
          {/* Tabs */}
          <div className="flex items-center gap-0.5 bg-surface-sunken rounded-lg p-0.5 mr-2">
            <button
              type="button"
              onClick={() => setTab('preview')}
              className={cn(
                'px-2.5 py-1 text-[11px] font-medium rounded-md transition-colors',
                effectiveTab === 'preview'
                  ? 'bg-surface shadow-sm text-foreground'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              Preview
            </button>
            {showGenTab && (
              <button
                type="button"
                onClick={() => setTab('genui')}
                className={cn(
                  'px-2.5 py-1 text-[11px] font-medium rounded-md transition-colors',
                  effectiveTab === 'genui'
                    ? 'bg-surface shadow-sm text-foreground'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                UI Tree
              </button>
            )}
          </div>

          <span className="text-[11px] font-medium text-muted-foreground truncate flex-1">
            {artifact.title || 'Canvas'}
          </span>

          {/* Action buttons */}
          <button
            type="button"
            onClick={handleRefresh}
            className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-surface-sunken transition-colors"
            aria-label="Refresh preview"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={handleScreenshot}
            disabled={screenshotting}
            className={cn(
              'p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-surface-sunken transition-colors',
              screenshotting && 'opacity-50 cursor-wait',
            )}
            aria-label="Download screenshot"
            title="Download screenshot"
          >
            <Camera className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={() => setCameraOpen(true)}
            className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-surface-sunken transition-colors"
            aria-label="Take photo with camera"
            title="Camera"
          >
            <Video className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={handleOpenExternal}
            className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-surface-sunken transition-colors"
            aria-label="Open in new window"
          >
            <ExternalLink className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={handleToggleFullscreen}
            className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-surface-sunken transition-colors"
            aria-label={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
          >
            {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </button>
        </div>

        {/* Preview fills panel height; Gen UI tab scrolls internally */}
        <div className="flex min-h-0 flex-1 basis-0 flex-col overflow-hidden">
          {(!showGenTab || effectiveTab === 'preview') && (
            <div className="flex min-h-0 min-w-0 flex-1 basis-0 flex-col overflow-hidden">
              {previewFrameError && (
                <div className="flex-shrink-0 px-3 py-2 text-xs text-amber-800 dark:text-amber-200 bg-amber-50 dark:bg-amber-950/40 border-b border-amber-200/60 dark:border-amber-800/50">
                  The preview frame reported a load error. Try Refresh, Open in new window, or
                  check that the API proxy can reach the canvas service.
                </div>
              )}
              <div className="relative flex min-h-0 min-w-0 flex-1 basis-0 flex-col bg-white dark:bg-zinc-950">
                <iframe
                  key={`${hostedSrc}-${iframeKey}`}
                  title={artifact.title}
                  src={hostedSrc}
                  className="min-h-0 w-full min-w-0 flex-1 border-0"
                  sandbox={iframeSandbox}
                  referrerPolicy="no-referrer"
                  onLoad={() => setPreviewFrameError(false)}
                  onError={() => setPreviewFrameError(true)}
                />
              </div>
            </div>
          )}
          {showGenTab && effectiveTab === 'genui' && (
            <div className="min-h-0 flex-1 overflow-auto bg-surface scrollbar-gutter-stable">
              <GenUiTreeView
                tree={tree}
                contentRef={genuiBodyRef}
                sessionId={sessionId}
                messageId={messageId || undefined}
              />
            </div>
          )}
        </div>
        <CameraCaptureModal open={cameraOpen} onOpenChange={setCameraOpen} />
      </div>
    );
  }

  if (isHostedHtmlCanvas) {
    return (
      <div className={cn('flex min-h-0 min-w-0 flex-1 flex-col', className)}>
        <CanvasMissingHostedPreview />
      </div>
    );
  }

  return (
    <div className={cn('flex min-h-0 min-w-0 flex-1 flex-col', className)}>
      <Suspense
        fallback={
          <div className="flex min-h-0 flex-1 items-center justify-center">
            <div className="w-5 h-5 border-2 border-primary-400 border-t-transparent rounded-full animate-spin" />
          </div>
        }
      >
        <SandboxedPreview artifact={artifact} className="min-h-0 flex-1" />
      </Suspense>
    </div>
  );
}

export default CanvasPanel;
