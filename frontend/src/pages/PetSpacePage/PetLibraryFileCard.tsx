import { ExternalLink, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { KeyboardEvent, MouseEvent } from 'react';
import type { PetProjectFileRow } from '@/api/petSpace';
import { cn } from '@/lib/utils';
import { FileThumb } from './PetSpaceFileThumb';

type PetLibraryFileCardBase = {
  row: PetProjectFileRow;
  deleteDisabled: boolean;
  onDelete: () => void;
  /** Narrower card + smaller thumb (e.g. customize appearance picker). */
  compact?: boolean;
};

export type PetLibraryFileCardProps =
  | (PetLibraryFileCardBase & { mode?: 'library'; downloadHref: string })
  | (PetLibraryFileCardBase & {
      mode: 'appearance';
      canPickAppearance: boolean;
      isCurrentAppearance: boolean;
      setAppearanceDisabled: boolean;
      onSetAppearance: () => void;
    });

function formatPetFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 KB';
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function DeleteCornerButton({
  compact,
  disabled,
  title,
  onClick,
}: {
  compact?: boolean;
  disabled: boolean;
  title: string;
  onClick: (e: MouseEvent) => void;
}) {
  return (
    <button
      type="button"
      data-pet-card-delete
      className={cn(
        compact ? 'right-0.5 top-0.5 z-20 p-px' : 'right-1 top-1 z-20 p-0.5',
        'absolute inline-flex rounded-sm',
        'text-foreground/65 transition-[opacity,color] duration-150',
        'hover:text-red-600 dark:hover:text-red-400',
        'opacity-0 pointer-events-none',
        '[@media(hover:none)]:opacity-100 [@media(hover:none)]:pointer-events-auto',
        'group-hover:pointer-events-auto group-hover:opacity-100',
        'group-focus-within:pointer-events-auto group-focus-within:opacity-100',
        'disabled:pointer-events-none disabled:opacity-40',
      )}
      title={title}
      aria-label={title}
      disabled={disabled}
      onClick={onClick}
    >
      <X className={compact ? 'h-3 w-3' : 'h-3.5 w-3.5'} strokeWidth={2.25} aria-hidden />
    </button>
  );
}

/** Pet Space asset card: library (open + delete) or appearance (click card to set + delete). */
export function PetLibraryFileCard(props: PetLibraryFileCardProps) {
  const { t } = useTranslation();
  const compact = props.compact ?? false;
  const isAppearance = props.mode === 'appearance';

  const appearanceInteractive =
    isAppearance && props.canPickAppearance && !props.setAppearanceDisabled;

  const handleAppearanceCardClick = () => {
    if (!isAppearance) return;
    if (!props.canPickAppearance || props.setAppearanceDisabled) return;
    if (props.isCurrentAppearance) return;
    props.onSetAppearance();
  };

  const handleAppearanceCardKeyDown = (e: KeyboardEvent<HTMLLIElement>) => {
    if (!appearanceInteractive) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      if (isAppearance && props.isCurrentAppearance) return;
      props.onSetAppearance();
    }
  };

  return (
    <li
      className={cn(
        'group flex min-w-0 flex-col overflow-hidden border border-border-subtle bg-surface-sunken/30',
        compact ? 'rounded-lg' : 'rounded-xl',
        /* Appearance picker: same width as compact thumb (h-24 w-24), centered in grid cell */
        compact && isAppearance && 'box-border w-24 max-w-full shrink-0 justify-self-center',
        appearanceInteractive && 'cursor-pointer',
        isAppearance && props.isCurrentAppearance && 'ring-2 ring-primary-500/35 ring-offset-2 ring-offset-background',
      )}
      onClick={
        isAppearance
          ? (e) => {
              if ((e.target as HTMLElement).closest('[data-pet-card-delete]')) return;
              handleAppearanceCardClick();
            }
          : undefined
      }
      onKeyDown={isAppearance ? handleAppearanceCardKeyDown : undefined}
      tabIndex={appearanceInteractive ? 0 : undefined}
      role={appearanceInteractive ? 'button' : undefined}
      aria-label={
        isAppearance && props.canPickAppearance
          ? props.isCurrentAppearance
            ? `${props.row.original_name} — ${t('petSpace.appearanceCurrent')}`
            : `${props.row.original_name} — ${t('petSpace.setAppearance')}`
          : undefined
      }
    >
      <div className="relative">
        <FileThumb
          row={props.row}
          variant="card"
          cardSize={compact ? 'compact' : 'default'}
        />

        {isAppearance && props.canPickAppearance ? (
          <div
            className={cn(
              'pointer-events-none absolute inset-x-0 top-0 z-[8]',
              'bg-gradient-to-b from-background/95 via-background/75 to-transparent px-1 pb-8 pt-1',
              'text-center text-[11px] font-semibold leading-tight tracking-tight text-foreground shadow-sm',
              'opacity-0 transition-opacity duration-150',
              /* Hover-capable: hint only on hover / keyboard focus inside card */
              'group-hover:opacity-100 group-focus-within:opacity-100',
              /* Touch: keep label visible (no hover) */
              '[@media(hover:none)]:opacity-100',
            )}
          >
            {props.isCurrentAppearance ? t('petSpace.appearanceCurrent') : t('petSpace.setAppearance')}
          </div>
        ) : null}

        <DeleteCornerButton
          compact={compact}
          disabled={props.deleteDisabled}
          title={t('petSpace.deleteFile')}
          onClick={(e) => {
            e.stopPropagation();
            props.onDelete();
          }}
        />
      </div>

      {isAppearance ? (
        <footer
          className={cn(
            'flex min-w-0 flex-col gap-0.5 border-t border-border-subtle/60 bg-background/30',
            compact ? 'px-1 py-1' : 'px-2 py-1.5',
          )}
        >
          <p
            className={cn(
              'min-w-0 truncate font-medium leading-tight text-foreground',
              compact ? 'text-[10px]' : 'text-xs',
            )}
            title={props.row.original_name}
          >
            {props.row.original_name}
          </p>
          <span
            className={cn(
              'tabular-nums text-muted-foreground',
              compact ? 'text-[9px]' : 'text-[10px]',
            )}
          >
            {formatPetFileSize(props.row.size)}
          </span>
        </footer>
      ) : (
        <footer
          className={cn(
            'flex min-w-0 items-center gap-1 border-t border-border-subtle/60 bg-background/30',
            compact ? 'px-1.5 py-1' : 'px-2 py-1.5',
          )}
        >
          <p
            className={cn(
              'min-w-0 flex-1 truncate font-medium leading-tight text-foreground',
              compact ? 'text-[10px]' : 'text-xs',
            )}
            title={props.row.original_name}
          >
            {props.row.original_name}
          </p>
          <span
            className={cn(
              'shrink-0 whitespace-nowrap tabular-nums text-muted-foreground',
              compact ? 'text-[9px]' : 'text-[10px]',
            )}
          >
            {formatPetFileSize(props.row.size)}
          </span>
          <a
            className="inline-flex shrink-0 rounded-md p-1 text-primary-600 hover:bg-surface-sunken dark:text-primary-400"
            href={props.downloadHref}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
          >
            <ExternalLink className={compact ? 'h-3 w-3' : 'h-3.5 w-3.5'} aria-hidden />
          </a>
        </footer>
      )}
    </li>
  );
}
