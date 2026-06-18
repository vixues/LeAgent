import { type MouseEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Download, FileAudio } from 'lucide-react';

import {
  extractApiFileDownloadId,
  extractApiFilePreviewId,
} from '@/components/chat/media/chatMediaUtils';
import { downloadAuthenticatedFile } from '@/lib/downloadAuthenticatedFile';
import { CanvasMesh3DPreview } from '@/features/workflow/components/CanvasMesh3DPreview';
import { useResolvedSrc } from './NodeMediaPreview';

/** Media kind carried by a workflow ``MediaRef``. */
export type ArtifactKind = 'image' | 'video' | 'model3d' | 'audio' | 'vfx';

export interface ArtifactDescriptor {
  kind: ArtifactKind;
  src: string;
  /** Managed file id — used to bust browser/blob cache when src paths collide. */
  fileId?: string;
  filename?: string;
  width?: number | null;
  height?: number | null;
  mime?: string;
  downloadUrl?: string;
  fileSize?: number | null;
  placeholder?: boolean;
}

const KIND_BADGE: Record<ArtifactKind, string> = {
  image: 'IMG',
  video: 'VID',
  model3d: '3D',
  audio: 'AUD',
  vfx: 'VFX',
};

function formatSize(bytes?: number | null): string | null {
  if (bytes == null || !Number.isFinite(bytes) || bytes <= 0) return null;
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value >= 10 || unit === 0 ? Math.round(value) : value.toFixed(1)} ${units[unit]}`;
}

function ArtifactMedia({
  descriptor,
  height,
}: {
  descriptor: ArtifactDescriptor;
  height: number;
}) {
  const managedId =
    descriptor.fileId?.trim() ||
    extractApiFilePreviewId(descriptor.src) ||
    null;
  const { src: resolvedSrc, loading } = useResolvedSrc(descriptor.src, managedId);
  const src = resolvedSrc;

  if (descriptor.kind === 'model3d') {
    return (
      <CanvasMesh3DPreview
        previewUrl={src || descriptor.src}
        height={height}
        className="rounded-md"
      />
    );
  }

  if (loading) {
    return (
      <div
        className="w-full animate-pulse rounded-md bg-surface-sunken"
        style={{ height }}
        aria-hidden
      />
    );
  }

  if (!src) {
    return (
      <div
        className="flex w-full items-center justify-center rounded-md bg-surface-sunken text-[10px] text-muted-foreground"
        style={{ height }}
      >
        {descriptor.filename || descriptor.kind}
      </div>
    );
  }

  if (descriptor.kind === 'video') {
    return (
      <video
        src={src}
        className="w-full rounded-md bg-black"
        style={{ maxHeight: height }}
        muted
        loop
        autoPlay
        playsInline
      />
    );
  }

  if (descriptor.kind === 'audio') {
    return (
      <div className="flex w-full items-center gap-2 rounded-md bg-surface-sunken px-2 py-2">
        <FileAudio className="h-4 w-4 flex-shrink-0 text-muted-foreground" aria-hidden />
        <audio src={src} controls className="h-8 w-full" />
      </div>
    );
  }

  return (
    <img
      key={descriptor.fileId ?? descriptor.src}
      src={src}
      alt={descriptor.filename || 'artifact'}
      className="w-full rounded-md object-contain"
      style={{ maxHeight: height }}
      loading="lazy"
      decoding="async"
    />
  );
}

/**
 * Professional artifact preview card rendered inside a workflow node. Shows the
 * media itself (image / video / 3D / audio) plus a metadata footer — filename,
 * kind, dimensions, file size — and an authenticated download button.
 *
 * ``full`` is used by the dedicated ``Art.Preview`` node; ``compact`` enriches
 * the inline preview shown on generation / processing nodes once they finish.
 */
export function NodeArtifactPreview({
  descriptor,
  variant = 'compact',
  title,
}: {
  descriptor: ArtifactDescriptor;
  variant?: 'compact' | 'full';
  title?: string;
}) {
  const { t } = useTranslation();
  const full = variant === 'full';
  const height = full ? 240 : 140;

  const dims =
    descriptor.width && descriptor.height
      ? `${descriptor.width}\u00d7${descriptor.height}`
      : null;
  const size = formatSize(descriptor.fileSize);
  const filename = descriptor.filename;

  const downloadId =
    extractApiFileDownloadId(descriptor.downloadUrl) ??
    extractApiFilePreviewId(descriptor.src) ??
    extractApiFilePreviewId(descriptor.downloadUrl);
  const downloadLabel = t('artifactPreview.download', 'Download');

  const handleDownload = (event: MouseEvent<HTMLButtonElement | HTMLAnchorElement>) => {
    if (!downloadId) return;
    event.preventDefault();
    void downloadAuthenticatedFile(downloadId, filename || `artifact.${descriptor.kind}`);
  };
  const downloadHref = descriptor.downloadUrl || descriptor.src;

  return (
    <div className="flex flex-col gap-1.5">
      {full && title ? (
        <div className="truncate text-[11px] font-semibold text-foreground" title={title}>
          {title}
        </div>
      ) : null}

      <ArtifactMedia descriptor={descriptor} height={height} />

      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          <span className="flex-shrink-0 rounded bg-primary/15 px-1 py-0.5 text-[8px] font-semibold uppercase tracking-wide text-primary">
            {KIND_BADGE[descriptor.kind]}
          </span>
          {filename ? (
            <span className="truncate text-[10px] text-muted-foreground" title={filename}>
              {filename}
            </span>
          ) : null}
        </div>

        {downloadHref ? (
          <a
            href={downloadHref}
            download={filename || true}
            onClick={downloadId ? handleDownload : undefined}
            className="flex flex-shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] text-muted-foreground transition-colors hover:bg-surface-sunken hover:text-foreground"
            aria-label={downloadLabel}
            title={downloadLabel}
          >
            <Download className="h-3 w-3" aria-hidden />
            {full ? downloadLabel : null}
          </a>
        ) : null}
      </div>

      {(dims || size || (full && descriptor.mime)) && (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[9px] text-muted-foreground-tertiary">
          {dims ? <span>{dims}</span> : null}
          {size ? <span>{size}</span> : null}
          {full && descriptor.mime ? <span className="truncate">{descriptor.mime}</span> : null}
          {descriptor.placeholder ? (
            <span className="text-amber-600 dark:text-amber-400">
              {t('artifactPreview.offline', 'offline')}
            </span>
          ) : null}
        </div>
      )}
    </div>
  );
}
