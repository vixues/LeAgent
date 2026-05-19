import { useTranslation } from 'react-i18next';
import { FileText, Puzzle, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ComposerFileRef } from '@/stores/chatDraft';

interface ComposerReferenceStripProps {
  refs: ComposerFileRef[];
  onRemove: (clientId: string) => void;
  className?: string;
}

/**
 * Pending @knowledge / @skill / @file tokens — chip shell matches
 * {@link AttachmentStrip} non-image rows; knowledge entries add a small
 * ``知识库`` (or i18n) tag before the filename.
 */
export function ComposerReferenceStrip({
  refs,
  onRemove,
  className,
}: ComposerReferenceStripProps) {
  const { t } = useTranslation();

  if (refs.length === 0) return null;

  return (
    <div className={cn('px-3 pt-3 pb-1', className)}>
      <div className="flex flex-wrap gap-1.5">
        {refs.map((ref) => {
          const isKb = ref.kind === 'knowledge';
          const isSkill = ref.kind === 'skill';
          return (
            <div
              key={ref.clientId}
              className="group/ref relative flex items-center gap-1.5 rounded-lg border border-border-subtle bg-surface-sunken/60 px-2 py-1 text-xs"
              title={ref.token}
            >
              <span className="text-muted-foreground-tertiary flex-shrink-0">
                {isSkill ? (
                  <Puzzle className="w-3.5 h-3.5" aria-hidden />
                ) : (
                  <FileText className="w-3.5 h-3.5" aria-hidden />
                )}
              </span>
              {isKb && (
                <span
                  className={cn(
                    'flex-shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-semibold tracking-tight',
                    'bg-primary-50 text-primary-800',
                    'dark:bg-primary-900/35 dark:text-primary-200',
                  )}
                >
                  {t('chat.composerRefs.knowledgeBadge', { defaultValue: 'Knowledge' })}
                </span>
              )}
              {isSkill && (
                <span
                  className={cn(
                    'flex-shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-semibold tracking-tight',
                    'bg-violet-50 text-violet-900',
                    'dark:bg-violet-900/35 dark:text-violet-200',
                  )}
                >
                  {t('chat.composerRefs.skillBadge', { defaultValue: 'Skill' })}
                </span>
              )}
              <span className="max-w-[160px] truncate text-muted-foreground font-medium">
                {ref.label}
              </span>
              <button
                type="button"
                onClick={() => onRemove(ref.clientId)}
                className="p-0.5 rounded-full text-muted-foreground-tertiary hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                aria-label={t('chat.composerRefs.removeAria', {
                  name: ref.label,
                  defaultValue: `Remove reference ${ref.label}`,
                })}
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
