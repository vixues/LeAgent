import { memo } from 'react';
import { cn } from '@/lib/utils';
import { usePetDockPreview } from '@/hooks/usePetDockPreview';
import { useAuthedFileBlobUrl } from '@/hooks/useAuthedFileBlobUrl';
import { resolvedNest } from '@/lib/petSettings';

interface PetNestProps {
  active: boolean;
  /** Tighter chrome so the preview fits the collapsed rail gutter (same px-2 / p-2 inset as nav). */
  compact?: boolean;
  children: React.ReactNode;
}

export const PetNest = memo(function PetNest({ active, compact, children }: PetNestProps) {
  const { data: dock } = usePetDockPreview();
  const nest = resolvedNest(dock?.settings ?? {});
  const { url: bgUrl } = useAuthedFileBlobUrl(
    dock?.nestBackgroundFileId ?? null,
    dock?.nestBackgroundMime ?? null,
    dock?.nestBackgroundOriginalName ?? null,
  );
  const pattern = nest.backgroundPattern ?? 'none';
  const bgOpacity = nest.backgroundOpacity ?? 0.25;
  const bgFit = nest.backgroundFit ?? 'cover';
  const bgPosition = nest.backgroundPosition ?? 'center';

  return (
    <div
      className={cn(
        'pet-nest relative rounded-xl border overflow-visible transition-shadow',
        'border-border/80 bg-surface-sunken/40',
        active && 'ring-2 ring-primary-400/35 border-primary-300/60 dark:border-primary-700/50',
      )}
      data-theme={nest.themeId}
      data-pattern={pattern}
      data-bg-fit={bgFit}
      data-bg-position={bgPosition}
      style={
        {
          '--pet-nest-accent': nest.accent,
          '--pet-nest-bg-opacity': String(bgOpacity),
        } as React.CSSProperties
      }
    >
      <div
        className="pointer-events-none absolute inset-0 overflow-hidden rounded-[inherit]"
        aria-hidden
      >
        <div className="pet-nest__preset absolute inset-0 opacity-[0.22] dark:opacity-[0.28]" />
        {bgUrl ? (
          <div
            className="pet-nest__bg-photo absolute inset-0"
            style={{ backgroundImage: `url(${bgUrl})` }}
          />
        ) : null}
        {pattern !== 'none' ? (
          <div className={cn('pet-nest__pattern absolute inset-0', `pet-nest__pattern--${pattern}`)} />
        ) : null}
      </div>
      <div
        className={cn(
          'relative z-[1] overflow-visible rounded-[inherit]',
          compact ? 'p-px' : 'p-1 sm:p-1.5',
          'shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--pet-nest-accent)_18%,transparent)]',
        )}
      >
        {children}
      </div>
    </div>
  );
});
