import { useMemo } from 'react';
import { cn } from '@/lib/utils';
import { useChatFileBlobUrl } from '@/hooks/useChatFileBlobUrl';
import {
  extractApiFilePreviewId,
  isInvalidApiFilePreviewRef,
  managedFilePreviewHasSignedToken,
} from '@/components/chat/media/chatMediaUtils';
import type { GenUiMediaItem } from '@/components/canvas/genUi/genUiMedia';
import { CanvasMesh3DPreview } from '@/features/workflow/components/CanvasMesh3DPreview';

/** Resolve a (possibly managed) media src to a directly-renderable URL. */
export function useResolvedSrc(
  rawSrc: string,
  managedIdOverride?: string | null,
): { src: string | undefined; loading: boolean } {
  const invalid = useMemo(() => isInvalidApiFilePreviewRef(rawSrc), [rawSrc]);
  const managedId = useMemo(() => {
    if (managedIdOverride?.trim()) return managedIdOverride.trim();
    return invalid ? null : extractApiFilePreviewId(rawSrc);
  }, [rawSrc, invalid, managedIdOverride]);
  const signed = useMemo(() => managedFilePreviewHasSignedToken(rawSrc), [rawSrc]);
  const { blobUrl, isLoading } = useChatFileBlobUrl(managedId);
  const trimmed = rawSrc.trim();
  const src = useMemo(() => {
    if (invalid) return undefined;
    if (!managedId) return trimmed || undefined;
    if (blobUrl) return blobUrl;
    if (signed && trimmed) return trimmed;
    return undefined;
  }, [invalid, managedId, blobUrl, signed, trimmed]);
  return { src, loading: Boolean(managedId) && isLoading && !src };
}

/**
 * Compact, ComfyUI-style media thumbnail rendered *inside* a workflow node
 * card once it finishes generating. Images/videos render inline; 3D meshes
 * render a lightweight chip (the full GLB viewer lives in the run panel
 * gallery to avoid spinning a WebGL context per node).
 */
export function NodeMediaPreview({ item }: { item: GenUiMediaItem }) {
  const { src, loading } = useResolvedSrc(item.src);

  if (item.kind === 'Model3D') {
    return (
      <CanvasMesh3DPreview previewUrl={src || item.src} height={140} className="rounded-md" />
    );
  }

  if (loading) {
    return <div className="h-20 w-full animate-pulse rounded-md bg-surface-sunken" aria-hidden />;
  }

  if (!src) return null;

  if (item.kind === 'Video') {
    return (
      <video
        src={src}
        poster={item.poster}
        className={cn('w-full rounded-md bg-black')}
        style={{ maxHeight: 140 }}
        muted
        loop
        autoPlay
        playsInline
      />
    );
  }

  return (
    <img
      src={src}
      alt={item.caption || 'preview'}
      className="w-full rounded-md object-contain"
      style={{ maxHeight: 140 }}
      loading="lazy"
      decoding="async"
    />
  );
}
