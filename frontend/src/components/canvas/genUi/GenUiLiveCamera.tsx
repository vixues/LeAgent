import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Camera, VideoOff } from 'lucide-react';
import { useChatDraftStore } from '@/stores/chatDraft';
import { cn } from '@/lib/utils';
import { PRIMARY_SOFT_CTA_CLASSNAME } from '@/components/ui/Button';
import type { GenUiNode } from '@/types/genUi';

const s = (v: unknown): string => (typeof v === 'string' ? v : v != null ? String(v) : '');

function parseFacingMode(raw: unknown): 'user' | 'environment' {
  return raw === 'environment' ? 'environment' : 'user';
}

const shellClass =
  'flex w-full flex-col overflow-hidden rounded-2xl border border-border/80 bg-surface text-foreground shadow-sm ring-1 ring-black/[0.04] dark:ring-white/[0.06]';

/** Live camera preview inside GenUi (SPA only). Default off; user opens/closes; stops tracks when closed. */
export function GenUiLiveCamera({ node }: { node: GenUiNode }) {
  const { t } = useTranslation();
  const p = (node.props || {}) as Record<string, unknown>;
  const facing = parseFacingMode(p.facingMode);
  const mirrored = Boolean(p.mirrored);
  const maxH = p.maxHeight ? `${Number(p.maxHeight)}px` : 'min(50vh, 360px)';
  const label = s(p.label) || 'Camera preview';

  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const setComposerFiles = useChatDraftStore((s) => s.setComposerFiles);

  const [err, setErr] = useState<string | null>(null);
  const [cameraOn, setCameraOn] = useState(false);
  const [active, setActive] = useState(false);
  const [capturing, setCapturing] = useState(false);

  const stopTracks = useCallback((stream: MediaStream | null) => {
    stream?.getTracks().forEach((tr) => {
      try {
        tr.stop();
      } catch {
        /* ignore */
      }
    });
  }, []);

  const closeCamera = useCallback(() => {
    stopTracks(streamRef.current);
    streamRef.current = null;
    const el = videoRef.current;
    if (el) el.srcObject = null;
    setCameraOn(false);
    setActive(false);
  }, [stopTracks]);

  useEffect(() => {
    if (!cameraOn) return;
    if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      setErr(
        t('chat.camera.notSupported', {
          defaultValue: 'Camera is not supported in this browser.',
        }),
      );
      setCameraOn(false);
      return;
    }

    let stream: MediaStream | null = null;
    let cancelled = false;
    setErr(null);
    setActive(false);

    void (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: facing },
          audio: false,
        });
        if (cancelled) {
          stopTracks(stream);
          return;
        }
        streamRef.current = stream;
        const el = videoRef.current;
        if (!el) {
          stopTracks(stream);
          streamRef.current = null;
          if (!cancelled) setCameraOn(false);
          return;
        }
        el.srcObject = stream;
        try {
          await el.play();
        } catch {
          stopTracks(stream);
          streamRef.current = null;
          if (!cancelled) {
            setErr(
              t('chat.camera.livePlaybackFailed', {
                defaultValue: 'Could not start video playback.',
              }),
            );
            setCameraOn(false);
          }
          return;
        }
        if (cancelled) return;
        setActive(true);
      } catch {
        if (!cancelled) {
          setErr(
            t('chat.camera.permissionDenied', {
              defaultValue: 'Could not access the camera. Check permissions.',
            }),
          );
          setCameraOn(false);
        }
      }
    })();

    return () => {
      cancelled = true;
      stopTracks(stream);
      streamRef.current = null;
      const el = videoRef.current;
      if (el) el.srcObject = null;
      setActive(false);
    };
  }, [cameraOn, facing, stopTracks, t]);

  const handleOpen = useCallback(() => {
    setErr(null);
    setCameraOn(true);
  }, []);

  const handleCapture = useCallback(() => {
    const video = videoRef.current;
    if (!video || !active || capturing) return;
    const w = video.videoWidth;
    const h = video.videoHeight;
    if (!w || !h) return;

    setCapturing(true);
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      setCapturing(false);
      return;
    }
    ctx.drawImage(video, 0, 0);
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          setCapturing(false);
          return;
        }
        const file = new File([blob], `camera-${Date.now()}.jpg`, {
          type: 'image/jpeg',
        });
        setComposerFiles((prev) => [...prev, file]);
        setCapturing(false);
      },
      'image/jpeg',
      0.92,
    );
  }, [active, capturing, setComposerFiles]);

  const unsupported =
    typeof navigator !== 'undefined' && !navigator.mediaDevices?.getUserMedia;

  if (unsupported) {
    return (
      <div
        key={node.nodeId}
        className={cn(
          'rounded-2xl border border-amber-200/80 bg-amber-50/90 px-3 py-2 text-xs text-amber-900',
          'dark:border-amber-800/60 dark:bg-amber-950/40 dark:text-amber-100',
        )}
        role="status"
      >
        {t('chat.camera.notSupported', {
          defaultValue: 'Camera is not supported in this browser.',
        })}
      </div>
    );
  }

  const idleHint = t('chat.camera.liveIdleHint', { defaultValue: 'Camera is off' });
  const openLabel = t('chat.camera.liveOpen', { defaultValue: 'Open camera' });
  const closeLabel = t('chat.camera.liveClose', { defaultValue: 'Close camera' });
  const captureLabel = t('chat.camera.liveCapture', { defaultValue: 'Take photo' });
  const startingLabel = t('chat.camera.liveStarting', { defaultValue: 'Starting camera…' });

  const toolbarLabel = t('chat.camera.title', { defaultValue: 'Camera' });

  const dockBtnBase =
    'inline-flex shrink-0 items-center justify-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/55 focus-visible:ring-offset-2 focus-visible:ring-offset-black';

  return (
    <div key={node.nodeId} className={shellClass}>
      {!cameraOn ? (
        <div
          className="flex min-h-[160px] flex-col items-center justify-center gap-4 px-5 py-8 text-center"
          style={{ maxHeight: maxH }}
        >
          {err ? (
            <div
              className={cn(
                'max-w-sm rounded-xl border border-border bg-surface-sunken px-3 py-2.5 text-sm text-muted-foreground',
              )}
              role="status"
            >
              {err}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">{idleHint}</p>
          )}
          <button
            type="button"
            onClick={handleOpen}
            aria-label={openLabel}
            title={openLabel}
            className={cn(
              'inline-flex h-14 w-14 items-center justify-center rounded-full',
              PRIMARY_SOFT_CTA_CLASSNAME,
              'border border-primary-300/80 dark:border-primary-600 shadow-md',
              'focus-visible:ring-2 focus-visible:ring-primary-500/55 focus-visible:ring-offset-2 focus-visible:ring-offset-surface',
            )}
          >
            <Camera className="size-7 shrink-0" aria-hidden />
          </button>
        </div>
      ) : (
        <div className="relative w-full min-h-[min(12.5rem,50vh)] bg-black">
          <video
            ref={videoRef}
            playsInline
            muted
            autoPlay
            className={cn('block w-full object-cover', mirrored && 'scale-x-[-1]')}
            style={{ maxHeight: maxH }}
            aria-label={label}
          />
          {!active && !err && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/50 text-sm text-white/80">
              {startingLabel}
            </div>
          )}

          <div
            role="toolbar"
            aria-label={toolbarLabel}
            className={cn(
              'pointer-events-auto absolute bottom-3 left-1/2 z-10 flex -translate-x-1/2 items-center gap-2 rounded-full',
              'border border-white/15 bg-black/40 px-2 py-1.5 backdrop-blur-md sm:gap-3',
            )}
          >
            <button
              type="button"
              onClick={closeCamera}
              aria-label={closeLabel}
              title={closeLabel}
              className={cn(
                dockBtnBase,
                'h-10 w-10 bg-white/10 text-white/90 hover:bg-white/20',
              )}
            >
              <VideoOff className="size-[18px] shrink-0" aria-hidden />
            </button>
            <button
              type="button"
              onClick={handleCapture}
              disabled={!active || capturing}
              aria-label={captureLabel}
              title={captureLabel}
              className={cn(
                dockBtnBase,
                'h-11 w-11 bg-white text-zinc-900 shadow-sm hover:bg-white/90',
                'disabled:pointer-events-none disabled:opacity-45',
              )}
            >
              <Camera className="size-[22px] shrink-0" aria-hidden />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
