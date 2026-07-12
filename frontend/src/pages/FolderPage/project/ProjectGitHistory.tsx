/**
 * Slide-over or inline history panel for a single file (or the whole project).
 *
 * Lists commits via :func:`useProjectGitLog`. When the user clicks a
 * row we load the file blob at that commit and the unified diff for
 * the same commit, rendering the diff with a tiny custom +/- line
 * styler so we don't pull in a diff-viewer dependency.
 */
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { GitCommit as GitCommitIcon, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button, Sheet, SheetContent } from '@/components/ui';
import {
  useProjectGitDiff,
  useProjectGitLog,
  useProjectGitShow,
} from '@/hooks/useProjectFolder';

interface ProjectGitHistoryProps {
  folderId: string;
  filePath: string | null;
  /** Sheet slide-over (default) vs embedded Git-tab body. */
  variant?: 'sheet' | 'inline';
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export default function ProjectGitHistory({
  folderId,
  filePath,
  variant = 'sheet',
  open = false,
  onOpenChange,
}: ProjectGitHistoryProps) {
  const { t } = useTranslation();
  const [activeCommit, setActiveCommit] = useState<string | null>(null);
  const enabled = variant === 'inline' || open;

  const { data: commits, isLoading, isError, error } = useProjectGitLog(folderId, {
    path: filePath ?? undefined,
    limit: 80,
    enabled,
  });

  const { data: blob } = useProjectGitShow(
    folderId,
    activeCommit,
    filePath,
    Boolean(activeCommit && filePath),
  );

  const { data: diff } = useProjectGitDiff(folderId, {
    commit: activeCommit,
    path: filePath ?? undefined,
    enabled: Boolean(activeCommit),
  });

  const body = (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center gap-2 border-b border-border px-4 py-3">
        <GitCommitIcon className="h-4 w-4 text-muted-foreground" />
        <h3 className="text-sm font-medium">
          {filePath
            ? t('folders.project.history.titleFile', {
                defaultValue: 'History · {{path}}',
                path: filePath,
              })
            : t('folders.project.history.title', { defaultValue: 'History' })}
        </h3>
        {variant === 'sheet' ? (
          <Button
            variant="ghost"
            size="icon"
            className="ml-auto"
            onClick={() => onOpenChange?.(false)}
            aria-label={t('common.close')}
          >
            <X className="h-4 w-4" />
          </Button>
        ) : null}
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 grid-rows-[auto_1fr] lg:grid-cols-[260px_1fr]">
        <div className="max-h-[40vh] overflow-auto border-b border-border lg:max-h-none lg:border-b-0 lg:border-r">
          {isLoading && (
            <div className="p-3 text-xs text-muted-foreground">{t('common.loading')}</div>
          )}
          {isError && (
            <div className="whitespace-pre-wrap p-3 text-xs text-destructive">
              {(error as Error)?.message ?? 'Failed to load history'}
            </div>
          )}
          {commits && commits.length === 0 && (
            <div className="p-3 text-xs text-muted-foreground">
              {t('folders.project.history.empty', {
                defaultValue: 'No commits found for this path.',
              })}
            </div>
          )}
          {commits?.map((c) => (
            <button
              key={c.commit}
              type="button"
              onClick={() => setActiveCommit(c.commit)}
              className={cn(
                'w-full border-b border-border/60 px-3 py-2 text-left text-xs transition-colors hover:bg-surface-sunken/60',
                activeCommit === c.commit && 'bg-primary/5',
              )}
            >
              <div className="flex items-center gap-2">
                <span className="font-mono text-[10px] text-muted-foreground">
                  {c.short}
                </span>
                <span className="ml-auto text-[10px] text-muted-foreground">
                  {c.date_iso.slice(0, 10)}
                </span>
              </div>
              <div className="mt-1 line-clamp-2">{c.summary}</div>
              <div className="mt-1 truncate text-[10px] text-muted-foreground">
                {c.author_name}
              </div>
            </button>
          ))}
        </div>

        <div className="overflow-auto p-3">
          {!activeCommit && (
            <div className="text-xs text-muted-foreground">
              {t('folders.project.history.pickCommit', {
                defaultValue: 'Select a commit to view its diff and contents.',
              })}
            </div>
          )}
          {activeCommit && (
            <div className="space-y-4">
              <section>
                <h4 className="mb-1 text-xs font-medium text-muted-foreground">
                  {t('folders.project.history.diff', { defaultValue: 'Diff' })}
                </h4>
                <DiffPane raw={diff?.diff ?? ''} />
              </section>
              {filePath && blob && (
                <section>
                  <h4 className="mb-1 text-xs font-medium text-muted-foreground">
                    {t('folders.project.history.atCommit', {
                      defaultValue: 'File at {{commit}}',
                      commit: activeCommit.slice(0, 7),
                    })}
                  </h4>
                  <pre className="max-h-[40vh] overflow-auto whitespace-pre rounded bg-surface-sunken/50 p-2 font-mono text-[11px]">
                    {blob.content}
                  </pre>
                </section>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );

  if (variant === 'inline') {
    return <div className="flex h-full min-h-0 flex-col">{body}</div>;
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange} side="right">
      <SheetContent className="w-full p-0 sm:max-w-2xl" showCloseButton={false}>
        {body}
      </SheetContent>
    </Sheet>
  );
}

interface DiffPaneProps {
  raw: string;
}

/**
 * Minimal +/- line styler for unified diffs. We deliberately avoid
 * pulling in a diff-viewer library — for the read-only history pane
 * a colored ``<pre>`` is enough and stays consistent with the rest
 * of the UI's typography.
 */
function DiffPane({ raw }: DiffPaneProps) {
  if (!raw.trim()) {
    return (
      <div className="text-xs italic text-muted-foreground">
        (no diff)
      </div>
    );
  }
  const lines = raw.split('\n');
  return (
    <pre className="max-h-[60vh] overflow-auto rounded bg-surface-sunken/40 p-2 font-mono text-[11px] leading-snug">
      {lines.map((line, idx) => {
        let cls = '';
        if (line.startsWith('+++') || line.startsWith('---')) {
          cls = 'text-muted-foreground';
        } else if (line.startsWith('@@')) {
          cls = 'text-primary';
        } else if (line.startsWith('+')) {
          cls = 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10';
        } else if (line.startsWith('-')) {
          cls = 'text-red-600 dark:text-red-400 bg-red-500/10';
        }
        return (
          <span key={idx} className={cn('block', cls)}>
            {line || ' '}
          </span>
        );
      })}
    </pre>
  );
}
