import { startTransition, useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  HelpCircle,
  Monitor,
  Moon,
  Settings as SettingsIcon,
  Sun,
  Globe,
  Info as InfoIcon,
  ChevronRight,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/stores/auth';
import { useThemeStore, type ThemePreference } from '@/stores/theme';
import { changeAppLanguage } from '@/i18n';
import { Avatar, AvatarFallback, AvatarImage } from '../ui/Avatar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../ui/DropdownMenu';
import { AboutDialog } from './AboutDialog';

interface UserMenuProps {
  collapsed?: boolean;
}

export function UserMenu({ collapsed = false }: UserMenuProps) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const [aboutOpen, setAboutOpen] = useState(false);
  const { user } = useAuthStore();
  const { theme, setTheme } = useThemeStore();

  const navigateWithTransition = useCallback(
    (to: string) => {
      startTransition(() => navigate(to));
    },
    [navigate]
  );

  const themeOptions: { value: ThemePreference; label: string; Icon: React.ComponentType<{ className?: string }> }[] = [
    { value: 'light', label: t('settings.themeLight'), Icon: Sun },
    { value: 'dark', label: t('settings.themeDark'), Icon: Moon },
    { value: 'system', label: t('settings.themeSystem'), Icon: Monitor },
  ];

  const resolvedUiLang =
    i18n.language === 'en' || i18n.language === 'en-US' ? 'en-US' : 'zh-CN';

  return (
    <>
      <DropdownMenu fullWidth>
        <DropdownMenuTrigger
          className={cn(
            'group relative w-full flex items-center gap-2.5 p-2 rounded-lg',
            'hover:bg-surface-sunken dark:hover:bg-surface-elevated transition-colors',
            collapsed && 'justify-center'
          )}
          aria-label={t('nav.account')}
        >
          <span className="relative flex-shrink-0">
            <Avatar size="sm">
              <AvatarImage src={undefined} alt={user?.username} />
              <AvatarFallback>
                {user?.username?.charAt(0).toUpperCase() || 'U'}
              </AvatarFallback>
            </Avatar>
          </span>
          {!collapsed && (
            <>
              <div className="flex-1 text-left min-w-0">
                <p className="text-sm font-medium text-foreground truncate">
                  {user?.displayName || user?.username || t('nav.guest')}
                </p>
                <p className="text-xs text-muted-foreground truncate">
                  {user?.email}
                </p>
              </div>
              <ChevronRight className="w-4 h-4 text-muted-foreground-tertiary transition-transform group-data-[state=open]:rotate-90" />
            </>
          )}
        </DropdownMenuTrigger>

        <DropdownMenuContent
          align="start"
          side="top"
          sideOffset={8}
          className="w-80"
        >
          <div className="px-3 py-3 flex items-center gap-3">
            <Avatar size="md">
              <AvatarImage src={undefined} alt={user?.username} />
              <AvatarFallback>
                {user?.username?.charAt(0).toUpperCase() || 'U'}
              </AvatarFallback>
            </Avatar>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-foreground truncate">
                {user?.displayName || user?.username || t('nav.guest')}
              </p>
              <p className="text-xs text-muted-foreground truncate">
                {user?.email || ''}
              </p>
            </div>
          </div>

          <DropdownMenuSeparator />

          {/* Theme segmented control */}
          <DropdownMenuLabel className="flex items-center gap-1.5">
            <Sun className="w-3.5 h-3.5" />
            {t('settings.theme')}
          </DropdownMenuLabel>
          <div className="px-2 pb-2">
            <div
              role="radiogroup"
              aria-label={t('settings.theme')}
              className="grid grid-cols-3 gap-1 p-1 rounded-lg bg-surface-sunken dark:bg-surface-elevated"
            >
              {themeOptions.map(({ value, label, Icon }) => {
                const active = theme === value;
                return (
                  <button
                    key={value}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    onClick={() => setTheme(value)}
                    className={cn(
                      'flex items-center justify-center gap-1 px-2 py-1.5 rounded-md text-xs font-medium',
                      'transition-colors',
                      active
                        ? 'bg-surface text-foreground shadow-sm'
                        : 'text-muted-foreground hover:text-foreground'
                    )}
                  >
                    <Icon className="w-3.5 h-3.5" />
                    <span className="truncate">{label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Language segmented control */}
          <DropdownMenuLabel className="flex items-center gap-1.5">
            <Globe className="w-3.5 h-3.5" />
            {t('settings.language')}
          </DropdownMenuLabel>
          <div className="px-2 pb-2">
            <div
              role="radiogroup"
              aria-label={t('settings.language')}
              className="grid grid-cols-2 gap-1 p-1 rounded-lg bg-surface-sunken dark:bg-surface-elevated"
            >
              {[
                { value: 'zh-CN', label: t('settings.langZhCN') },
                { value: 'en-US', label: t('settings.langEnUS') },
              ].map((opt) => {
                const active = resolvedUiLang === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    onClick={() => void changeAppLanguage(opt.value)}
                    className={cn(
                      'flex items-center justify-center px-2 py-1.5 rounded-md text-xs font-medium',
                      'transition-colors',
                      active
                        ? 'bg-surface text-foreground shadow-sm'
                        : 'text-muted-foreground hover:text-foreground'
                    )}
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </div>

          <DropdownMenuSeparator />

          <DropdownMenuItem onClick={() => navigateWithTransition('/settings')}>
            <SettingsIcon className="w-4 h-4 mr-2" />
            {t('nav.settings')}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => navigateWithTransition('/docs')}>
            <HelpCircle className="w-4 h-4 mr-2" />
            {t('nav.help')}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => setAboutOpen(true)}>
            <InfoIcon className="w-4 h-4 mr-2" />
            {t('about.title')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <AboutDialog open={aboutOpen} onOpenChange={setAboutOpen} />
    </>
  );
}
