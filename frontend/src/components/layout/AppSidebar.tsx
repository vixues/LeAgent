import { Link, useLocation, useNavigate } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';
import {
  LayoutGrid,
  LayoutDashboard,
  MessageSquare,
  GitBranch,
  PlayCircle,
  BookOpen,
  Wrench,
  FileText,
  FolderKanban,
  Settings,
  Shield,
  ChevronLeft,
  ChevronRight,
  HelpCircle,
  Clock,
  LayoutTemplate,
  Server,
  Zap,
  Webhook,
  Radio,
  ScrollText,
} from 'lucide-react';
import { useAuthStore } from '@/stores/auth';
import { isAdminUser } from '@/lib/authUser';
import { Avatar, AvatarImage, AvatarFallback } from '../ui/Avatar';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuLabel,
} from '../ui/DropdownMenu';
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from '../ui/Tooltip';

interface NavItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  href: string;
  badge?: number;
  children?: NavItem[];
}

interface AppSidebarProps {
  collapsed?: boolean;
  onCollapsedChange?: (collapsed: boolean) => void;
}

const AppSidebar = ({ collapsed = false, onCollapsedChange }: AppSidebarProps) => {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuthStore();

  const mainNavItems: NavItem[] = [
    {
      id: 'home',
      label: t('nav.chat'),
      icon: <MessageSquare className="w-5 h-5" />,
      href: '/home',
    },
    {
      id: 'overview',
      label: t('nav.overview'),
      icon: <LayoutGrid className="w-5 h-5" />,
      href: '/overview',
    },
    {
      id: 'dashboard',
      label: t('nav.dashboard'),
      icon: <LayoutDashboard className="w-5 h-5" />,
      href: '/dashboard',
    },
    {
      id: 'workflows',
      label: t('nav.workflows'),
      icon: <GitBranch className="w-5 h-5" />,
      href: '/workflows',
    },
    {
      id: 'playground',
      label: t('nav.playground'),
      icon: <PlayCircle className="w-5 h-5" />,
      href: '/playground',
    },
    {
      id: 'templates',
      label: t('nav.templates'),
      icon: <LayoutTemplate className="w-5 h-5" />,
      href: '/templates',
    },
    {
      id: 'cron',
      label: t('nav.cron'),
      icon: <Clock className="w-5 h-5" />,
      href: '/cron',
    },
  ];

  const resourceNavItems: NavItem[] = [
    {
      id: 'knowledge',
      label: t('nav.knowledge'),
      icon: <BookOpen className="w-5 h-5" />,
      href: '/knowledge',
    },
    {
      id: 'folders',
      label: t('nav.folders'),
      icon: <FolderKanban className="w-5 h-5" />,
      href: '/folders',
    },
    {
      id: 'tools',
      label: t('nav.tools'),
      icon: <Wrench className="w-5 h-5" />,
      href: '/tools',
    },
    {
      id: 'mcp',
      label: t('nav.mcp'),
      icon: <Server className="w-5 h-5" />,
      href: '/mcp',
    },
    {
      id: 'rules',
      label: t('nav.rules'),
      icon: <FileText className="w-5 h-5" />,
      href: '/rules',
    },
    {
      id: 'skills',
      label: t('nav.skills'),
      icon: <Zap className="w-5 h-5" />,
      href: '/skills',
    },
    {
      id: 'webhooks',
      label: t('nav.webhooks'),
      icon: <Webhook className="w-5 h-5" />,
      href: '/webhooks',
    },
    {
      id: 'channels',
      label: t('nav.channels'),
      icon: <Radio className="w-5 h-5" />,
      href: '/channels',
    },
  ];

  const bottomNavItems: NavItem[] = [
    {
      id: 'docs',
      label: t('nav.docs'),
      icon: <ScrollText className="w-5 h-5" />,
      href: '/docs',
    },
    {
      id: 'settings',
      label: t('nav.settings'),
      icon: <Settings className="w-5 h-5" />,
      href: '/settings',
    },
  ];

  if (isAdminUser(user ?? undefined)) {
    bottomNavItems.unshift({
      id: 'admin',
      label: t('nav.admin'),
      icon: <Shield className="w-5 h-5" />,
      href: '/admin',
    });
  }

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
    return location.pathname.startsWith(href);
  };

  const NavLink = ({ item }: { item: NavItem }) => {
    const active = isActive(item.href);

    const linkContent = (
      <Link
        to={item.href}
        className={cn(
          'flex items-center gap-3 px-3 py-2.5 rounded-lg transition-[color,background-color,border-color,box-shadow,opacity,transform] duration-200',
          active
            ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300'
            : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-white',
          collapsed && 'justify-center px-2'
        )}
      >
        <span className="flex-shrink-0">{item.icon}</span>
        {!collapsed && (
          <>
            <span className="flex-1 text-sm font-medium">{item.label}</span>
            {item.badge !== undefined && item.badge > 0 && (
              <span
                className={cn(
                  'px-1.5 py-0.5 text-xs font-medium rounded-full',
                  active
                    ? 'bg-primary-200 dark:bg-primary-800 text-primary-800 dark:text-primary-200'
                    : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
                )}
              >
                {item.badge}
              </span>
            )}
          </>
        )}
      </Link>
    );

    if (collapsed) {
      return (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>{linkContent}</TooltipTrigger>
            <TooltipContent side="right">{item.label}</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      );
    }

    return linkContent;
  };

  return (
    <aside
      className={cn(
        'fixed left-0 top-0 z-40 h-screen flex flex-col',
        'bg-surface',
        'border-r border-gray-200 dark:border-gray-700',
        'transition-[color,background-color,border-color,box-shadow,opacity,transform] duration-300',
        collapsed ? 'w-16' : 'w-64'
      )}
    >
      <div
        className={cn(
          'flex items-center h-16 px-4',
          'border-b border-gray-200 dark:border-gray-700',
          collapsed ? 'justify-center' : 'justify-between'
        )}
      >
        {!collapsed && (
          <Link to="/home" className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary-500 to-primary-700 flex items-center justify-center">
              <span className="text-white font-bold text-lg">W</span>
            </div>
            <span className="font-bold text-lg text-gray-900 dark:text-white">
              LeAgent
            </span>
          </Link>
        )}
        {collapsed && (
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary-500 to-primary-700 flex items-center justify-center">
            <span className="text-white font-bold text-lg">W</span>
          </div>
        )}
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4">
        <div className="space-y-1">
          {mainNavItems.map((item) => (
            <NavLink key={item.id} item={item} />
          ))}
        </div>

        <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
          {!collapsed && (
            <p className="px-3 mb-2 text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider">
              {t('nav.resources')}
            </p>
          )}
          <div className="space-y-1">
            {resourceNavItems.map((item) => (
              <NavLink key={item.id} item={item} />
            ))}
          </div>
        </div>

        <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
          <div className="space-y-1">
            {bottomNavItems.map((item) => (
              <NavLink key={item.id} item={item} />
            ))}
          </div>
        </div>
      </nav>

      <div className="border-t border-gray-200 dark:border-gray-700 p-3">
        <DropdownMenu fullWidth>
          <DropdownMenuTrigger
            className={cn(
              'w-full flex items-center gap-3 p-2 rounded-lg',
              'hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors',
              collapsed && 'justify-center'
            )}
          >
            <Avatar size="sm">
              <AvatarImage src={user?.avatar ?? undefined} alt={user?.username} />
              <AvatarFallback>
                {user?.username?.charAt(0).toUpperCase() || 'U'}
              </AvatarFallback>
            </Avatar>
            {!collapsed && (
              <div className="flex-1 text-left min-w-0">
                <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                  {user?.username || t('nav.guest')}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                  {user?.email}
                </p>
              </div>
            )}
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel>{t('nav.account')}</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => navigate('/settings')}>
              <Settings className="w-4 h-4 mr-2" />
              {t('nav.settings')}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => navigate('/docs')}>
              <HelpCircle className="w-4 h-4 mr-2" />
              {t('nav.help')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <button
        type="button"
        onClick={() => onCollapsedChange?.(!collapsed)}
        className={cn(
          'absolute -right-3 top-20 z-50',
          'w-6 h-6 rounded-full flex items-center justify-center',
          'bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700',
          'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200',
          'shadow-sm hover:shadow transition-[color,background-color,border-color,box-shadow,opacity,transform]'
        )}
      >
        {collapsed ? (
          <ChevronRight className="w-4 h-4" />
        ) : (
          <ChevronLeft className="w-4 h-4" />
        )}
      </button>
    </aside>
  );
};

export { AppSidebar };
