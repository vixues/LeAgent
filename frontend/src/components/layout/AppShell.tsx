import { useState, useEffect, Suspense } from 'react';
import { Outlet } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { useLayoutStore } from '@/stores/layout';
import { useMobile } from '@/hooks/useMobile';
import { NavRail } from './NavRail';
import { NAV_RAIL_FLOAT_CLASSES } from './navRailLayout';
import { WorkPanel } from './WorkPanel';
import { RoutePlaceholder } from '@/components/common/RoutePlaceholder';
import { DeepSeekApiKeyDialog } from '@/components/setup/DeepSeekApiKeyDialog';
import { usePrewarmRoutes } from '@/routes/lazyPages';

export function AppShell() {
  const { sidebarCollapsed, setSidebarCollapsed } = useLayoutStore();
  const { isMobile, isTablet } = useMobile();
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

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Reserve horizontal space so main content does not sit under the fixed floating rail */}
      {!isMobile && (
        <div
          className={cn(
            'flex-shrink-0 transition-[width] duration-300 ease-out',
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
      <div className="relative z-10 flex flex-1 flex-col min-h-0 min-w-0 overflow-hidden">
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
        <DeepSeekApiKeyDialog />
      </div>
    </div>
  );
}
