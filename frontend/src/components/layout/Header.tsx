import { type ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { useTranslation } from 'react-i18next';
import { Menu, Bell, Sun, Moon, Monitor, Globe } from 'lucide-react';
import { Button } from '../ui/Button';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuLabel,
} from '../ui/DropdownMenu';
import { useThemeStore } from '@/stores/theme';
import { SearchInput } from '../common/SearchInput';
import { changeAppLanguage } from '@/i18n';

interface HeaderProps {
  title?: string;
  actions?: ReactNode;
  showMenuButton?: boolean;
  onMenuClick?: () => void;
  showSearch?: boolean;
  onSearch?: (value: string) => void;
  className?: string;
}

const Header = ({
  title,
  actions,
  showMenuButton = false,
  onMenuClick,
  showSearch = false,
  onSearch,
  className,
}: HeaderProps) => {
  const { t, i18n } = useTranslation();
  const { theme, setTheme } = useThemeStore();

  const themeOptions = [
    { value: 'light', label: t('settings.themeLight'), icon: <Sun className="w-4 h-4" /> },
    { value: 'dark', label: t('settings.themeDark'), icon: <Moon className="w-4 h-4" /> },
    { value: 'system', label: t('settings.themeSystem'), icon: <Monitor className="w-4 h-4" /> },
  ];

  const languageOptions = [
    { value: 'zh-CN', label: t('settings.langZhCN') },
    { value: 'en-US', label: t('settings.langEnUS') },
  ];

  const resolvedUiLang = i18n.language === 'en' || i18n.language === 'en-US' ? 'en-US' : 'zh-CN';

  const currentThemeIcon = () => {
    switch (theme) {
      case 'dark':
        return <Moon className="w-5 h-5" />;
      case 'system':
        return <Monitor className="w-5 h-5" />;
      default:
        return <Sun className="w-5 h-5" />;
    }
  };

  return (
    <header
      className={cn(
        'sticky top-0 z-30 h-16 flex items-center justify-between gap-3 px-4 sm:px-6',
        'bg-surface/80 backdrop-blur-md',
        'border-b border-border',
        className
      )}
    >
      <div className="flex items-center gap-3 sm:gap-4 min-w-0 flex-1">
        {showMenuButton && (
          <Button variant="ghost" size="icon" onClick={onMenuClick} className="flex-shrink-0">
            <Menu className="w-5 h-5" />
          </Button>
        )}
        {title && (
          <h1 className="text-lg font-semibold text-foreground truncate whitespace-nowrap min-w-0" title={title}>
            {title}
          </h1>
        )}
        {showSearch && (
          <div className="hidden sm:block w-64 flex-shrink-0">
            <SearchInput
              size="sm"
              placeholder={t('common.search')}
              onSearch={onSearch}
            />
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 flex-shrink-0">
        {actions}

        <DropdownMenu>
          <DropdownMenuTrigger
            className={cn(
              'p-2 rounded-lg',
              'text-muted-foreground',
              'hover:bg-surface-sunken dark:hover:bg-surface-elevated transition-colors'
            )}
          >
            <Globe className="w-5 h-5" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>{t('settings.language')}</DropdownMenuLabel>
            <DropdownMenuSeparator />
            {languageOptions.map((option) => (
              <DropdownMenuItem
                key={option.value}
                onClick={() => void changeAppLanguage(option.value)}
                className={cn(
                  resolvedUiLang === option.value && 'bg-primary-50 dark:bg-primary-900/20'
                )}
              >
                {option.label}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <DropdownMenu>
          <DropdownMenuTrigger
            className={cn(
              'p-2 rounded-lg',
              'text-muted-foreground',
              'hover:bg-surface-sunken dark:hover:bg-surface-elevated transition-colors'
            )}
          >
            {currentThemeIcon()}
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>{t('settings.theme')}</DropdownMenuLabel>
            <DropdownMenuSeparator />
            {themeOptions.map((option) => (
              <DropdownMenuItem
                key={option.value}
                onClick={() => setTheme(option.value as 'light' | 'dark' | 'system')}
                className={cn(
                  'gap-2',
                  theme === option.value && 'bg-primary-50 dark:bg-primary-900/20'
                )}
              >
                <span className="flex-shrink-0 inline-flex items-center">{option.icon}</span>
                <span className="truncate">{option.label}</span>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <DropdownMenu>
          <DropdownMenuTrigger
            className={cn(
              'relative p-2 rounded-lg',
              'text-muted-foreground',
              'hover:bg-surface-sunken dark:hover:bg-surface-elevated transition-colors'
            )}
          >
            <Bell className="w-5 h-5" />
            <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-peach-400 rounded-full" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-80">
            <DropdownMenuLabel className="flex items-center justify-between">
              <span>{t('header.notifications')}</span>
              <button
                type="button"
                className="text-xs text-primary-600 dark:text-primary-400 hover:underline"
              >
                {t('header.markAllRead')}
              </button>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <div className="max-h-64 overflow-y-auto">
              <NotificationItem
                title={t('header.taskCompleted')}
                description={t('header.taskCompletedDesc')}
                time={t('header.notificationTime1')}
                unread
              />
              <NotificationItem
                title={t('header.newMessage')}
                description={t('header.newMessageDesc')}
                time={t('header.notificationTime2')}
                unread
              />
              <NotificationItem
                title={t('header.systemUpdate')}
                description={t('header.systemUpdateDesc')}
                time={t('header.notificationTime3')}
              />
            </div>
            <DropdownMenuSeparator />
            <div className="p-2">
              <button
                type="button"
                className="w-full text-center text-sm text-primary-600 dark:text-primary-400 hover:underline"
              >
                {t('header.viewAll')}
              </button>
            </div>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
};

interface NotificationItemProps {
  title: string;
  description: string;
  time: string;
  unread?: boolean;
}

const NotificationItem = ({ title, description, time, unread = false }: NotificationItemProps) => {
  return (
    <div
      className={cn(
        'px-4 py-3 hover:bg-surface-sunken dark:hover:bg-surface-elevated/80 cursor-pointer',
        unread && 'bg-primary-50/50 dark:bg-primary-900/10'
      )}
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            'w-2 h-2 rounded-full mt-2 flex-shrink-0',
            unread ? 'bg-primary-500' : 'bg-transparent'
          )}
        />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-foreground">{title}</p>
          <p className="text-xs text-muted-foreground truncate">{description}</p>
          <p className="text-xs text-muted-foreground-tertiary mt-1">{time}</p>
        </div>
      </div>
    </div>
  );
};

export { Header };
