import { useMemo } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { Menu } from 'lucide-react';
import type { CSSProperties, ReactNode } from 'react';
import { BrandMascot } from '@/components/brand/BrandMascot';
import { LogoStageMobile } from '@/components/brand/LogoStage';
import { usePetAppearancePreview } from '@/hooks/usePetAppearancePreview';
import { resolvedNest } from '@/lib/petSettings';

interface WorkPanelProps {
  className?: string;
  isMobile?: boolean;
  onMobileMenuOpen?: () => void;
  /** Nested route outlet (pass `<Outlet />` from the layout route). */
  children: ReactNode;
}

const WorkPanel = ({ className, isMobile = false, onMobileMenuOpen, children }: WorkPanelProps) => {
  const { t } = useTranslation();
  const location = useLocation();
  const isHome = location.pathname === '/home' || location.pathname === '/';
  /** IDE-like pages: scroll inside panels (e.g. code, flow canvas) instead of the WorkPanel shell. */
  const isWorkflowFlowEditor =
    location.pathname === '/workflows/new' ||
    (location.pathname.startsWith('/workflows/') && !location.pathname.endsWith('/executions'));
  const isOutletScrollOwner =
    isHome ||
    location.pathname === '/coding-projects' ||
    location.pathname.startsWith('/coding-projects/') ||
    isWorkflowFlowEditor;
  const {
    previewUrl,
    motionClass,
    motionStyle,
    previewShellClass,
    reduceMotion,
    dock,
    clipMirror,
    clipObjectFit,
    appearanceLoading,
  } = usePetAppearancePreview();
  const objectFit = clipObjectFit === 'cover' ? 'object-cover' : 'object-contain';
  const nest = useMemo(() => resolvedNest(dock?.settings ?? {}), [dock?.settings]);

  return (
    <main
      className={cn(
        'relative flex-1 flex flex-col min-h-0 min-w-0 overflow-hidden',
        'bg-background',
        className
      )}
    >
      {/* Mobile header bar */}
      {isMobile && (
        <div className="flex items-center gap-3 h-14 px-4 border-b border-border flex-shrink-0">
          <button
            type="button"
            onClick={onMobileMenuOpen}
            className="p-1.5 rounded-lg text-muted-foreground hover:bg-surface-sunken transition-colors"
            aria-label={t('nav.openMobileMenu')}
          >
            <Menu className="w-5 h-5" />
          </button>
          <LogoStageMobile />
        </div>
      )}
      {/*
        Single scroll container for every non-home page.
        - `overflow-y-auto` on THIS element (not on <main>) gives us exactly one
          vertical scrollbar that respects the shell layout — no more "page can't
          scroll when content overflows" bugs.
        - `overscroll-contain` prevents scroll chaining into the AppShell, which
          kept producing rubber-band bounce on iOS Safari.
        - Home still uses `overflow-hidden` so the ChatView owns its own scroll.
      */}
      <div
        className={cn(
          'min-h-0 flex-1',
          isOutletScrollOwner
            ? /* flex flex-col is load-bearing: the inner ChatView relies on
                 `flex-1 + min-h-0` to propagate a bounded height down to its
                 scroll container. Without flex here, the inner div becomes a
                 plain block, `flex-1` no-ops, ChatView grows to content height,
                 and the surrounding `overflow-hidden` silently clips instead of
                 letting `.chat-messages-scroll` overflow — manifesting as
                 "the chat messages won't scroll with my mouse". */
              'flex flex-col overflow-hidden'
            : /* Reserve gutter when scrollbars toggle (e.g. PetSpace tabs) so layout does not shift sideways. */
              'overflow-x-hidden overflow-y-auto overscroll-contain [scrollbar-gutter:stable]'
        )}
      >
        <div
          className={cn(
            /* flex-1 + min-h-0: percentage h-full here often fails inside nested flex; this keeps the main/chat column scroll chain valid */
            isOutletScrollOwner
              ? isHome
                ? 'flex min-h-0 min-w-0 flex-1 flex-col'
                : isWorkflowFlowEditor
                  ? /* Flow editor: full-bleed like an IDE canvas; background matches WorkPanel. */
                    'flex min-h-0 min-w-0 flex-1 flex-col'
                  : /* Same bounded-height chain as home; padding matches standard pages. */
                    'flex min-h-0 min-w-0 flex-1 flex-col p-6 sm:p-8'
              : /* p-8 (32px) + responsive; flex + min-h-full so PageShell flex-1 fills the scrollport. */
                'flex min-h-0 min-h-full flex-col p-6 sm:p-8'
          )}
        >
          {/*
            Do not use key={location.pathname} here: it forced a full remount of <Outlet /> on every
            navigation, re-triggering React.lazy Suspense fallbacks and could leave the UI
            stuck if remount timing interacted badly with code-split chunks.
            <Outlet /> already swaps route elements when the URL changes.
          */}
          {children}
        </div>
      </div>

      {!isHome && (
        <Link
          to="/home"
          data-theme={nest.themeId}
          style={
            {
              '--pet-nest-accent': nest.accent,
              '--pet-nest-bg-opacity': String(nest.backgroundOpacity ?? 0.25),
            } as CSSProperties
          }
          className={cn(
            'pet-nest fixed bottom-4 right-4 z-40 flex h-12 w-12 flex-shrink-0',
            'rounded-full focus:outline-none focus:ring-2 focus:ring-primary-400/35 focus:ring-offset-2 focus:ring-offset-background',
          )}
          aria-label={t('nav.openAiAssistant')}
        >
          <div
            className={cn(
              'relative flex size-full items-center justify-center overflow-hidden rounded-full',
              'border border-border/80 bg-surface-sunken/40',
              'shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--pet-nest-accent)_18%,transparent),0_2px_10px_-4px_rgba(0,0,0,0.12)]',
              'transition-[box-shadow,colors,border-color] duration-200',
              'hover:border-primary-300/55 hover:shadow-[inset_0_0_0_1px_color-mix(in_srgb,var(--pet-nest-accent)_22%,transparent),0_4px_16px_-4px_rgba(0,0,0,0.16)] dark:hover:border-primary-700/45',
            )}
          >
            <div
              className="pet-nest__preset pointer-events-none absolute inset-0 opacity-[0.22] dark:opacity-[0.28]"
              aria-hidden
            />
            <span
              className={cn(
                'relative z-[1] flex size-full items-center justify-center rounded-[inherit] p-px',
                previewShellClass,
              )}
            >
              {previewUrl ? (
                clipMirror ? (
                  <span className="inline-block scale-x-[-1]">
                    <img
                      src={previewUrl}
                      alt=""
                      className={cn('h-9 w-9 shrink-0 rounded-lg', objectFit, motionClass)}
                      style={motionStyle}
                    />
                  </span>
                ) : (
                  <img
                    src={previewUrl}
                    alt=""
                    className={cn('h-9 w-9 shrink-0 rounded-lg', objectFit, motionClass)}
                    style={motionStyle}
                  />
                )
              ) : appearanceLoading ? (
                <span className={cn('flex h-9 w-9 items-center justify-center', motionClass)} style={motionStyle} aria-hidden />
              ) : (
                <span className={cn('flex items-center justify-center', motionClass)} style={motionStyle}>
                  <BrandMascot size="md" staticFallback={reduceMotion} aria-hidden />
                </span>
              )}
            </span>
          </div>
        </Link>
      )}
    </main>
  );
};

export { WorkPanel };
