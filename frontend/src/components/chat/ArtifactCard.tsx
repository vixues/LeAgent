import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { Code, FileText, Table, GitBranch, Image, ExternalLink, Layout, Download } from 'lucide-react';
import { useArtifactStore } from '@/stores/artifact';
import type { Artifact, ArtifactType } from '@/types/artifact';
import { downloadAuthenticatedFile } from '@/lib/downloadAuthenticatedFile';

const ARTIFACT_ICONS: Record<ArtifactType, React.ReactNode> = {
  code: <Code className="w-4 h-4" />,
  file: <FileText className="w-4 h-4" />,
  workflow: <GitBranch className="w-4 h-4" />,
  table: <Table className="w-4 h-4" />,
  markdown: <FileText className="w-4 h-4" />,
  image: <Image className="w-4 h-4" />,
  html: <Layout className="w-4 h-4" />,
  react: <Layout className="w-4 h-4" />,
  mermaid: <GitBranch className="w-4 h-4" />,
};

const ARTIFACT_COLORS: Record<ArtifactType, string> = {
  code: 'text-sky-600 dark:text-sky-400 bg-sky-50 dark:bg-sky-900/20',
  file: 'text-peach-600 dark:text-peach-400 bg-peach-50 dark:bg-peach-900/20',
  workflow: 'text-sky-700 dark:text-sky-400 bg-sky-50 dark:bg-sky-900/20',
  table: 'text-mint-600 dark:text-mint-400 bg-mint-50 dark:bg-mint-900/20',
  markdown: 'text-muted-foreground bg-surface-sunken',
  image: 'text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-900/20',
  html: 'text-sky-600 dark:text-sky-400 bg-sky-50 dark:bg-sky-900/20',
  react: 'text-sky-600 dark:text-sky-400 bg-sky-50 dark:bg-sky-900/20',
  mermaid: 'text-sky-700 dark:text-sky-400 bg-sky-50 dark:bg-sky-900/20',
};

interface ArtifactCardProps {
  artifact: Artifact;
  className?: string;
}

export function ArtifactCard({ artifact, className }: ArtifactCardProps) {
  const { t } = useTranslation();
  const { openArtifact } = useArtifactStore();

  const handleOpen = () => {
    openArtifact(artifact.id);
  };

  const fileId = typeof artifact.metadata?.fileId === 'string' ? artifact.metadata.fileId : null;
  const downloadHref = fileId ? `/api/v1/files/${fileId}/download` : null;
  const handleDownload = () => {
    if (!fileId) return;
    void downloadAuthenticatedFile(fileId, artifact.title);
  };

  return (
    <div
      className={cn(
        'group flex items-center gap-3 w-full text-left',
        'rounded-xl border border-border',
        'bg-surface',
        'px-3 py-2.5 transition-[color,background-color,border-color,box-shadow,opacity,transform] duration-200',
        'hover:border-primary-300 dark:hover:border-primary-600',
        'hover:shadow-sm',
        'focus:outline-none focus:ring-2 focus:ring-primary-500/20',
        className
      )}
    >
      <div
        className={cn(
          'flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center',
          ARTIFACT_COLORS[artifact.type]
        )}
      >
        {ARTIFACT_ICONS[artifact.type]}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">
            {t(`chat.artifactTypes.${artifact.type}`)}
          </span>
          {artifact.language && (
            <span className="text-xs text-muted-foreground-tertiary">· {artifact.language}</span>
          )}
        </div>
        <p className="text-sm font-medium text-foreground truncate">
          {artifact.title}
        </p>
      </div>

      {downloadHref && (
        <button
          type="button"
          onClick={handleDownload}
          className="p-1 rounded-md text-muted-foreground-tertiary hover:text-foreground hover:bg-surface-sunken transition-colors flex-shrink-0"
          aria-label={t('knowledge.download', { defaultValue: 'Download' })}
          title={t('knowledge.download', { defaultValue: 'Download' })}
        >
          <Download className="w-3.5 h-3.5" />
        </button>
      )}
      <button
        type="button"
        onClick={handleOpen}
        className="p-1 rounded-md text-muted-foreground-tertiary hover:text-foreground hover:bg-surface-sunken transition-colors flex-shrink-0"
        aria-label={t('chat.openArtifactAria', { title: artifact.title })}
      >
        <ExternalLink
          className="w-4 h-4 opacity-0 group-hover:opacity-100 transition-opacity"
          aria-hidden="true"
        />
      </button>
    </div>
  );
}
