import { memo, useMemo, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';
import type { LucideIcon } from 'lucide-react';
import {
  MessageSquare,
  LayoutGrid,
  LayoutDashboard,
  GitBranch,
  PlayCircle,
  BookOpen,
  Wrench,
  FileText,
  FolderKanban,
  Settings,
  Shield,
  Clock,
  LayoutTemplate,
  Plug,
  Zap,
  Webhook,
  Radio,
  ScrollText,
} from 'lucide-react';
import { useAuthStore } from '@/stores/auth';
import { isAdminUser } from '@/lib/authUser';
import { prefetchRoute } from '@/routes/lazyPages';
import { useLayoutStore } from '@/stores/layout';
import { TooltipProvider } from '../ui/Tooltip';
import { UserMenu } from './UserMenu';
import { ChatHistoryPanel } from '@/components/chat/ChatHistoryPanel';
import { LogoStageRail } from '@/components/brand/LogoStage';
import { PetNest } from '@/components/layout/PetNest';
import { PetDockWidget } from '@/components/layout/PetDockWidget';

interface NavItem {
  id: string;
  label: string;
  icon: LucideIcon;
  href: string;
  badge?: number;
}

interface NavLinkProps {
  item: NavItem;
  collapsed: boolean;
  active: boolean;
}

/**
 * Single-structure nav row that MORPHS between expanded and collapsed instead of
 * swapping DOM. The icon is fixed and stays anchored on the left; the label and
 * badge fade + slide while the rail width animates, so every size change is
 * continuous. `min-w-0 truncate` lets the label shrink to zero smoothly as the
 * rail narrows, leaving an icon-only row at the collapsed width.
 */
const NavLink = memo(function NavLink({ item, collapsed, active }: NavLinkProps) {
  const Icon = item.icon;

  // Do not wrap Link in TooltipTrigger: our Tooltip ignores `asChild` and wraps a div around the
  // anchor, which breaks client-side navigation (React Router 7 Link) in some environments.
  return (
    <Link
      to={item.href}
      title={collapsed ? item.label : undefined}
      onMouseEnter={() => prefetchRoute(item.href)}
      onFocus={() => prefetchRoute(item.href)}
      className={cn(
        'flex items-center gap-3 rounded-lg px-3 py-2.5 transition-colors duration-150',
        active
          ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300'
          : 'text-muted-foreground hover:bg-surface-sunken dark:hover:bg-surface-elevated hover:text-foreground'
      )}
    >
      <span className="flex-shrink-0">
        <Icon className="h-5 w-5" />
      </span>
      <span
        aria-hidden={collapsed}
        className={cn(
          'min-w-0 flex-1 truncate whitespace-nowrap text-sm font-medium',
          'transition-[opacity,transform] duration-200 ease-out',
          collapsed ? 'pointer-events-none -translate-x-1 opacity-0' : 'translate-x-0 opacity-100'
        )}
      >
        {item.label}
      </span>
      {item.badge !== undefined && item.badge > 0 && (
        <span
          className={cn(
            'flex-shrink-0 rounded-full px-1.5 py-0.5 text-xs font-medium whitespace-nowrap',
            'transition-opacity duration-200 ease-out',
            collapsed ? 'pointer-events-none opacity-0' : 'opacity-100',
            active
              ? 'bg-primary-200 dark:bg-primary-800 text-primary-800 dark:text-primary-200'
              : 'bg-border-subtle dark:bg-surface-elevated text-muted-foreground'
          )}
        >
          {item.badge}
        </span>
      )}
    </Link>
  );
});

interface NavRailProps {
  collapsed?: boolean;
  onCollapsedChange?: (collapsed: boolean) => void;
  isMobile?: boolean;
  mobileOpen?: boolean;
  onMobileClose?: () => void;
}

const NavRail = ({
  collapsed = false,
  onCollapsedChange,
  isMobile = false,
  mobileOpen = false,
  onMobileClose,
}: NavRailProps) => {
  const { t } = useTranslation();
  const location = useLocation();
  const { user } = useAuthStore();
  const chatHistoryOpen = useLayoutStore((s) => s.chatHistoryOpen);
  const setChatHistoryOpen = useLayoutStore((s) => s.setChatHistoryOpen);
  // Auto-close drawer on route change
  useEffect(() => {
    if (isMobile && mobileOpen) {
      onMobileClose?.();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  const homeNavItem = useMemo<NavItem>(
    () => ({ id: 'home', label: t('nav.chat'), icon: MessageSquare, href: '/home' }),
    [t],
  );

  const mainNavItems = useMemo<NavItem[]>(() => [
    { id: 'overview', label: t('nav.overview'), icon: LayoutGrid, href: '/overview' },
    { id: 'dashboard', label: t('nav.dashboard'), icon: LayoutDashboard, href: '/dashboard' },
    { id: 'workflows', label: t('nav.workflows'), icon: GitBranch, href: '/workflows' },
    { id: 'playground', label: t('nav.playground'), icon: PlayCircle, href: '/playground' },
    { id: 'templates', label: t('nav.templates'), icon: LayoutTemplate, href: '/templates' },
    { id: 'cron', label: t('nav.cron'), icon: Clock, href: '/cron' },
  ], [t]);

  const resourceNavItems = useMemo<NavItem[]>(() => [
    { id: 'knowledge', label: t('nav.knowledge'), icon: BookOpen, href: '/knowledge' },
    { id: 'folders', label: t('nav.folders'), icon: FolderKanban, href: '/folders' },
    { id: 'tools', label: t('nav.tools'), icon: Wrench, href: '/tools' },
    { id: 'mcp', label: t('nav.mcp'), icon: Plug, href: '/mcp' },
    { id: 'skills', label: t('nav.skills'), icon: Zap, href: '/skills' },
    { id: 'rules', label: t('nav.rules'), icon: FileText, href: '/rules' },
    { id: 'webhooks', label: t('nav.webhooks'), icon: Webhook, href: '/webhooks' },
    { id: 'channels', label: t('nav.channels'), icon: Radio, href: '/channels' },
  ], [t]);

  const bottomNavItems = useMemo<NavItem[]>(() => {
    const items: NavItem[] = [
      { id: 'docs', label: t('nav.docs'), icon: ScrollText, href: '/docs' },
      { id: 'settings', label: t('nav.settings'), icon: Settings, href: '/settings' },
    ];
    if (isAdminUser(user ?? undefined)) {
      items.unshift({ id: 'admin', label: t('nav.admin'), icon: Shield, href: '/admin' });
    }
    return items;
  }, [t, user]);

  const isActive = (href: string) => {
    if (href === '/home') {
      return location.pathname === '/home' || location.pathname === '/';
    }
    if (href === '/overview') {
      return location.pathname === '/overview';
    }
    if (href === '/docs') {
      return location.pathname === '/docs';
    }
    if (href === '/pet-space') {
      return location.pathname.startsWith('/pet-space');
    }
    return location.pathname.startsWith(href);
  };

  const homeActive = isActive('/home');
  const petSpaceActive = isActive('/pet-space');
  // Mobile drawer is always the expanded rail (labels + section headers visible).
  // Do not inherit desktop/tablet `sidebarCollapsed` — tablet forces collapse, which
  // would leave a w-64 drawer with opacity-0 labels.
  const railCollapsed = isMobile ? false : collapsed;

  // On mobile, don't render sidebar at all when drawer is closed
  if (isMobile && !mobileOpen) return null;

  return (
    <TooltipProvider delayDuration={200}>
      {/* Mobile backdrop */}
      {isMobile && mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm"
          aria-hidden="true"
          onClick={onMobileClose}
        />
      )}
      <aside
        className={cn(
          'flex flex-col overflow-hidden',
          'bg-surface',
          'border border-border',
          'rounded-2xl',
          isMobile
            ? 'fixed left-2 top-[calc(var(--titlebar-height,0px)_+_10px)] bottom-2 z-50 w-64 max-w-[min(16rem,calc(100vw-1rem))] shadow-2xl ring-1 ring-black/10 dark:ring-white/10'
            : cn(
                'fixed left-2 top-[calc(var(--titlebar-height,0px)_+_10px)] bottom-2 z-20 transition-[width] duration-200 ease-[cubic-bezier(0.4,0,0.2,1)] [contain:layout_paint] motion-reduce:transition-none',
                'shadow-soft ring-1 ring-black/[0.06] dark:ring-white/[0.08]',
                railCollapsed ? 'w-16' : 'w-64'
              )
        )}
      >
        {/*
          Content follows the rail's animating width so every child resizes
          continuously (icons stay put, labels truncate + fade in sync). The
          `aside` owns `[contain:layout_paint]`, so this per-frame reflow stays
          scoped to the rail and never touches the page.
        */}
        <div className="flex h-full min-h-0 w-full min-w-0 flex-col">
        <LogoStageRail
          collapsed={railCollapsed}
          isMobile={isMobile}
          onCollapsedChange={onCollapsedChange}
          onMobileClose={onMobileClose}
        />

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-1 no-scrollbar min-h-0">
          <div className="space-y-0.5">
            {/*
              Home/chat-assistant row uses the SAME morphing shape as NavLink so
              it resizes continuously with the rail. The chat-history disclosure
              only mounts when expanded + open.
            */}
            <div className="space-y-1">
              <Link
                id="nav-chat-assistant"
                to="/home"
                onMouseEnter={() => prefetchRoute('/home')}
                onFocus={() => prefetchRoute('/home')}
                onClick={(e) => {
                  if (!railCollapsed && homeActive) {
                    e.preventDefault();
                    setChatHistoryOpen(!chatHistoryOpen);
                  }
                }}
                aria-expanded={!railCollapsed && homeActive ? chatHistoryOpen : undefined}
                aria-controls={!railCollapsed && homeActive && chatHistoryOpen ? 'nav-chat-history' : undefined}
                className={cn(
                  'flex items-center gap-3 rounded-lg border border-transparent px-3 py-2.5 transition-colors duration-150',
                  homeActive
                    ? 'border-primary-200/60 dark:border-primary-800/50 bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300'
                    : 'text-muted-foreground hover:bg-surface-sunken dark:hover:bg-surface-elevated hover:text-foreground',
                )}
                title={
                  railCollapsed
                    ? homeNavItem.label
                    : homeActive
                      ? t('chat.toggleHistorySectionAria', {
                          defaultValue: 'Show or hide chat history',
                        })
                      : undefined
                }
              >
                <span className="flex-shrink-0">
                  <MessageSquare className="h-5 w-5" />
                </span>
                <span
                  aria-hidden={railCollapsed}
                  className={cn(
                    'min-w-0 flex-1 truncate whitespace-nowrap text-sm font-medium',
                    'transition-[opacity,transform] duration-200 ease-out',
                    railCollapsed ? 'pointer-events-none -translate-x-1 opacity-0' : 'translate-x-0 opacity-100',
                  )}
                >
                  {homeNavItem.label}
                </span>
              </Link>
              {!railCollapsed && chatHistoryOpen && (
                <div
                  id="nav-chat-history"
                  role="region"
                  aria-labelledby="nav-chat-assistant"
                  className="flex max-h-[min(40vh,320px)] min-h-0 flex-col overflow-hidden rounded-lg border border-border-subtle bg-surface-sunken/50 dark:bg-surface-elevated/30"
                >
                  <ChatHistoryPanel variant="nav" />
                </div>
              )}
            </div>
            {mainNavItems.map((item) => (
              <NavLink key={item.id} item={item} collapsed={railCollapsed} active={isActive(item.href)} />
            ))}
          </div>

          <div className="mt-4 pt-4 border-t border-border">
            <p
              aria-hidden={railCollapsed}
              className={cn(
                'overflow-hidden px-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground-tertiary',
                'transition-[max-height,opacity,margin] duration-200 ease-out',
                railCollapsed ? 'mb-0 max-h-0 opacity-0' : 'mb-1.5 max-h-5 opacity-100',
              )}
            >
              {t('nav.resources')}
            </p>
            <div className="space-y-0.5">
              {resourceNavItems.map((item) => (
                <NavLink key={item.id} item={item} collapsed={railCollapsed} active={isActive(item.href)} />
              ))}
            </div>
          </div>

          <div className="mt-4 pt-4 border-t border-border">
            <div className="space-y-0.5">
              {bottomNavItems.map((item) => (
                <NavLink key={item.id} item={item} collapsed={railCollapsed} active={isActive(item.href)} />
              ))}
            </div>
          </div>
        </nav>

        {/* Pet dock + user menu */}
        <div className="flex-shrink-0 space-y-2 overflow-visible p-2">
          <div onMouseEnter={() => prefetchRoute('/pet-space')} onFocus={() => prefetchRoute('/pet-space')}>
            <PetNest active={petSpaceActive} compact={railCollapsed}>
              <PetDockWidget collapsed={railCollapsed} active={petSpaceActive} />
            </PetNest>
          </div>
          <UserMenu collapsed={railCollapsed} />
        </div>
        </div>

      </aside>
    </TooltipProvider>
  );
};

export { NavRail };
