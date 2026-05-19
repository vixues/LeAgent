import { memo } from 'react';
import { cn } from '@/lib/utils';

export type BrandMascotSize = 'xs' | 'sm' | 'md' | 'lg';

const SIZE_PX: Record<BrandMascotSize, number> = {
  xs: 14,
  sm: 24,
  md: 40,
  lg: 48,
};

/** Served from `public/brand/doge.svg` (Wikimedia Commons File:Doge.svg, CC BY-SA 4.0). */
export const BRAND_MASCOT_SRC = '/brand/doge.svg';

export interface BrandMascotProps {
  size?: BrandMascotSize;
  /** When true, use static gradient tile (reduced motion / tiny rail slot). */
  staticFallback?: boolean;
  className?: string;
  'aria-label'?: string;
  /** Hide from assistive tech (decorative uses). */
  'aria-hidden'?: boolean | 'true' | 'false';
}

/**
 * Doge mark — brand mascot. Asset: Wikimedia Commons Doge.svg (see `BRAND_MASCOT_SRC`).
 */
export const BrandMascot = memo(function BrandMascot({
  size = 'md',
  staticFallback = false,
  className,
  'aria-label': ariaLabel = 'Doge',
  'aria-hidden': ariaHidden,
}: BrandMascotProps) {
  const svgSize = SIZE_PX[size];
  const hidden = ariaHidden === true || ariaHidden === 'true';
  const imgAlt = hidden ? '' : ariaLabel;

  if (staticFallback) {
    return (
      <div
        aria-hidden={ariaHidden}
        className={cn(
          'rounded-lg bg-gradient-to-br from-primary-500 to-primary-700 flex items-center justify-center shadow-glow text-white font-bold select-none',
          size === 'xs' && 'text-[9px] w-3.5 h-3.5 rounded',
          size === 'sm' && 'text-xs w-6 h-6',
          size === 'md' && 'text-sm w-10 h-10',
          size === 'lg' && 'text-base w-12 h-12 rounded-2xl',
          className,
        )}
        role="img"
        aria-label={ariaLabel}
      >
        D
      </div>
    );
  }

  return (
    <span
      aria-hidden={ariaHidden}
      className={cn(
        'inline-flex max-h-full max-w-full items-end justify-center motion-safe:animate-float',
        className,
      )}
      style={{ transformBox: 'view-box', transformOrigin: '50% 50%' }}
    >
      <img
        src={BRAND_MASCOT_SRC}
        width={svgSize}
        height={svgSize}
        className="overflow-visible shrink-0 object-contain max-h-[inherit] max-w-[inherit]"
        alt={imgAlt}
      />
    </span>
  );
});
