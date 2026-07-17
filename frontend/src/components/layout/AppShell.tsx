import { lazy, useCallback, useState, useEffect, Suspense } from 'react';
import { Outlet } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { useLayoutStore } from '@/stores/layout';
import { useMobile } from '@/hooks/useMobile';
import { NavRail } from './NavRail';
import { NAV_RAIL_FLOAT_CLASSES } from './navRailLayout';
import { WorkPanel } from './WorkPanel';
import { RoutePlaceholder } from '@/components/common/RoutePlaceholder';
import { usePrewarmRoutes } from '@/routes/lazyPages';
import { useDesktop } from '@/hooks/useDesktop';

const MAIN_CONTENT_ID = 'main-content';

const DesktopTitleBar = lazy(() =>
  import('./TitleBar').then((module) => ({ default: module.TitleBar }))
);

export function AppShell() {
  const { t } = useTranslation();
  const { sidebarCollapsed, setSidebarCollapsed } = useLayoutStore();
  const { isMobile, isTablet } = useMobile();
  const { isDesktop } = useDesktop();
  const [mobileOpen, setMobileOpen] = useState(false);

  usePrewarmRoutes();

  useEffect(() => {
    if (isTablet && !isMobile) {
      setSidebarCollapsed(true);
    }
    if (!isMobile) {
      setMobileOpen(false);
    }
  }, [isMobile, isTablet, setSidebarCollapsed]);

  // Esc closes the mobile drawer — standard professional dismissal affordance.
  useEffect(() => {
    if (!isMobile || !mobileOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMobileOpen(false);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isMobile, mobileOpen]);

  // Skip-link target: move focus into the content region without a visible jump.
  const focusMainContent = useCallback((event: React.MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault();
    const el = document.getElementById(MAIN_CONTENT_ID);
    if (el) {
      el.focus({ preventScroll: true });
      el.scrollIntoView({ block: 'nearest' });
    }
  }, []);

  return (
    <div className={cn('flex h-screen overflow-hidden bg-background', isDesktop && 'flex-col')}>
      {/* Accessibility: keyboard users can jump straight past the nav rail. */}
      <a
        href={`#${MAIN_CONTENT_ID}`}
        onClick={focusMainContent}
        className={cn(
          'sr-only focus:not-sr-only',
          'focus:fixed focus:left-3 focus:top-[calc(var(--titlebar-height,0px)+0.75rem)] focus:z-[100]',
          'focus:rounded-lg focus:bg-primary-600 focus:px-4 focus:py-2',
          'focus:text-sm focus:font-medium focus:text-white focus:shadow-lg',
          'focus:outline-none focus:ring-2 focus:ring-primary-400/60'
        )}
      >
        {t('nav.skipToContent')}
      </a>

      {/* Load Electron chrome only inside the desktop shell so web startup stays unchanged. */}
      {isDesktop && (
        <Suspense fallback={null}>
          <DesktopTitleBar />
        </Suspense>
      )}
      <div className="relative flex min-h-0 flex-1 overflow-hidden">
        {/* Reserve horizontal space so main content does not sit under the fixed floating rail */}
        {!isMobile && (
          <div
            className={cn(
              // Animate in lockstep with the rail (same duration/easing) so the
              // content edge tracks the floating rail exactly — no gap on expand,
              // no overlap on collapse. Kept in sync with NavRail's transition.
              'flex-shrink-0 transition-[width] duration-200 ease-[cubic-bezier(0.4,0,0.2,1)] motion-reduce:transition-none',
              sidebarCollapsed
                ? NAV_RAIL_FLOAT_CLASSES.spacerCollapsed
                : NAV_RAIL_FLOAT_CLASSES.spacerExpanded
            )}
            aria-hidden
          />
        )}
        <NavRail
          collapsed={sidebarCollapsed}
          onCollapsedChange={setSidebarCollapsed}
          isMobile={isMobile}
          mobileOpen={mobileOpen}
          onMobileClose={() => setMobileOpen(false)}
        />
        {/*
          `flex flex-col` is load-bearing here: WorkPanel uses `flex-1` + an
          inner `overflow-y-auto` scroller to own the single page-level scroll
          container. If this wrapper is a plain block, WorkPanel's `flex-1`
          resolves to `0` of available space, <main> collapses to content
          height, the inner `overflow-y-auto` div stops overflowing, and the
          wrapper's `overflow-hidden` silently clips everything below the
          fold — which manifests as "Settings/Templates pages can't scroll".
        */}
        <div
          id={MAIN_CONTENT_ID}
          tabIndex={-1}
          aria-label={t('nav.skipToContent')}
          className="relative z-10 flex flex-1 flex-col min-h-0 min-w-0 overflow-hidden outline-none"
        >
          <WorkPanel
            onMobileMenuOpen={() => setMobileOpen(true)}
            isMobile={isMobile}
          >
            {/*
              Inner Suspense boundary so ONLY the page content re-suspends
              while a lazy chunk is being fetched — the NavRail, WorkPanel
              chrome, and any mounted chat history stay in place, which makes
              page transitions feel instant (no full-screen flash).
            */}
            <Suspense fallback={<RoutePlaceholder />}>
              <Outlet />
            </Suspense>
          </WorkPanel>
        </div>
      </div>
    </div>
  );
}
