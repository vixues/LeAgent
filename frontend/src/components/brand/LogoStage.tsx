import { memo, useEffect, useState, useMemo, type CSSProperties } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import {
  getLogoBackdropStyle,
  getMinimalBrandMarkStyle,
  getMinimalBrandTitleStyle,
  isMinimalBackdrop,
  MINIMAL_BRAND_MARK_SRC,
} from '@/lib/brandingBackdrop';
import { useTheme } from '@/hooks/useTheme';
import { useBrandingStore, resolveDisplayName, type BrandFontPreset } from '@/stores/branding';
import { AppLogo } from './AppLogo';

function useBrandingClockHour(): number {
  const [hour, setHour] = useState(() => new Date().getHours());

  useEffect(() => {
    const tick = () => setHour(new Date().getHours());
    const id = window.setInterval(tick, 60_000);
    const onVis = () => {
      if (document.visibilityState === 'visible') tick();
    };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      window.clearInterval(id);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, []);

  return hour;
}

const frostedInner =
  'relative z-[1] flex items-center gap-2 rounded-lg';

const brandFontStyles: Record<BrandFontPreset, CSSProperties> = {
  modern: {
    fontFamily: 'Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    letterSpacing: '-0.035em',
  },
  rounded: {
    fontFamily: '"Trebuchet MS", "Avenir Next Rounded Std", ui-rounded, system-ui, sans-serif',
    letterSpacing: '-0.025em',
  },
  handwritten: {
    fontFamily: '"Comic Sans MS", "Bradley Hand", "Segoe Print", cursive',
    letterSpacing: '-0.015em',
  },
  mono: {
    fontFamily: '"JetBrains Mono", "Fira Code", ui-monospace, SFMono-Regular, monospace',
    letterSpacing: '-0.04em',
  },
};

function BrandMark({
  customIcon,
  minimal,
  className,
}: {
  customIcon: string | null;
  minimal: boolean;
  className?: string;
}) {
  if (minimal) {
    // Custom upload: tint with favicon gradient via mask. Default: use favicon.svg itself.
    if (customIcon && customIcon.length > 0) {
      return (
        <span
          className={cn('block shrink-0 rounded-lg', className)}
          style={getMinimalBrandMarkStyle(customIcon)}
          aria-hidden
        />
      );
    }
    return (
      <AppLogo
        src={MINIMAL_BRAND_MARK_SRC}
        className={className}
      />
    );
  }
  return <AppLogo src={customIcon} className={className} />;
}

interface LogoStageRailProps {
  collapsed: boolean;
  isMobile: boolean;
  onCollapsedChange?: (collapsed: boolean) => void;
  /** Close mobile drawer when navigating home from the expanded logo. */
  onMobileClose?: () => void;
}

export const LogoStageRail = memo(function LogoStageRail({
  collapsed,
  isMobile,
  onCollapsedChange,
  onMobileClose,
}: LogoStageRailProps) {
  const { t } = useTranslation();
  const { resolvedTheme } = useTheme();
  const hour = useBrandingClockHour();
  const displayName = useBrandingStore((s) => s.displayName);
  const customIcon = useBrandingStore((s) => s.customIconDataUrl);
  const preset = useBrandingStore((s) => s.logoBackdropPreset);
  const fontPreset = useBrandingStore((s) => s.brandFontPreset);

  const title = resolveDisplayName(displayName);
  const minimal = isMinimalBackdrop(preset);
  const backdropStyle = useMemo(
    () => getLogoBackdropStyle(hour, preset, resolvedTheme),
    [hour, preset, resolvedTheme],
  );
  const brandFontStyle = brandFontStyles[fontPreset] ?? brandFontStyles.modern;
  const titleStyle = useMemo(
    () => (minimal ? { ...brandFontStyle, ...getMinimalBrandTitleStyle() } : brandFontStyle),
    [brandFontStyle, minimal],
  );

  const stageShell = cn(
    'relative w-full overflow-hidden rounded-xl',
    !minimal && 'ring-1 ring-black/5 dark:ring-white/10',
  );

  const backdropLayer = (staticFill = false) => {
    if (minimal) return null;
    return (
      <>
        <div
          className={cn(
            'logo-stage-backdrop absolute inset-0 rounded-[inherit]',
            staticFill && 'logo-stage-backdrop--static',
          )}
          style={backdropStyle}
          aria-hidden
        />
        <div
          className={cn(
            'pointer-events-none absolute inset-0 rounded-[inherit] mix-blend-soft-light',
            resolvedTheme === 'dark' ? 'opacity-[0.055]' : 'opacity-[0.035]',
            staticFill && 'opacity-0',
          )}
          style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
          }}
          aria-hidden
        />
      </>
    );
  };

  /*
   * One morphing body for both states. Logo sits in a fixed 40px grid column that
   * never shrinks — even while the rail width is still animating after click.
   */
  const stageBody = (showTitle: boolean) => (
    <>
      {backdropLayer(!showTitle)}
      <div
        className={cn(
          frostedInner,
          'relative min-h-0 min-w-0 flex-1 items-center gap-2',
          showTitle
            ? 'm-1.5 grid grid-cols-[2.5rem_minmax(0,1fr)] px-2.5 py-1.5'
            : 'm-1 grid grid-cols-1 justify-items-center px-0 py-0',
        )}
      >
        <span className="flex h-10 w-10 items-center justify-center">
          <BrandMark
            customIcon={customIcon}
            minimal={minimal}
            className={cn(
              '!size-10 !min-h-10 !min-w-10 !max-h-10 !max-w-10 object-contain',
              !minimal &&
                (resolvedTheme === 'dark'
                  ? 'drop-shadow-[0_1px_2px_rgba(0,0,0,0.38)]'
                  : 'drop-shadow-[0_1px_2px_rgba(15,23,42,0.28)]'),
            )}
          />
        </span>
        <span
          aria-hidden={!showTitle}
          className={cn(
            'truncate whitespace-nowrap text-xl font-extrabold leading-snug',
            'transition-[opacity,transform] duration-200 ease-out',
            minimal ? null : 'text-white',
            !minimal &&
              (resolvedTheme === 'dark'
                ? 'drop-shadow-[0_1px_2px_rgba(0,0,0,0.35)]'
                : 'drop-shadow-[0_1px_2px_rgba(15,23,42,0.22)]'),
            showTitle
              ? 'min-w-0 translate-x-0 opacity-100'
              : 'pointer-events-none absolute w-0 overflow-hidden opacity-0',
          )}
          style={titleStyle}
        >
          {title}
        </span>
      </div>
    </>
  );

  if (isMobile) {
    return (
      <div className="px-2 pt-2 pb-1 flex-shrink-0">
        <Link
          to="/home"
          onClick={() => onMobileClose?.()}
          className={cn(
            stageShell,
            'flex min-h-[56px] w-full items-stretch text-left transition-opacity duration-150 active:opacity-90'
          )}
          aria-label={title}
        >
          {stageBody(true)}
        </Link>
      </div>
    );
  }

  return (
    <div className="px-2 pt-2 pb-1 flex-shrink-0">
      <button
        type="button"
        onClick={() => onCollapsedChange?.(!collapsed)}
        title={collapsed ? t('nav.expandRail') : t('nav.collapseRail')}
        className={cn(
          stageShell,
          // Fixed heights only — never `aspect-square` here: `collapsed` flips
          // instantly but the rail width still animates for 200ms, so
          // aspect-square would briefly match the full expanded width (~238px)
          // and the tile looks like it zooms before shrinking.
          'flex w-full items-stretch text-left',
          'cursor-pointer transition-[height] duration-200 ease-[cubic-bezier(0.4,0,0.2,1)] motion-reduce:transition-none',
          collapsed ? 'h-12' : 'h-[68px]'
        )}
        aria-label={collapsed ? t('nav.expandRail') : t('nav.collapseRail')}
      >
        {stageBody(!collapsed)}
      </button>
    </div>
  );
});

export const LogoStageMobile = memo(function LogoStageMobile() {
  const { resolvedTheme } = useTheme();
  const hour = useBrandingClockHour();
  const displayName = useBrandingStore((s) => s.displayName);
  const customIcon = useBrandingStore((s) => s.customIconDataUrl);
  const preset = useBrandingStore((s) => s.logoBackdropPreset);
  const fontPreset = useBrandingStore((s) => s.brandFontPreset);
  const title = resolveDisplayName(displayName);
  const minimal = isMinimalBackdrop(preset);
  const backdropStyle = useMemo(
    () => getLogoBackdropStyle(hour, preset, resolvedTheme),
    [hour, preset, resolvedTheme],
  );
  const brandFontStyle = brandFontStyles[fontPreset] ?? brandFontStyles.modern;
  const titleStyle = useMemo(
    () => (minimal ? { ...brandFontStyle, ...getMinimalBrandTitleStyle() } : brandFontStyle),
    [brandFontStyle, minimal],
  );

  return (
    <Link to="/home" className="flex min-w-0 flex-1 items-center">
      <div
        className={cn(
          'relative flex min-h-10 w-full min-w-0 overflow-hidden rounded-xl',
          !minimal && 'ring-1 ring-black/5 dark:ring-white/10',
        )}
      >
        {!minimal ? (
          <>
            <div className="logo-stage-backdrop absolute inset-0" style={backdropStyle} aria-hidden />
            <div
              className={cn(
                'pointer-events-none absolute inset-0 mix-blend-soft-light',
                resolvedTheme === 'dark' ? 'opacity-[0.055]' : 'opacity-[0.035]',
              )}
              style={{
                backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
              }}
              aria-hidden
            />
          </>
        ) : null}
        <div className={cn(frostedInner, 'm-1 min-w-0 flex-1 gap-2 px-2 py-1.5')}>
          <BrandMark
            customIcon={customIcon}
            minimal={minimal}
            className={cn(
              'size-7 shrink-0',
              !minimal &&
                (resolvedTheme === 'dark'
                  ? 'drop-shadow-[0_1px_2px_rgba(0,0,0,0.38)]'
                  : 'drop-shadow-[0_1px_2px_rgba(15,23,42,0.28)]'),
            )}
          />
          <span
            className={cn(
              'min-w-0 flex-1 truncate font-bold text-sm',
              minimal ? null : 'text-white',
              !minimal &&
                (resolvedTheme === 'dark'
                  ? 'drop-shadow-[0_1px_2px_rgba(0,0,0,0.35)]'
                  : 'drop-shadow-[0_1px_2px_rgba(15,23,42,0.22)]'),
            )}
            style={titleStyle}
          >
            {title}
          </span>
        </div>
      </div>
    </Link>
  );
});
