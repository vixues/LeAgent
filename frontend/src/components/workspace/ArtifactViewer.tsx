import {
  Pin,
  PinOff,
  Copy,
  Check,
  Download,
  GraduationCap,
  ZoomIn,
  ZoomOut,
  ExternalLink,
} from 'lucide-react';
import { useState, useRef, lazy, Suspense } from 'react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { useArtifactStore } from '@/stores/artifact';
import { getArtifactIcon } from '@/components/chat/workspace/artifactIcon';
import { Markdown } from '@/components/chat/markdown/Markdown';
import { MermaidDiagram } from '@/components/chat/markdown/MermaidDiagram';
import { CodeBlock } from '@/components/chat/markdown/CodeBlock';
import type { Artifact } from '@/types/artifact';
import { UniversalFilePreview } from '@/components/files/UniversalFilePreview';
import { useFilePreviewActions } from '@/components/files/useFilePreviewActions';
import { isPdfTarget, usePdfResearchStore } from '@/features/pdf-reader';

const CanvasPanel = lazy(() => import('../canvas/CanvasPanel'));
const PdfReader = lazy(() =>
  import('@/features/pdf-reader/PdfReader').then((m) => ({ default: m.PdfReader })),
);

/** Matches unpinned `ArtifactHeader` control styling (icon-only). */
const artifactHeaderIconBtn =
  'p-1 rounded-md transition-colors text-muted-foreground hover:text-foreground hover:bg-surface-sunken disabled:opacity-50 disabled:cursor-not-allowed';

export function ArtifactViewer() {
  const { t } = useTranslation();
  const { artifacts, openArtifactId, pinnedIds, pinArtifact, unpinArtifact } =
    useArtifactStore();

  const activeTabId = useArtifactStore((s) => s.activeTabId);
  const effectiveId = activeTabId ?? openArtifactId;
  const artifact = effectiveId ? artifacts[effectiveId] : null;

  const researchActive = usePdfResearchStore((s) => s.active);
  const researchFileId = usePdfResearchStore((s) => s.target?.fileId ?? null);
  const startResearch = usePdfResearchStore((s) => s.start);
  const stopResearch = usePdfResearchStore((s) => s.stop);

  const rawFileId = artifact?.metadata?.fileId;
  const fileId = typeof rawFileId === 'string' ? rawFileId : '';
  const filePreviewActions = useFilePreviewActions(
    fileId,
    artifact?.title ?? '',
    { enabled: Boolean(fileId) },
  );

  if (!artifact) return null;

  const isPinned = pinnedIds.includes(artifact.id);
  const isPdf = Boolean(fileId) && isPdfTarget(
    typeof artifact.metadata?.mimeType === 'string' ? artifact.metadata.mimeType : null,
    artifact.title,
  );

  const readerOpen = isPdf && researchActive && researchFileId === fileId;

  // Research Mode owns the whole panel (its own toolbar replaces the artifact
  // header) so the reader is not boxed under a redundant title bar.
  if (readerOpen) {
    return (
      <div className={cn('flex min-h-0 min-w-0 flex-1 basis-0 flex-col bg-surface')}>
        <Suspense
          fallback={
            <div className="flex min-h-0 flex-1 items-center justify-center text-sm text-muted-foreground">
              {t('pdfReader.loading', { defaultValue: 'Loading PDF…' })}
            </div>
          }
        >
          <PdfReader
            target={{
              fileId,
              fileName: artifact.title,
              mimeType:
                typeof artifact.metadata?.mimeType === 'string'
                  ? artifact.metadata.mimeType
                  : undefined,
            }}
            initialMode="research"
            externalSidebar
            onClose={stopResearch}
          />
        </Suspense>
      </div>
    );
  }

  return (
    <div className={cn('flex min-h-0 min-w-0 flex-1 basis-0 flex-col bg-surface')}>
      <ArtifactHeader
        artifact={artifact}
        isPinned={isPinned}
        onPin={() =>
          isPinned
            ? unpinArtifact(artifact.id)
            : pinArtifact(artifact.id)
        }
        fileToolbar={
          fileId ? (
            <>
              {isPdf && (
                <button
                  type="button"
                  onClick={() =>
                    startResearch({
                      fileId,
                      fileName: artifact.title,
                      mimeType:
                        typeof artifact.metadata?.mimeType === 'string'
                          ? artifact.metadata.mimeType
                          : undefined,
                    })
                  }
                  className={cn(
                    artifactHeaderIconBtn,
                    'text-primary-600 dark:text-primary-400',
                  )}
                  aria-label={t('pdfReader.researchMode', { defaultValue: 'Research Mode' })}
                  title={t('pdfReader.researchMode', { defaultValue: 'Research Mode' })}
                >
                  <GraduationCap className="w-3.5 h-3.5" aria-hidden />
                </button>
              )}
              <button
                type="button"
                disabled={filePreviewActions.openBusy}
                onClick={filePreviewActions.handleOpenClick}
                className={artifactHeaderIconBtn}
                aria-label={t('knowledge.openExternal')}
                title={t('knowledge.openExternal')}
              >
                <ExternalLink className="w-3.5 h-3.5" aria-hidden />
              </button>
              <button
                type="button"
                disabled={filePreviewActions.downloadBusy}
                onClick={filePreviewActions.handleDownloadClick}
                className={artifactHeaderIconBtn}
                aria-label={t('knowledge.download')}
                title={t('knowledge.download')}
              >
                <Download className="w-3.5 h-3.5" aria-hidden />
              </button>
            </>
          ) : null
        }
      />
      <div className="min-h-0 flex flex-1 flex-col overflow-hidden min-w-0">
        <ArtifactContent artifact={artifact} />
      </div>
    </div>
  );
}

/* ── Header ── */
interface ArtifactHeaderProps {
  artifact: Artifact;
  isPinned: boolean;
  onPin: () => void;
  fileToolbar?: ReactNode;
}

function ArtifactHeader({
  artifact,
  isPinned,
  onPin,
  fileToolbar,
}: ArtifactHeaderProps) {
  return (
    <div className="flex items-center gap-1.5 px-3 py-2 border-b border-border-subtle flex-shrink-0">
      <div className="w-7 h-7 shrink-0 rounded-md bg-surface-sunken flex items-center justify-center text-muted-foreground [&_svg]:h-4 [&_svg]:w-4">
        {getArtifactIcon(artifact.type)}
      </div>
      <div className="flex-1 min-w-0">
        <h3 className="text-[13px] font-semibold leading-tight text-foreground truncate">
          {artifact.title}
        </h3>
        <p className="text-[11px] leading-tight text-muted-foreground-tertiary mt-0.5">
          {artifact.language ?? artifact.type}
        </p>
      </div>
      <div className="flex items-center gap-0.5 shrink-0">
        {fileToolbar}
        <button
          type="button"
          onClick={onPin}
          className={cn(
            'p-1 rounded-md transition-colors',
            isPinned
              ? 'text-primary-600 dark:text-primary-400 bg-primary-50 dark:bg-primary-900/20'
              : 'text-muted-foreground hover:text-foreground hover:bg-surface-sunken',
          )}
          aria-label={isPinned ? 'Unpin' : 'Pin'}
        >
          {isPinned ? (
            <PinOff className="w-3.5 h-3.5" />
          ) : (
            <Pin className="w-3.5 h-3.5" />
          )}
        </button>
      </div>
    </div>
  );
}

/* ── Content renderer by type ── */
interface ArtifactContentProps {
  artifact: Artifact;
}

function ArtifactContent({ artifact }: ArtifactContentProps) {
  const fileId =
    typeof artifact.metadata?.fileId === 'string'
      ? artifact.metadata.fileId
      : null;
  if (fileId) {
    const metadata = artifact.metadata as
      | { mimeType?: unknown; size?: unknown }
      | undefined;
    const metaMime = metadata?.mimeType;
    return (
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto overflow-x-hidden p-4">
        <UniversalFilePreview
          layout="fill"
          fileId={fileId}
          fileName={artifact.title}
          mimeType={
            typeof metaMime === 'string' && metaMime.length > 0
              ? metaMime
              : undefined
          }
          sizeBytes={
            typeof metadata?.size === 'number' ? metadata.size : undefined
          }
          showToolbar={false}
        />
      </div>
    );
  }

  switch (artifact.type) {
    case 'code':
      return <CodeArtifact artifact={artifact} />;
    case 'image':
      return <ImageArtifact artifact={artifact} />;
    case 'markdown':
      return (
        <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden p-4">
          <Markdown content={artifact.content} />
        </div>
      );
    case 'mermaid':
      return (
        <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden p-4">
          <MermaidDiagram source={artifact.content} />
        </div>
      );
    case 'html':
    case 'react':
      return (
        <div className="flex flex-1 min-h-0 min-w-0 flex-col">
          <Suspense
            fallback={
              <div className="flex flex-1 min-h-0 items-center justify-center">
                <div className="w-5 h-5 border-2 border-primary-400 border-t-transparent rounded-full animate-spin" />
              </div>
            }
          >
            <CanvasPanel artifact={artifact} className="min-h-0 flex-1" />
          </Suspense>
        </div>
      );
    default:
      return <TextArtifact artifact={artifact} />;
  }
}

function CodeArtifact({ artifact }: { artifact: Artifact }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(artifact.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const ext = artifact.language ? `.${artifact.language}` : '.txt';
    const blob = new Blob([artifact.content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${artifact.title}${ext}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      <div className="absolute top-3 right-3 z-10 flex items-center gap-1">
        <button
          type="button"
          onClick={handleDownload}
          className="flex items-center gap-1 px-2 py-1 rounded-lg bg-foreground/10 hover:bg-foreground/20 text-muted-foreground text-xs transition-colors"
          aria-label="Download"
        >
          <Download className="w-3.5 h-3.5" />
        </button>
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1 px-2 py-1 rounded-lg bg-foreground/10 hover:bg-foreground/20 text-muted-foreground text-xs transition-colors"
          aria-label="Copy code"
        >
          {copied ? (
            <Check className="w-3.5 h-3.5 text-mint-400" />
          ) : (
            <Copy className="w-3.5 h-3.5" />
          )}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <CodeBlock language={artifact.language}>
          <code className="font-mono">{artifact.content}</code>
        </CodeBlock>
      </div>
    </div>
  );
}

function ImageArtifact({ artifact }: { artifact: Artifact }) {
  const [zoom, setZoom] = useState(1);
  const containerRef = useRef<HTMLDivElement>(null);

  return (
    <div className="flex flex-col min-h-0 min-w-0">
      <div className="flex items-center gap-1 px-3 py-1.5 border-b border-border-subtle flex-shrink-0">
        <button
          type="button"
          onClick={() => setZoom((z) => Math.max(0.25, z - 0.25))}
          className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-surface-sunken transition-colors"
          aria-label="Zoom out"
        >
          <ZoomOut className="w-3.5 h-3.5" />
        </button>
        <span className="text-[11px] text-muted-foreground-tertiary tabular-nums min-w-[3ch] text-center">
          {Math.round(zoom * 100)}%
        </span>
        <button
          type="button"
          onClick={() => setZoom((z) => Math.min(4, z + 0.25))}
          className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-surface-sunken transition-colors"
          aria-label="Zoom in"
        >
          <ZoomIn className="w-3.5 h-3.5" />
        </button>
      </div>
      <div
        ref={containerRef}
        className="flex-1 min-h-0 overflow-auto flex items-center justify-center p-4 bg-surface-sunken/30"
      >
        <img
          src={artifact.content}
          alt={artifact.title}
          className="object-contain rounded-lg shadow-sm transition-transform duration-200"
          style={{ transform: `scale(${zoom})`, transformOrigin: 'center' }}
        />
      </div>
    </div>
  );
}

function TextArtifact({ artifact }: { artifact: Artifact }) {
  return (
    <pre className="min-h-0 flex-1 overflow-auto p-4 text-sm text-foreground whitespace-pre-wrap font-mono leading-relaxed">
      {artifact.content}
    </pre>
  );
}
