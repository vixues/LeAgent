import type { CSSProperties } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { ImageOff } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChatFileBlobUrl } from '@/hooks/useChatFileBlobUrl';
import {
  extractApiFilePreviewId,
  isInvalidApiFilePreviewRef,
  managedFilePreviewHasSignedToken,
} from '@/components/chat/media/chatMediaUtils';
import { MediaLightbox } from '@/components/chat/media/MediaLightbox';
import type { GenUiNode } from '@/types/genUi';

const s = (v: unknown): string => (typeof v === 'string' ? v : v != null ? String(v) : '');
const b = (v: unknown): boolean => Boolean(v);

const FIT_MAP: Record<string, string> = {
  cover: 'object-cover',
  contain: 'object-contain',
  fill: 'object-fill',
};

const SHADOW_MAP: Record<string, string> = {
  none: '',
  sm: 'shadow-sm',
  md: 'shadow-md',
  lg: 'shadow-lg',
};

/** GenUi ``Image`` with optional API file preview, lightbox, and layout props. */
export function GenUiImage({ node }: { node: GenUiNode }) {
  const p = (node.props || {}) as Record<string, unknown>;
  const rawSrc = (p.src as string) || '';
  const invalidManagedRef = useMemo(() => isInvalidApiFilePreviewRef(rawSrc), [rawSrc]);
  const managedId = useMemo(
    () => (invalidManagedRef ? null : extractApiFilePreviewId(rawSrc)),
    [rawSrc, invalidManagedRef],
  );
  const hasSignedPreviewToken = useMemo(() => managedFilePreviewHasSignedToken(rawSrc), [rawSrc]);
  const { blobUrl, isLoading: blobLoading, isError: blobError } = useChatFileBlobUrl(managedId);
  const [failed, setFailed] = useState(false);
  const [lightboxOpen, setLightboxOpen] = useState(false);

  useEffect(() => {
    setFailed(false);
  }, [rawSrc, managedId]);

  useEffect(() => {
    if (blobUrl) setFailed(false);
  }, [blobUrl]);

  const maxH = p.maxHeight ? `${p.maxHeight as number}px` : undefined;
  const fitClass = FIT_MAP[(p.fit as string) || ''] || 'object-cover';
  const shadowClass = SHADOW_MAP[(p.shadow as string) || 'none'] || '';
  const aspectStyle =
    typeof p.aspect === 'string' && p.aspect.trim()
      ? ({ aspectRatio: p.aspect.trim().replace(':', ' / ') } as CSSProperties)
      : undefined;
  const priority = b(p.priority);
  const rounded = b(p.rounded);
  const altText = s(p.alt) || s(p.caption) || 'image';

  const trimmed = rawSrc.trim();
  const displaySrc = useMemo(() => {
    if (invalidManagedRef) return undefined;
    if (!managedId) return trimmed || undefined;
    if (blobUrl) return blobUrl;
    if (hasSignedPreviewToken && trimmed) return trimmed;
    return undefined;
  }, [invalidManagedRef, managedId, blobUrl, hasSignedPreviewToken, trimmed]);

  const lightboxOptIn = p.lightbox != null ? b(p.lightbox) : Boolean(p.aspect) || (typeof p.maxHeight === 'number' && p.maxHeight >= 240);
  const useLightbox = lightboxOptIn && Boolean(displaySrc) && !failed;

  if (invalidManagedRef) {
    return (
      <figure
        key={node.nodeId}
        className={cn(
          'flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border bg-surface-sunken/60 p-4 text-center',
        )}
        style={{ ...aspectStyle, maxHeight: maxH }}
      >
        <ImageOff className="h-6 w-6 text-muted-foreground-tertiary" aria-hidden />
        <figcaption className="text-xs text-muted-foreground line-clamp-2 break-all">
          {s(p.caption) || altText}
        </figcaption>
        {rawSrc && (
          <span className="text-[10px] text-muted-foreground-tertiary line-clamp-1 break-all">
            {rawSrc}
          </span>
        )}
      </figure>
    );
  }

  const interimSignedOnly =
    Boolean(managedId) && blobLoading && !blobUrl && hasSignedPreviewToken && trimmed;

  if (Boolean(managedId) && blobLoading && !blobUrl && !interimSignedOnly) {
    return (
      <figure key={node.nodeId} className="space-y-1">
        <div
          className={cn('w-full animate-pulse rounded-xl bg-surface-sunken', !aspectStyle && 'h-32')}
          style={{ ...aspectStyle, maxHeight: maxH }}
          aria-hidden
        />
        {!!p.caption && <figcaption className="text-xs text-muted-foreground text-center">{s(p.caption)}</figcaption>}
      </figure>
    );
  }

  if (Boolean(managedId) && blobError && !blobUrl && !hasSignedPreviewToken) {
    return (
      <figure
        key={node.nodeId}
        className={cn(
          'flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border bg-surface-sunken/60 p-4 text-center',
        )}
        style={{ ...aspectStyle, maxHeight: maxH }}
      >
        <ImageOff className="h-6 w-6 text-muted-foreground-tertiary" aria-hidden />
        <figcaption className="text-xs text-muted-foreground line-clamp-2 break-all">
          {s(p.caption) || altText}
        </figcaption>
      </figure>
    );
  }

  if (failed && managedId && trimmed && !blobUrl) {
    return (
      <figure
        key={node.nodeId}
        className={cn(
          'flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border bg-surface-sunken/60 p-4 text-center',
        )}
        style={{ ...aspectStyle, maxHeight: maxH }}
      >
        <ImageOff className="h-6 w-6 text-muted-foreground-tertiary" aria-hidden />
        <figcaption className="text-xs text-muted-foreground line-clamp-2 break-all">
          {s(p.caption) || altText}
        </figcaption>
        {rawSrc && (
          <span className="text-[10px] text-muted-foreground-tertiary line-clamp-1 break-all">
            {rawSrc}
          </span>
        )}
      </figure>
    );
  }

  if (failed && !managedId) {
    return (
      <figure
        key={node.nodeId}
        className={cn(
          'flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border bg-surface-sunken/60 p-4 text-center',
        )}
        style={{ ...aspectStyle, maxHeight: maxH }}
      >
        <ImageOff className="h-6 w-6 text-muted-foreground-tertiary" aria-hidden />
        <figcaption className="text-xs text-muted-foreground line-clamp-2 break-all">
          {s(p.caption) || altText}
        </figcaption>
        {rawSrc && (
          <span className="text-[10px] text-muted-foreground-tertiary line-clamp-1 break-all">
            {rawSrc}
          </span>
        )}
      </figure>
    );
  }

  if (!displaySrc) {
    return (
      <figure key={node.nodeId} className="text-xs text-muted-foreground">
        Missing image src
      </figure>
    );
  }

  const img = (
    <img
      src={displaySrc}
      alt={altText}
      className={cn(
        'w-full max-h-[min(70vh,560px)]',
        fitClass,
        rounded && 'rounded-xl',
        shadowClass,
        useLightbox && 'cursor-zoom-in',
      )}
      style={{ ...aspectStyle, maxHeight: maxH }}
      loading={priority ? 'eager' : 'lazy'}
      decoding={priority ? 'auto' : 'async'}
      onError={() => setFailed(true)}
    />
  );

  return (
    <figure key={node.nodeId} className="space-y-1">
      {useLightbox ? (
        <button
          type="button"
          className="block w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40 rounded-xl"
          onClick={() => setLightboxOpen(true)}
        >
          {img}
        </button>
      ) : (
        img
      )}
      {!!p.caption && <figcaption className="text-xs text-muted-foreground text-center">{s(p.caption)}</figcaption>}
      {useLightbox && (
        <MediaLightbox
          open={lightboxOpen}
          onOpenChange={setLightboxOpen}
          src={displaySrc}
          alt={altText}
          kind="image"
        />
      )}
    </figure>
  );
}
