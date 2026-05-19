import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiClient } from '@/api/client';
import { cn } from '@/lib/utils';

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) || '/api/v1';

function mjpegAbsoluteUrl(token: string): string {
  const base = API_BASE.replace(/\/$/, '');
  const path = `${base}/streams/rtsp/mjpeg`;
  const u = new URL(path, window.location.origin);
  u.searchParams.set('token', token);
  return u.href;
}

/** Inline RTSP preview when the API exposes ``POST /streams/rtsp/token`` (requires ffmpeg on the server). */
export function ChatRtspStream({ src, title }: { src: string; title?: string }) {
  const { t } = useTranslation();
  const [mjpegUrl, setMjpegUrl] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setErr(null);
    setMjpegUrl(null);
    (async () => {
      try {
        const data = await apiClient.post<{ token: string }>('/streams/rtsp/token', { url: src });
        if (cancelled) return;
        setMjpegUrl(mjpegAbsoluteUrl(data.token));
      } catch (e) {
        if (cancelled) return;
        setErr(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [src]);

  const onImgError = useCallback(() => {
    setErr(t('chat.media.rtspBroken', { defaultValue: 'Stream stopped or could not be decoded.' }));
  }, [t]);

  if (err) {
    return (
      <div
        className={cn(
          'my-3 rounded-xl border border-border-subtle bg-surface-sunken/40 px-4 py-3 text-sm text-muted-foreground',
        )}
      >
        <p className="font-medium text-foreground">
          {t('chat.media.rtspError', { defaultValue: 'RTSP preview unavailable' })}
        </p>
        <p className="mt-1 break-all">{err}</p>
        <a
          href={src}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 inline-block text-primary-600 dark:text-primary-400 hover:underline"
        >
          {t('chat.media.rtspOpenLink', { defaultValue: 'Open RTSP URL' })}
        </a>
      </div>
    );
  }

  if (!mjpegUrl) {
    return (
      <div
        className={cn(
          'my-3 rounded-xl border border-border-subtle bg-surface-sunken/30 px-4 py-6 text-center text-sm text-muted-foreground',
        )}
      >
        {t('chat.media.rtspLoading', { defaultValue: 'Starting RTSP preview…' })}
      </div>
    );
  }

  return (
    <div
      className={cn(
        'my-3 overflow-hidden rounded-xl border border-border-subtle bg-black/80 shadow-soft max-w-full',
      )}
    >
      <img
        src={mjpegUrl}
        alt={title ?? t('chat.media.rtspStreamAlt', { defaultValue: 'RTSP video stream' })}
        className="max-h-[min(70vh,480px)] w-full object-contain bg-black"
        onError={onImgError}
      />
      <div className="border-t border-border-subtle bg-surface-sunken/30 px-3 py-2 text-xs">
        <a
          href={src}
          target="_blank"
          rel="noopener noreferrer"
          className="break-all text-primary-600 dark:text-primary-400 hover:underline"
        >
          {src}
        </a>
      </div>
    </div>
  );
}
