import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ExternalLink, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui';
import { EMPTY_MESSAGE_LIST } from '@/lib/emptyChatMessages';
import {
  buildCodingProjectLoopbackPreviewUrl,
  findLatestCodingProjectRunPreview,
} from '@/lib/projectToolEnvelope';
import { useChatStore } from '@/stores/chat';
import { useCodingProjectStatus } from '@/hooks/useCodingProjects';

const EMPTY_IDS: string[] = [];

export function CodingProjectPreviewTab() {
  const { t } = useTranslation();
  const currentSessionId = useChatStore((s) => s.currentSessionId);
  const startedProjectIds = useChatStore((s) =>
    currentSessionId ? s.codingProjectIdsBySession[currentSessionId] : undefined,
  );
  const messages = useChatStore((s) =>
    currentSessionId ? s.messages[currentSessionId] : undefined,
  );

  const safeStartedIds = startedProjectIds ?? EMPTY_IDS;
  const safeMessages = messages ?? EMPTY_MESSAGE_LIST;

  const preview = useMemo(
    () => findLatestCodingProjectRunPreview(safeMessages),
    [safeMessages],
  );
  const [iframeKey, setIframeKey] = useState(0);

  // Fallback: clicking Run/Restart buttons doesn't create a new tool-call message,
  // so we also try the last registered coding project id for this session.
  const fallbackProjectId = safeStartedIds[safeStartedIds.length - 1] ?? null;
  const effectiveProjectId = preview?.projectId ?? fallbackProjectId;

  const { data: status } = useCodingProjectStatus(effectiveProjectId, {
    enabled: Boolean(effectiveProjectId),
  });

  const isRunning =
    !!status?.is_running || status?.status === 'running' || status?.status === 'starting';

  const iframeSrc = useMemo(() => {
    if (preview) return buildCodingProjectLoopbackPreviewUrl(preview);
    const port = status?.port ?? null;
    if (!port || port <= 0) return '';
    const origin = `http://127.0.0.1:${port}`;
    return status?.runtime_kind === 'fastapi' ? `${origin}/docs` : `${origin}/`;
  }, [preview, status?.port, status?.runtime_kind]);

  if (!effectiveProjectId) {
    return (
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-2 p-6 text-center">
        <p className="text-xs text-muted-foreground">
          {t('chat.workspace.agent.codingProjectPreviewNotRunning')}
        </p>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 h-full min-w-0 flex-1 basis-0 flex-col overflow-hidden rounded-lg border border-border-subtle/50 bg-surface-sunken/40">
      <div className="flex flex-wrap items-center gap-1 border-b border-border-subtle/40 bg-surface/30 px-2 py-1">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-6 w-6 p-0"
          disabled={!isRunning || !iframeSrc}
          onClick={() => window.open(iframeSrc, '_blank', 'noopener,noreferrer')}
          aria-label={t('chat.workspace.agent.codingProjectPreviewOpenExternal')}
          title={t('chat.workspace.agent.codingProjectPreviewOpenExternal')}
        >
          <ExternalLink className="size-3 shrink-0" aria-hidden />
        </Button>
        <span className="hidden whitespace-nowrap text-[10px] text-muted-foreground sm:inline">
          {t('chat.workspace.agent.codingProjectPreviewOpenExternal')}
        </span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-6 w-6 p-0"
          disabled={!isRunning || !iframeSrc}
          aria-label={t('chat.workspace.agent.codingProjectPreviewRefresh')}
          title={t('chat.workspace.agent.codingProjectPreviewRefresh')}
          onClick={() => setIframeKey((k) => k + 1)}
        >
          <RefreshCw className="size-3 shrink-0" aria-hidden />
        </Button>
        <span className="hidden whitespace-nowrap text-[10px] text-muted-foreground sm:inline">
          {t('chat.workspace.agent.codingProjectPreviewRefresh')}
        </span>
        <div className="ml-auto truncate font-mono text-[9px] tabular-nums text-muted-foreground/70">
          {preview?.iframeHost ? `${preview.iframeHost}:${preview.port}` : status?.port ?? '—'}
        </div>
      </div>

      <div className="min-h-0 flex-1 bg-background">
        {isRunning && iframeSrc ? (
          <iframe
            key={iframeKey}
            src={iframeSrc}
            className="h-full min-h-0 w-full border-0"
            sandbox="allow-scripts allow-same-origin allow-popups allow-forms allow-modals"
            referrerPolicy="no-referrer"
            title="coding-project-workspace-preview"
          />
        ) : (
          <div className="flex h-full min-h-0 items-center justify-center px-4 text-center text-[12px] text-muted-foreground">
            {t('chat.workspace.agent.codingProjectPreviewNotRunning')}
          </div>
        )}
      </div>
    </div>
  );
}

