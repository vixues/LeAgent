/**
 * Compact ``git status --porcelain`` summary above the project tree.
 *
 * Counts modified / added / deleted / untracked entries. Empty (or
 * non-repo) state collapses to a single muted line so the strip
 * never grows when nothing is going on.
 */
import { useTranslation } from 'react-i18next';
import { useProjectGitStatus, type ProjectGitStatusEntry } from '@/hooks/useProjectFolder';

interface ProjectGitStatusStripProps {
  folderId: string;
}

interface Counts {
  modified: number;
  added: number;
  deleted: number;
  untracked: number;
  renamed: number;
}

function tally(entries: ProjectGitStatusEntry[]): Counts {
  const c: Counts = { modified: 0, added: 0, deleted: 0, untracked: 0, renamed: 0 };
  for (const e of entries) {
    const code = e.status_code;
    if (code === '??') c.untracked += 1;
    else if (code.includes('M')) c.modified += 1;
    else if (code.includes('A')) c.added += 1;
    else if (code.includes('D')) c.deleted += 1;
    else if (code.includes('R')) c.renamed += 1;
  }
  return c;
}

export default function ProjectGitStatusStrip({ folderId }: ProjectGitStatusStripProps) {
  const { t } = useTranslation();
  const { data, isLoading, isError } = useProjectGitStatus(folderId);

  if (isLoading) {
    return (
      <div className="px-3 py-1 text-[11px] text-muted-foreground border-b border-border">
        {t('common.loading')}
      </div>
    );
  }
  if (isError) {
    return (
      <div className="px-3 py-1 text-[11px] text-muted-foreground border-b border-border">
        {t('folders.project.status.unavailable', {
          defaultValue: 'git status unavailable',
        })}
      </div>
    );
  }
  if (!data || data.length === 0) {
    return (
      <div className="px-3 py-1 text-[11px] text-muted-foreground border-b border-border">
        {t('folders.project.status.clean', {
          defaultValue: 'Working tree clean',
        })}
      </div>
    );
  }
  const counts = tally(data);
  return (
    <div className="px-3 py-1 text-[11px] flex flex-wrap items-center gap-3 border-b border-border bg-surface-sunken/40">
      {counts.modified > 0 && (
        <span className="text-amber-600 dark:text-amber-400">
          M {counts.modified}
        </span>
      )}
      {counts.added > 0 && (
        <span className="text-emerald-600 dark:text-emerald-400">
          A {counts.added}
        </span>
      )}
      {counts.deleted > 0 && (
        <span className="text-red-600 dark:text-red-400">
          D {counts.deleted}
        </span>
      )}
      {counts.renamed > 0 && (
        <span className="text-sky-600 dark:text-sky-400">
          R {counts.renamed}
        </span>
      )}
      {counts.untracked > 0 && (
        <span className="text-muted-foreground">
          ?? {counts.untracked}
        </span>
      )}
    </div>
  );
}
