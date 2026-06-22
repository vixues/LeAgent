import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, ChevronRight, Download } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ChatImage } from '@/components/chat/media/ChatImage';
import type { AgentImageArtifact } from '@/lib/agentImageArtifacts';

interface ArtifactsRailProps {
  artifacts: AgentImageArtifact[];
}

/**
 * Persistent, compact gallery of produced media artifacts. Thumbnails render
 * independently of timeline expand state, so generated images stay visible for
 * the whole session and never flash-then-vanish. Click → lightbox (via
 * {@link ChatImage}); hover → download.
 */
export function ArtifactsRail({ artifacts }: ArtifactsRailProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(true);

  if (artifacts.length === 0) return null;

  return (
    <div className="shrink-0 overflow-hidden rounded-lg border border-border-subtle/50 bg-surface-sunken/40">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-surface/40"
      >
        {open ? (
          <ChevronDown className="size-3 shrink-0 text-muted-foreground" aria-hidden />
        ) : (
          <ChevronRight className="size-3 shrink-0 text-muted-foreground" aria-hidden />
        )}
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          {t('chat.workspace.agent.artifactsTitle', { defaultValue: 'Artifacts' })}
        </span>
        <span className="ml-auto text-[10px] tabular-nums text-muted-foreground/60">
          {artifacts.length}
        </span>
      </button>
      {open && (
        <div className="flex max-h-[26vh] flex-wrap gap-2 overflow-y-auto border-t border-border-subtle/40 p-2.5">
          {artifacts.map((artifact) => (
            <figure key={artifact.id} className="group/thumb relative w-16">
              <ChatImage
                src={artifact.previewUrl}
                alt={artifact.fileName ?? 'artifact'}
                thumbnail
                className="size-16"
              />
              {artifact.downloadUrl && (
                <a
                  href={artifact.downloadUrl}
                  download={artifact.fileName}
                  onClick={(e) => e.stopPropagation()}
                  title={t('chat.workspace.agent.artifactDownload', { defaultValue: 'Download' })}
                  className={cn(
                    'absolute right-1 top-1 flex size-5 items-center justify-center rounded',
                    'bg-black/55 text-white opacity-0 transition-opacity',
                    'group-hover/thumb:opacity-100 focus-visible:opacity-100',
                  )}
                >
                  <Download className="size-3" aria-hidden />
                </a>
              )}
              {artifact.fileName && (
                <figcaption
                  className="mt-1 w-16 truncate text-center font-mono text-[9px] text-muted-foreground"
                  title={artifact.fileName}
                >
                  {artifact.fileName}
                </figcaption>
              )}
            </figure>
          ))}
        </div>
      )}
    </div>
  );
}
