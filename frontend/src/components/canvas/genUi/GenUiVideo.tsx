import { useMemo } from 'react';
import { VideoOff } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChatFileBlobUrl } from '@/hooks/useChatFileBlobUrl';
import {
  extractApiFilePreviewId,
  isInvalidApiFilePreviewRef,
  managedFilePreviewHasSignedToken,
} from '@/components/chat/media/chatMediaUtils';
import type { GenUiNode } from '@/types/genUi';

const s = (v: unknown): string => (typeof v === 'string' ? v : v != null ? String(v) : '');
const b = (v: unknown): boolean => Boolean(v);

/** GenUi ``Video`` — inline player for a generated clip (managed file or URL). */
export function GenUiVideo({ node }: { node: GenUiNode }) {
  const p = (node.props || {}) as Record<string, unknown>;
  const rawSrc = (p.src as string) || '';
  const invalidManagedRef = useMemo(() => isInvalidApiFilePreviewRef(rawSrc), [rawSrc]);
  const managedId = useMemo(
    () => (invalidManagedRef ? null : extractApiFilePreviewId(rawSrc)),
    [rawSrc, invalidManagedRef],
  );
  const hasSignedPreviewToken = useMemo(() => managedFilePreviewHasSignedToken(rawSrc), [rawSrc]);
  const { blobUrl, isLoading: blobLoading } = useChatFileBlobUrl(managedId);

  const trimmed = rawSrc.trim();
  const displaySrc = useMemo(() => {
    if (invalidManagedRef) return undefined;
    if (!managedId) return trimmed || undefined;
    if (blobUrl) return blobUrl;
    if (hasSignedPreviewToken && trimmed) return trimmed;
    return undefined;
  }, [invalidManagedRef, managedId, blobUrl, hasSignedPreviewToken, trimmed]);

  const maxH = p.maxHeight ? `${p.maxHeight as number}px` : undefined;
  const rounded = b(p.rounded);
  const caption = s(p.caption);

  if (Boolean(managedId) && blobLoading && !displaySrc) {
    return (
      <figure key={node.nodeId} className="space-y-1">
        <div
          className={cn('w-full animate-pulse rounded-xl bg-surface-sunken h-40', rounded && 'rounded-xl')}
          style={{ maxHeight: maxH }}
          aria-hidden
        />
        {!!caption && <figcaption className="text-xs text-muted-foreground text-center">{caption}</figcaption>}
      </figure>
    );
  }

  if (!displaySrc) {
    return (
      <figure
        key={node.nodeId}
        className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border bg-surface-sunken/60 p-4 text-center"
        style={{ maxHeight: maxH }}
      >
        <VideoOff className="h-6 w-6 text-muted-foreground-tertiary" aria-hidden />
        <figcaption className="text-xs text-muted-foreground line-clamp-2 break-all">
          {caption || 'Missing video src'}
        </figcaption>
      </figure>
    );
  }

  return (
    <figure key={node.nodeId} className="space-y-1">
      <video
        src={displaySrc}
        poster={s(p.poster) || undefined}
        className={cn('w-full max-h-[min(70vh,560px)] bg-black', rounded && 'rounded-xl')}
        style={{ maxHeight: maxH }}
        controls={p.controls !== false}
        autoPlay={b(p.autoPlay)}
        loop={p.loop !== false}
        muted={p.muted !== false}
        playsInline
      />
      {!!caption && <figcaption className="text-xs text-muted-foreground text-center">{caption}</figcaption>}
    </figure>
  );
}
