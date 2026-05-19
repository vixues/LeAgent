import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronRight, ClipboardCopy, Copy, FileText, Folder, Loader2 } from 'lucide-react';
import { CodeBlock } from '@/components/common/CodeBlock';
import { Badge, Button } from '@/components/ui';
import { cn } from '@/lib/utils';
import {
  useCodingProjectFile,
  useCodingProjectTree,
  type WorkspaceTreeNode,
} from '@/hooks/useCodingProjectWorkspace';
import { extToLanguage } from '@/pages/FolderPage/project/extToLanguage';

interface TreeEntryProps {
  node: WorkspaceTreeNode;
  depth: number;
  selectedPath: string | null;
  onSelectFile: (path: string) => void;
}

function TreeEntry({
  node,
  depth,
  selectedPath,
  onSelectFile,
}: TreeEntryProps) {
  if (node.type === 'file') {
    const active = selectedPath === node.path;
    return (
      <button
        type="button"
        onClick={() => onSelectFile(node.path)}
        className={cn(
          'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors',
          active
            ? 'bg-primary/10 text-primary font-medium'
            : 'text-foreground hover:bg-muted/60',
        )}
      >
        <FileText className="size-3.5 shrink-0 opacity-60" aria-hidden />
        <span className="min-w-0 truncate">{node.name}</span>
      </button>
    );
  }

  const children = node.children ?? [];
  if (children.length === 0) {
    return null;
  }

  const label = node.name === '.' ? '…' : node.name;

  return (
    <details open={depth < 2} className="group">
      <summary
        className={cn(
          'flex cursor-pointer list-none items-center gap-1.5 rounded-md px-2 py-1.5 text-sm font-medium text-foreground hover:bg-muted/40',
          '[&::-webkit-details-marker]:hidden',
        )}
      >
        <ChevronRight
          className="size-3.5 shrink-0 opacity-60 transition-transform group-open:rotate-90"
          aria-hidden
        />
        <Folder className="size-3.5 shrink-0 opacity-70" aria-hidden />
        <span className="min-w-0 truncate">{label}</span>
      </summary>
      <div className="ml-1 mt-0.5 space-y-0.5 border-l border-border/70 pl-2">
        {children.map((ch) => (
          <TreeEntry
            key={ch.path || `${depth}-${ch.name}`}
            node={ch}
            depth={depth + 1}
            selectedPath={selectedPath}
            onSelectFile={onSelectFile}
          />
        ))}
      </div>
    </details>
  );
}

function FilePreview({
  projectId,
  path,
}: {
  projectId: string;
  path: string | null;
}) {
  const { t } = useTranslation();
  const { data, isLoading, error } = useCodingProjectFile(projectId, path);

  if (!path) {
    return (
      <div className="flex min-h-[12rem] flex-1 items-center justify-center p-8 text-center text-sm text-muted-foreground md:min-h-0">
        {t('codingProjects.files.chooseFile')}
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex min-h-[12rem] flex-1 items-center justify-center gap-2 p-8 text-sm text-muted-foreground md:min-h-0">
        <Loader2 className="size-4 animate-spin" aria-hidden />
        {t('common.loading')}
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-[12rem] flex-1 items-center justify-center p-6 text-sm text-rose-600 dark:text-rose-400 md:min-h-0">
        {t('codingProjects.files.fileError')}
      </div>
    );
  }

  const content = data?.content ?? '';

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex shrink-0 items-center gap-2 border-b border-border bg-surface-sunken/40 px-3 py-2">
        <span className="min-w-0 truncate font-mono text-xs text-muted-foreground" title={path}>
          {path}
        </span>
        {data?.truncated && (
          <Badge variant="warning" className="shrink-0 text-[10px]">
            {t('codingProjects.files.truncated')}
          </Badge>
        )}
        <div className="ml-auto flex items-center gap-0.5">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            aria-label={t('codingProjects.files.copyContents')}
            onClick={() => void navigator.clipboard?.writeText(content)}
          >
            <ClipboardCopy className="h-3.5 w-3.5" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            aria-label={t('folders.project.viewer.copyPath', { defaultValue: 'Copy path' })}
            onClick={() => void navigator.clipboard?.writeText(path)}
          >
            <Copy className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {data?.truncated && (
          <p className="border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-xs text-amber-800 dark:text-amber-200">
            {t('folders.project.viewer.truncatedNotice', {
              defaultValue:
                'File is too large to preview in full. Content below may be truncated.',
            })}
          </p>
        )}
        <CodeBlock
          code={content}
          language={extToLanguage(path)}
          showLineNumbers
          showLanguage={false}
          showCopyButton={false}
          className="border-0 rounded-none"
        />
      </div>
    </div>
  );
}

interface FileExplorerProps {
  projectId: string;
}

export function FileExplorer({ projectId }: FileExplorerProps) {
  const { t } = useTranslation();
  const { data, isLoading, error, refetch } = useCodingProjectTree(projectId);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);

  useEffect(() => {
    setSelectedPath(null);
  }, [projectId]);

  if (isLoading) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center gap-2 p-8 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" aria-hidden />
        {t('common.loading')}
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center p-6 text-center text-sm text-rose-600 dark:text-rose-400">
        {t('codingProjects.files.loadError')}
        <button
          type="button"
          className="ml-2 underline"
          onClick={() => refetch()}
        >
          {t('common.retry')}
        </button>
      </div>
    );
  }

  const root = data?.root;
  const children = root?.children ?? [];

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 md:grid-cols-[260px_1fr]">
      <div className="flex max-h-52 min-h-0 flex-col border-b border-border md:max-h-none md:h-full md:min-h-0 md:self-stretch md:border-b-0 md:border-r">
        <div className="shrink-0 border-b border-border px-3 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {t('codingProjects.files.treeTitle')}
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {data?.truncated && (
            <p className="mb-2 rounded-md bg-amber-500/10 px-2 py-1.5 text-[11px] text-amber-800 dark:text-amber-200">
              {t('codingProjects.files.truncated')}
            </p>
          )}
          {children.length === 0 ? (
            <p className="px-2 text-sm text-muted-foreground">
              {t('codingProjects.emptyHint')}
            </p>
          ) : (
            <div className="space-y-0.5">
              {children.map((node) => (
                <TreeEntry
                  key={node.path || node.name}
                  node={node}
                  depth={0}
                  selectedPath={selectedPath}
                  onSelectFile={setSelectedPath}
                />
              ))}
            </div>
          )}
        </div>
      </div>
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-muted/20">
        <div className="shrink-0 border-b border-border px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {t('codingProjects.files.preview')}
        </div>
        <FilePreview projectId={projectId} path={selectedPath} />
      </div>
    </div>
  );
}
