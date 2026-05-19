import { Image as ImageIcon, FileIcon } from 'lucide-react';
import type { PetProjectFileRow } from '@/api/petSpace';
import { useAuthedFileBlobUrl } from '@/hooks/useAuthedFileBlobUrl';
import { cn } from '@/lib/utils';
import { isPetRenderableImageRow } from '@/lib/petAppearanceMime';

export function FileThumb({
  row,
  variant = 'row',
  cardSize = 'default',
}: {
  row: PetProjectFileRow;
  variant?: 'row' | 'card';
  /** Smaller square hero for compact dex cards (e.g. customize tab). */
  cardSize?: 'default' | 'compact';
}) {
  const { url: src } = useAuthedFileBlobUrl(row.file_id, row.mime_type, row.original_name);
  if (variant === 'card') {
    const frame = cn(
      'flex min-h-0 items-center justify-center rounded-lg border border-border-subtle bg-surface-sunken/40 p-1',
      cardSize === 'compact'
        ? 'mx-auto h-24 w-24 shrink-0'
        : 'aspect-square w-full min-h-0',
    );
    if (src) {
      return (
        <div className={frame}>
          <img src={src} alt="" className="h-full w-full max-h-full max-w-full object-contain rounded-md" />
        </div>
      );
    }
    if (isPetRenderableImageRow(row)) {
      return (
        <div className={frame}>
          <ImageIcon className={cn(cardSize === 'compact' ? 'h-6 w-6' : 'h-8 w-8', 'text-muted-foreground')} />
        </div>
      );
    }
    return (
      <div className={frame}>
        <FileIcon className={cn(cardSize === 'compact' ? 'h-6 w-6' : 'h-8 w-8', 'text-muted-foreground')} />
      </div>
    );
  }
  if (src) {
    return (
      <img src={src} alt="" className="w-12 h-12 rounded-lg object-cover border border-border-subtle" />
    );
  }
  if (isPetRenderableImageRow(row)) {
    return (
      <div className="flex h-12 w-12 items-center justify-center rounded-lg border border-border-subtle bg-surface-sunken">
        <ImageIcon className="h-5 w-5 text-muted-foreground" />
      </div>
    );
  }
  return (
    <div className="flex h-12 w-12 items-center justify-center rounded-lg border border-border-subtle bg-surface-sunken">
      <FileIcon className="h-5 w-5 text-muted-foreground" />
    </div>
  );
}
