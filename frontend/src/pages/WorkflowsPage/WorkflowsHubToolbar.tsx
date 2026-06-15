import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Grid3x3, LayoutTemplate, List, RefreshCw, Search, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { PRIMARY_SOFT_CTA_CLASSNAME } from '@/components/ui/Button';
import { Input } from '@/components/ui';
import { FilterPillGroup, type FilterPillOption } from '@/components/common/FilterPillGroup';

export type HubFilterOption = FilterPillOption;

interface WorkflowsHubToolbarProps {
  search: string;
  onSearchChange: (value: string) => void;
  searchPlaceholder: string;
  filterValue: string;
  onFilterChange: (value: string) => void;
  filterOptions: HubFilterOption[];
  view: 'grid' | 'list';
  onViewChange: (view: 'grid' | 'list') => void;
  onRefresh: () => void;
  onFromTemplate: () => void;
  primaryLabel: string;
  primaryLoading?: boolean;
  primaryIcon: ReactNode;
  onPrimaryClick: () => void;
  primaryTitle?: string;
}

function ToolbarIconButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      onClick={onClick}
      className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-surface-sunken hover:text-foreground"
    >
      {children}
    </button>
  );
}

/** Shared filter/action row — compact controls aligned with TemplatesPage toolbar. */
export function WorkflowsHubToolbar({
  search,
  onSearchChange,
  searchPlaceholder,
  filterValue,
  onFilterChange,
  filterOptions,
  view,
  onViewChange,
  onRefresh,
  onFromTemplate,
  primaryLabel,
  primaryLoading = false,
  primaryIcon,
  onPrimaryClick,
  primaryTitle,
}: WorkflowsHubToolbarProps) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-wrap items-center gap-3">
      <FilterPillGroup
        value={filterValue}
        onChange={onFilterChange}
        options={filterOptions}
        aria-label={t('list.hub.filterGroupAria')}
        className="min-w-0 flex-1"
      />

      <div className="flex shrink-0 items-center gap-2 sm:ml-auto">
        <div className="relative">
          <Input
            type="text"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder={searchPlaceholder}
            leftIcon={<Search className="h-3.5 w-3.5" />}
            className="w-48 py-1.5 text-xs"
          />
          {search ? (
            <button
              type="button"
              onClick={() => onSearchChange('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground-tertiary hover:text-foreground"
              aria-label={t('common.reset')}
            >
              <X className="h-3 w-3" />
            </button>
          ) : null}
        </div>

        <div className="flex items-center rounded-lg bg-surface-sunken p-0.5">
          <button
            type="button"
            onClick={() => onViewChange('grid')}
            title={t('list.viewGrid')}
            aria-label={t('list.viewGrid')}
            className={cn(
              'rounded-md p-1.5 transition-colors',
              view === 'grid'
                ? 'bg-surface-elevated text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <Grid3x3 className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={() => onViewChange('list')}
            title={t('list.viewList')}
            aria-label={t('list.viewList')}
            className={cn(
              'rounded-md p-1.5 transition-colors',
              view === 'list'
                ? 'bg-surface-elevated text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <List className="h-3.5 w-3.5" />
          </button>
        </div>

        <ToolbarIconButton label={t('list.refresh')} onClick={onRefresh}>
          <RefreshCw className="h-3.5 w-3.5" />
        </ToolbarIconButton>
        <ToolbarIconButton label={t('list.fromTemplate')} onClick={onFromTemplate}>
          <LayoutTemplate className="h-3.5 w-3.5" />
        </ToolbarIconButton>

        <button
          type="button"
          disabled={primaryLoading}
          title={primaryTitle ?? primaryLabel}
          onClick={onPrimaryClick}
          className={cn(
            'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors',
            'focus:outline-none focus:ring-2 focus:ring-primary-500/40 focus:ring-offset-2 focus:ring-offset-background',
            'disabled:cursor-not-allowed disabled:opacity-50',
            PRIMARY_SOFT_CTA_CLASSNAME,
          )}
        >
          {primaryLoading ? (
            <RefreshCw className="h-3.5 w-3.5 animate-spin" aria-hidden />
          ) : (
            <span className="inline-flex shrink-0 items-center [&>svg]:h-3.5 [&>svg]:w-3.5">
              {primaryIcon}
            </span>
          )}
          <span className="whitespace-nowrap">{primaryLabel}</span>
        </button>
      </div>
    </div>
  );
}
