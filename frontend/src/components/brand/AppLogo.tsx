import { memo } from 'react';
import { cn } from '@/lib/utils';

/** Default sidebar / app mark — `public/brand/logo.svg` (synced from repo `file.svg`, same pixels as `favicon.svg`). */
export const DEFAULT_BRAND_LOGO_SRC = '/brand/logo.svg';

export interface AppLogoProps {
  className?: string;
  /** When set (e.g. user-uploaded data URL), overrides the default SVG mark. */
  src?: string | null;
}

/**
 * Product logo: SVG from static `/favicon.svg` unless the user uploads a custom icon in Settings.
 */
export const AppLogo = memo(function AppLogo({ className, src: srcOverride }: AppLogoProps) {
  const src =
    srcOverride && srcOverride.length > 0 ? srcOverride : DEFAULT_BRAND_LOGO_SRC;

  return (
    <img
      src={src}
      alt=""
      width={32}
      height={32}
      decoding="async"
      className={cn('size-8 shrink-0 rounded-lg object-contain', className)}
    />
  );
});
