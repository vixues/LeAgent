import { forwardRef, type HTMLAttributes, type ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { Inbox, Search, FileX, FolderOpen, Database, AlertCircle } from 'lucide-react';
import { Button } from '../ui/Button';
import { useTranslation } from 'react-i18next';

type EmptyStateType = 'default' | 'search' | 'file' | 'folder' | 'data' | 'error';

interface EmptyStateProps extends HTMLAttributes<HTMLDivElement> {
  type?: EmptyStateType;
  icon?: ReactNode;
  title?: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  secondaryAction?: {
    label: string;
    onClick: () => void;
  };
  size?: 'sm' | 'md' | 'lg';
}

const EmptyState = forwardRef<HTMLDivElement, EmptyStateProps>(
  (
    {
      className,
      type = 'default',
      icon,
      title,
      description,
      action,
      secondaryAction,
      size = 'md',
      ...props
    },
    ref
  ) => {
    const { t } = useTranslation();

    const sizes = {
      sm: {
        container: 'py-6',
        icon: 'w-8 h-8',
        title: 'text-sm',
        description: 'text-xs',
      },
      md: {
        container: 'py-12',
        icon: 'w-12 h-12',
        title: 'text-base',
        description: 'text-sm',
      },
      lg: {
        container: 'py-16',
        icon: 'w-16 h-16',
        title: 'text-lg',
        description: 'text-base',
      },
    };

    const sizeConfig = sizes[size];
    const iconSizeClass = sizeConfig.icon;

    const icons: Record<EmptyStateType, ReactNode> = {
      default: <Inbox className={iconSizeClass} />,
      search: <Search className={iconSizeClass} />,
      file: <FileX className={iconSizeClass} />,
      folder: <FolderOpen className={iconSizeClass} />,
      data: <Database className={iconSizeClass} />,
      error: <AlertCircle className={iconSizeClass} />,
    };

    const defaultTitles: Record<EmptyStateType, string> = {
      default: t('common.noData'),
      search: t('common.noSearchResults'),
      file: t('common.noFiles'),
      folder: t('common.emptyFolder'),
      data: t('common.noData'),
      error: t('errors.unknown'),
    };

    const defaultDescriptions: Record<EmptyStateType, string> = {
      default: t('common.noDataDescription'),
      search: t('common.noSearchResultsDescription'),
      file: t('common.noFilesDescription'),
      folder: t('common.emptyFolderDescription'),
      data: t('common.noDataDescription'),
      error: t('errors.unknownDescription'),
    };

    const iconElement = icon || icons[type];
    const displayTitle = title || defaultTitles[type];
    const displayDescription = description || defaultDescriptions[type];

    return (
      <div
        ref={ref}
        className={cn(
          'flex flex-col items-center justify-center text-center',
          sizeConfig.container,
          className
        )}
        {...props}
      >
        <div
          className={cn(
            'flex items-center justify-center rounded-full p-4 mb-4',
            'bg-surface-sunken text-muted-foreground-tertiary'
          )}
        >
          <div className={sizeConfig.icon}>{iconElement}</div>
        </div>
        <h3
          className={cn(
            'font-semibold text-foreground mb-1',
            sizeConfig.title
          )}
        >
          {displayTitle}
        </h3>
        <p
          className={cn(
            'text-muted-foreground max-w-sm mb-4',
            sizeConfig.description
          )}
        >
          {displayDescription}
        </p>
        {(action || secondaryAction) && (
          <div className="flex items-center gap-3">
            {action && (
              <Button onClick={action.onClick} size={size === 'lg' ? 'md' : 'sm'}>
                {action.label}
              </Button>
            )}
            {secondaryAction && (
              <Button
                variant="ghost"
                onClick={secondaryAction.onClick}
                size={size === 'lg' ? 'md' : 'sm'}
              >
                {secondaryAction.label}
              </Button>
            )}
          </div>
        )}
      </div>
    );
  }
);

EmptyState.displayName = 'EmptyState';

export { EmptyState };
