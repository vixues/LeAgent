import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChatFileBlobUrl } from '@/hooks/useChatFileBlobUrl';
import {
  extractApiFilePreviewId,
  isInvalidApiFilePreviewRef,
  managedFilePreviewHasSignedToken,
} from './chatMediaUtils';
import { MediaLightbox } from './MediaLightbox';

interface ChatImageProps {
  src?: string;
  alt?: string;
  className?: string;
  /** Render as a fixed, cropped thumbnail (object-cover) instead of a full preview. */
  thumbnail?: boolean;
}

/**
 * Markdown / chat image with optional API preview blob URL and lightbox zoom.
 */
export function ChatImage({ src, alt = '', className, thumbnail = false }: ChatImageProps) {
  const { t } = useTranslation();
  const invalidManagedRef = useMemo(() => isInvalidApiFilePreviewRef(src), [src]);
  const managedId = useMemo(
    () => (invalidManagedRef ? null : extractApiFilePreviewId(src)),
    [src, invalidManagedRef],
  );
  const hasSignedPreviewToken = useMemo(() => managedFilePreviewHasSignedToken(src), [src]);
  const blobFetchId = managedId && !hasSignedPreviewToken ? managedId : null;
  const { blobUrl, isLoading: blobLoading, isError: blobError } = useChatFileBlobUrl(
    blobFetchId,
    alt,
  );
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
  }, [src, managedId]);

  useEffect(() => {
    if (blobUrl) setFailed(false);
  }, [blobUrl]);

  const trimmedSrc = src?.trim() ?? '';

  const displaySrc = useMemo(() => {
    if (failed && !managedId) return undefined;
    if (invalidManagedRef) return undefined;
    if (!managedId) return trimmedSrc || undefined;
    if (hasSignedPreviewToken && trimmedSrc && !failed) return trimmedSrc;
    if (blobUrl && !failed) return blobUrl;
    if (failed && hasSignedPreviewToken && trimmedSrc) return trimmedSrc;
    return undefined;
  }, [invalidManagedRef, managedId, blobUrl, failed, hasSignedPreviewToken, trimmedSrc]);

  if (!trimmedSrc && !blobUrl) return null;

  if (invalidManagedRef && trimmedSrc) {
    return (
      <a
        href={src}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 text-xs text-primary-600 dark:text-primary-400 hover:underline"
      >
        <ExternalLink className="w-3.5 h-3.5" aria-hidden />
        {t('chat.media.invalidFilePreview', { defaultValue: 'Invalid file preview link' })}
      </a>
    );
  }

  const interimSignedOnly =
    Boolean(managedId) && blobLoading && !blobUrl && hasSignedPreviewToken && trimmedSrc;

  if (Boolean(managedId) && blobLoading && !blobUrl && !interimSignedOnly) {
    return (
      <span className="inline-block min-h-[120px] min-w-[120px] max-w-full rounded-xl border border-border-subtle bg-surface-sunken/40 px-3 py-8 text-center text-xs text-muted-foreground">
        {t('chat.media.loading', { defaultValue: 'Loading…' })}
      </span>
    );
  }

  const noDisplayAndBlobFailed =
    Boolean(managedId) && blobError && !blobUrl && !hasSignedPreviewToken;

  const showOpenImageLink = noDisplayAndBlobFailed;

  if (failed && trimmedSrc && !displaySrc) {
    return (
      <span className="inline-flex max-w-full rounded-md bg-surface-sunken px-2 py-1 text-xs text-muted-foreground">
        {alt || t('chat.media.imageUnavailable', { defaultValue: 'Image unavailable' })}
      </span>
    );
  }

  if (showOpenImageLink) {
    return (
      <a
        href={src}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 text-xs text-primary-600 dark:text-primary-400 hover:underline"
      >
        <ExternalLink className="w-3.5 h-3.5" aria-hidden />
        {alt || t('chat.media.openImage', { defaultValue: 'Open image' })}
      </a>
    );
  }

  if (!displaySrc) {
    return (
      <span className="text-xs text-muted-foreground">
        {t('chat.media.loading', { defaultValue: 'Loading…' })}
      </span>
    );
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setLightboxOpen(true)}
        className={cn(
          'group block max-w-full overflow-hidden text-left',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/30',
          thumbnail && 'overflow-hidden',
          className,
        )}
        aria-label={t('chat.media.expandImage', { defaultValue: 'View larger' })}
      >
        <img
          src={displaySrc}
          alt={alt}
          loading="lazy"
          decoding="async"
          onError={() => setFailed(true)}
          className={cn(
            'overflow-hidden',
            thumbnail
              ? 'h-full w-full object-cover'
              : 'max-h-[min(70vh,480px)] w-full object-contain',
          )}
        />
      </button>
      <MediaLightbox
        open={lightboxOpen}
        onOpenChange={setLightboxOpen}
        src={displaySrc}
        alt={alt}
        kind="image"
      />
    </>
  );
}
