import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toPng } from 'html-to-image';
import {
  AlertCircle,
  Camera,
  Code2,
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
import { canvasIframeAllow, canvasIframeSandbox, srcDocIframeSandbox, withCanvasPreviewFlags } from '@/lib/canvasPreviewJs';
import { useCanvasPreviewDoc } from '@/hooks/useCanvasPreviewDoc';
import { getCameraAccessIssue, localhostPreviewUrl, stopIframeMediaTracks } from '@/lib/cameraAccess';
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
  const [jsEnabled, setJsEnabled] = useState(true);
  const [cameraAllowed, setCameraAllowed] = useState(false);
  const [screenshotting, setScreenshotting] = useState(false);
  const [previewFrameError, setPreviewFrameError] = useState(false);
  const previewIframeRef = useRef<HTMLIFrameElement>(null);
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
  const hostedSrcBase = resolvedPreviewPath
    ? resolveCanvasPreviewUrl(resolvedPreviewPath)
    : '';
  const hostedSrc = hostedSrcBase
    ? withCanvasPreviewFlags(hostedSrcBase, { jsEnabled, cameraAllowed })
    : '';
  const showGenTab = Boolean(tree);
  const effectiveTab: CanvasTab = showGenTab ? tab : 'preview';

  const isApiCanvasPreview =
    Boolean(hostedSrc) &&
    (hostedSrc.includes('/canvas/preview') || hostedSrc.includes('canvas%2Fpreview'));
  const { srcDoc: previewDoc, isLoading: previewDocLoading, isError: previewDocError } =
    useCanvasPreviewDoc(hostedSrc, isApiCanvasPreview);
  const useSrcDocPreview = isApiCanvasPreview && Boolean(previewDoc) && !previewDocError;
  const iframeSandbox = useSrcDocPreview
    ? srcDocIframeSandbox(jsEnabled)
    : canvasIframeSandbox(
        jsEnabled,
        isApiCanvasPreview || ((meta?.trust as string) === 'hosted' && Boolean(hostedSrc)),
        cameraAllowed,
      );

  const iframeAllow = canvasIframeAllow(cameraAllowed);

  useEffect(() => {
    setPreviewFrameError(false);
  }, [hostedSrc, iframeKey, jsEnabled, cameraAllowed, previewDoc, useSrcDocPreview]);

  const reloadPreviewIframe = useCallback(() => {
    stopIframeMediaTracks(previewIframeRef.current);
    setPreviewFrameError(false);
    window.setTimeout(() => setIframeKey((k) => k + 1), 80);
  }, []);

  const handleToggleJs = useCallback(() => {
    stopIframeMediaTracks(previewIframeRef.current);
    setJsEnabled((prev) => {
      const next = !prev;
      if (!next) {
        setCameraAllowed(false);
      }
      return next;
    });
    reloadPreviewIframe();
  }, [reloadPreviewIframe]);

  const handleToggleCamera = useCallback(() => {
    if (cameraAllowed) {
      stopIframeMediaTracks(previewIframeRef.current);
      setCameraAllowed(false);
      reloadPreviewIframe();
      return;
    }

    const issue = getCameraAccessIssue();
    if (issue === 'insecure') {
      if (hostedSrcBase) {
        window.open(localhostPreviewUrl(hostedSrcBase, true), '_blank', 'noopener');
      }
      toast({
        variant: 'info',
        title: t('chat.canvas.cameraInsecureContext'),
        description: t('chat.canvas.cameraOpenedLocalhost'),
      });
      return;
    }
    if (issue === 'unsupported') {
      toast({
        variant: 'error',
        title: t('chat.camera.notSupported'),
      });
      return;
    }

    stopIframeMediaTracks(previewIframeRef.current);
    setJsEnabled(true);
    setCameraAllowed(true);
    reloadPreviewIframe();
  }, [cameraAllowed, hostedSrcBase, reloadPreviewIframe, t, toast]);

  const handleRefresh = useCallback(() => {
    reloadPreviewIframe();
  }, [reloadPreviewIframe]);

  const handleOpenExternal = useCallback(() => {
    if (hostedSrc) {
      window.open(hostedSrc, '_blank', 'noopener');
    } else if (hostedSrcBase) {
      window.open(
        withCanvasPreviewFlags(hostedSrcBase, { jsEnabled, cameraAllowed }),
        '_blank',
        'noopener',
      );
    }
  }, [cameraAllowed, hostedSrc, hostedSrcBase, jsEnabled]);

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
            onClick={handleToggleJs}
            className={cn(
              'p-1 rounded-md transition-colors',
              jsEnabled
                ? 'text-foreground bg-surface-sunken'
                : 'text-muted-foreground hover:text-foreground hover:bg-surface-sunken',
            )}
            aria-label={jsEnabled ? t('chat.canvas.jsOn') : t('chat.canvas.jsOff')}
            title={jsEnabled ? t('chat.canvas.jsOn') : t('chat.canvas.jsOff')}
            aria-pressed={jsEnabled}
          >
            <Code2 className="w-3.5 h-3.5" aria-hidden />
          </button>
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
            onClick={handleToggleCamera}
            className={cn(
              'p-1 rounded-md transition-colors',
              cameraAllowed
                ? 'text-foreground bg-surface-sunken'
                : 'text-muted-foreground hover:text-foreground hover:bg-surface-sunken',
            )}
            aria-label={
              cameraAllowed
                ? t('chat.canvas.cameraAllowOn')
                : t('chat.canvas.cameraAllowOff')
            }
            title={
              cameraAllowed
                ? t('chat.canvas.cameraAllowOn')
                : t('chat.canvas.cameraAllowOff')
            }
            aria-pressed={cameraAllowed}
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
              {previewDocError && !previewDocLoading && (
                <div className="flex-shrink-0 px-3 py-2 text-xs text-amber-800 dark:text-amber-200 bg-amber-50 dark:bg-amber-950/40 border-b border-amber-200/60 dark:border-amber-800/50">
                  Could not load preview HTML. Use Open in new window or Refresh.
                </div>
              )}
              <div className="relative flex min-h-[min(60vh,640px)] min-w-0 flex-1 basis-0 flex-col bg-white dark:bg-zinc-950">
                {previewDocLoading && isApiCanvasPreview && !previewDoc ? (
                  <div className="absolute inset-0 flex items-center justify-center text-xs text-muted-foreground">
                    {t('chat.media.loading', { defaultValue: 'Loading…' })}
                  </div>
                ) : null}
                <iframe
                  ref={previewIframeRef}
                  key={`${hostedSrc}-${iframeKey}-${jsEnabled ? 'js' : 'nojs'}-${cameraAllowed ? 'cam' : 'nocam'}-${useSrcDocPreview ? 'doc' : 'url'}`}
                  title={artifact.title}
                  src={useSrcDocPreview ? undefined : hostedSrc}
                  srcDoc={useSrcDocPreview ? previewDoc ?? undefined : undefined}
                  className="absolute inset-0 h-full w-full min-h-0 border-0"
                  sandbox={iframeSandbox || undefined}
                  allow={iframeAllow}
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
                jsEnabled={jsEnabled}
              />
            </div>
          )}
        </div>
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
