import { memo, useEffect, useState, useMemo, type CSSProperties } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { getLogoBackdropStyle } from '@/lib/brandingBackdrop';
import { useTheme } from '@/hooks/useTheme';
import { useBrandingStore, resolveDisplayName, type BrandFontPreset } from '@/stores/branding';
import { AppLogo } from './AppLogo';
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/Tooltip';

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
  const backdropStyle = useMemo(
    () => getLogoBackdropStyle(hour, preset, resolvedTheme),
    [hour, preset, resolvedTheme],
  );
  const brandFontStyle = brandFontStyles[fontPreset] ?? brandFontStyles.modern;

  const stageShell = 'relative w-full overflow-hidden rounded-xl ring-1 ring-black/5 dark:ring-white/10';

  const backdropLayer = (
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
  );

  if (collapsed) {
    return (
      <div className="px-2 pt-2 pb-1 flex-shrink-0 flex justify-center">
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={() => onCollapsedChange?.(false)}
              className={cn(
                stageShell,
                'flex h-12 w-12 flex-shrink-0 items-center justify-center',
                'transition-transform duration-150 hover:scale-105 active:scale-95'
              )}
              aria-label={t('nav.expandRail')}
            >
              {backdropLayer}
              <span className={cn(frostedInner, 'm-1 flex size-9 items-center justify-center p-0')}>
                <AppLogo
          src={customIcon}
          className="size-7 shadow-none drop-shadow-[0_1px_1px_rgba(0,0,0,0.28)]"
        />
              </span>
            </button>
          </TooltipTrigger>
          <TooltipContent side="right">{t('nav.expandRail')}</TooltipContent>
        </Tooltip>
      </div>
    );
  }

  const expandedBody = (
    <>
      {backdropLayer}
      <div className={cn(frostedInner, 'm-1.5 min-w-0 flex-1 gap-2 px-2.5 py-2')}>
        <AppLogo
          src={customIcon}
          className={cn(
            'size-10 shrink-0',
            resolvedTheme === 'dark'
              ? 'drop-shadow-[0_1px_2px_rgba(0,0,0,0.38)]'
              : 'drop-shadow-[0_1px_2px_rgba(15,23,42,0.28)]',
          )}
        />
        <span
          className={cn(
            'min-w-0 flex-1 truncate text-xl font-extrabold leading-snug text-white',
            resolvedTheme === 'dark'
              ? 'drop-shadow-[0_1px_2px_rgba(0,0,0,0.35)]'
              : 'drop-shadow-[0_1px_2px_rgba(15,23,42,0.22)]',
          )}
          style={brandFontStyle}
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
            'flex min-h-[60px] w-full items-stretch text-left transition-opacity duration-150 active:opacity-90'
          )}
          aria-label={title}
        >
          {expandedBody}
        </Link>
      </div>
    );
  }

  return (
    <div className="px-2 pt-2 pb-1 flex-shrink-0">
      <button
        type="button"
        onClick={() => onCollapsedChange?.(true)}
        className={cn(
          stageShell,
          'flex min-h-[60px] w-full items-stretch text-left',
          'cursor-pointer transition-transform duration-150 hover:scale-[1.01] active:scale-[0.99]'
        )}
        aria-label={t('nav.collapseRail')}
      >
        {expandedBody}
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
  const backdropStyle = useMemo(
    () => getLogoBackdropStyle(hour, preset, resolvedTheme),
    [hour, preset, resolvedTheme],
  );
  const brandFontStyle = brandFontStyles[fontPreset] ?? brandFontStyles.modern;

  return (
    <Link to="/home" className="flex min-w-0 flex-1 items-center">
      <div
        className={cn(
          'relative flex min-h-10 w-full min-w-0 overflow-hidden rounded-xl ring-1 ring-black/5 dark:ring-white/10'
        )}
      >
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
        <div className={cn(frostedInner, 'm-1 min-w-0 flex-1 gap-2 px-2 py-1.5')}>
          <AppLogo
            src={customIcon}
            className={cn(
              'size-7 shrink-0',
              resolvedTheme === 'dark'
                ? 'drop-shadow-[0_1px_2px_rgba(0,0,0,0.38)]'
                : 'drop-shadow-[0_1px_2px_rgba(15,23,42,0.28)]',
            )}
          />
          <span
            className={cn(
              'min-w-0 flex-1 truncate font-bold text-sm text-white',
              resolvedTheme === 'dark'
                ? 'drop-shadow-[0_1px_2px_rgba(0,0,0,0.35)]'
                : 'drop-shadow-[0_1px_2px_rgba(15,23,42,0.22)]',
            )}
            style={brandFontStyle}
          >
            {title}
          </span>
        </div>
      </div>
    </Link>
  );
});
