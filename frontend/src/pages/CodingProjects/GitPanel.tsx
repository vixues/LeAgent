import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { GitBranch, GitCommitHorizontal, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui';
import {
  useCodingProjectGit,
  useInvalidateCodingProjectWorkspace,
} from '@/hooks/useCodingProjectWorkspace';

interface GitPanelProps {
  projectId: string;
}

/** Map ``git status --porcelain`` XY codes to a short, localized label. */
function gitPorcelainLabel(xy: string, t: TFunction): string {
  if (xy === '??') return t('codingProjects.git.status.untracked');
  if (xy.includes('U')) return t('codingProjects.git.status.unmerged');
  if (xy.includes('R')) return t('codingProjects.git.status.renamed');
  if (xy.includes('A')) return t('codingProjects.git.status.added');
  if (xy.includes('D')) return t('codingProjects.git.status.deleted');
  if (xy.includes('M')) return t('codingProjects.git.status.modified');
  if (xy === '!!') return t('codingProjects.git.status.ignored');
  return xy.trim() || xy;
}

export function GitPanel({ projectId }: GitPanelProps) {
  const { t } = useTranslation();
  const { data, isLoading, error, isFetching } = useCodingProjectGit(projectId);
  const invalidate = useInvalidateCodingProjectWorkspace();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" aria-hidden />
        {t('common.loading', 'Loading…')}
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-3 p-6 text-center">
        <p className="text-sm text-rose-600 dark:text-rose-400">
          {t('codingProjects.git.loadError')}
        </p>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => invalidate(projectId)}
          leftIcon={<RefreshCw className="size-3.5 shrink-0" aria-hidden />}
        >
          {t('codingProjects.git.refresh')}
        </Button>
      </div>
    );
  }

  if (!data?.git_available) {
    return (
      <p className="p-6 text-sm text-muted-foreground">
        {t('codingProjects.git.noGit')}
      </p>
    );
  }

  if (!data.is_git) {
    return (
      <p className="p-6 text-sm text-muted-foreground">
        {data.error ?? t('codingProjects.git.notRepo')}
      </p>
    );
  }

  const lines = data.lines ?? [];
  const hasChanges = lines.length > 0;

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="flex flex-col gap-4 p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-foreground">
                {t('codingProjects.git.title')}
              </h3>
              <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-sm">
                <span className="flex items-center gap-2 text-muted-foreground">
                  <GitBranch className="size-4 shrink-0" aria-hidden />
                  <span className="text-foreground">
                    {t('codingProjects.git.branch')}:{' '}
                    <strong className="font-medium">{data.branch ?? '—'}</strong>
                  </span>
                </span>
                <span className="flex items-center gap-2 text-muted-foreground">
                  <GitCommitHorizontal className="size-4 shrink-0" aria-hidden />
                  <span className="font-mono text-xs text-foreground">
                    {t('codingProjects.git.commit')}: {data.head ?? data.head_full ?? '—'}
                  </span>
                </span>
              </div>
            </div>
            <Button
              variant="ghost"
              size="sm"
              disabled={isFetching}
              onClick={() => invalidate(projectId)}
              leftIcon={
                isFetching ? (
                  <Loader2 className="size-3.5 shrink-0 animate-spin" aria-hidden />
                ) : (
                  <RefreshCw className="size-3.5 shrink-0" aria-hidden />
                )
              }
            >
              {t('codingProjects.git.refresh')}
            </Button>
          </div>

          {data.error && (
            <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-900 dark:text-amber-100">
              {data.error}
            </p>
          )}

          <div>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {t('codingProjects.git.workingTree')}
            </h4>
            {!hasChanges ? (
              <p className="rounded-lg border border-border bg-muted/30 px-4 py-6 text-center text-sm text-muted-foreground">
                {t('codingProjects.git.clean')}
              </p>
            ) : (
              <ul className="max-h-[min(24rem,50vh)] overflow-auto rounded-lg border border-border">
                {lines.map((line, i) => (
                  <li
                    key={`${line.path}-${i}`}
                    className="flex gap-3 border-b border-border px-3 py-2 font-mono text-xs last:border-b-0"
                  >
                    <span
                      className="w-14 shrink-0 text-muted-foreground"
                      title={t('codingProjects.git.status.porcelainHint', { code: line.xy })}
                    >
                      {gitPorcelainLabel(line.xy, t)}
                    </span>
                    <span className="min-w-0 flex-1 break-all text-foreground">
                      {line.path}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
