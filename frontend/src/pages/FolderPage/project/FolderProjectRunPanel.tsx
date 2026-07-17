/**
 * Dev-server run/stop/logs for a project-mode folder (folder-scoped API).
 */
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, ExternalLink, PlayCircle, Square, Terminal } from 'lucide-react';
import { Badge, Button, Card } from '@/components/ui';
import {
  useFolderProjectStatus,
  useFolderProjectPreview,
  useRunFolderProject,
  useStopFolderProject,
  useFolderProjectLogs,
} from '@/hooks/useFolderProjectRuntime';
import { resolveCodingProjectPreviewHref } from '@/lib/previewUrl';
import { CodingProjectStatusBadge } from '@/pages/CodingProjects/CodingProjectStatusBadge';
import type { CodingProjectStatus } from '@/hooks/useCodingProjects';

interface Props {
  folderId: string;
  folderName: string;
}

export default function FolderProjectRunPanel({ folderId, folderName }: Props) {
  const { t } = useTranslation();
  const { data: status } = useFolderProjectStatus(folderId);
  const run = useRunFolderProject();
  const stop = useStopFolderProject();
  const isRunning = Boolean(status?.is_running);
  const { data: preview } = useFolderProjectPreview(folderId, isRunning);
  const { lines, error: logsError } = useFolderProjectLogs(folderId, { enabled: true });
  const [logsOpen, setLogsOpen] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [lines]);

  const handleRun = async () => {
    await run.mutateAsync(folderId);
  };

  const handleStop = async () => {
    await stop.mutateAsync(folderId);
  };

  const previewUrl = isRunning ? preview?.preview_url ?? null : null;
  const previewHref = previewUrl ? resolveCodingProjectPreviewHref(previewUrl) : null;
  const showPreview = Boolean(previewHref);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 p-4 sm:p-5">
      <Card className="shrink-0 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="truncate text-base font-semibold">{folderName}</h2>
              {status?.status && (
                <CodingProjectStatusBadge status={status.status as CodingProjectStatus} />
              )}
              {status?.runtime_kind && (
                <Badge variant="primary" className="text-[10px]">
                  {status.runtime_kind}
                </Badge>
              )}
            </div>
            {status?.port ? (
              <p className="mt-1 text-xs text-muted-foreground">
                {t('codingProjects.run.port', { defaultValue: 'Port' })}: {status.port}
              </p>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            {!isRunning ? (
              <Button
                size="sm"
                onClick={() => void handleRun()}
                loading={run.isPending}
                leftIcon={<PlayCircle className="h-4 w-4" />}
              >
                {t('codingProjects.run.start', { defaultValue: 'Run' })}
              </Button>
            ) : (
              <Button
                size="sm"
                variant="secondary"
                onClick={() => void handleStop()}
                loading={stop.isPending}
                leftIcon={<Square className="h-4 w-4" />}
              >
                {t('codingProjects.run.stop', { defaultValue: 'Stop' })}
              </Button>
            )}
            {previewHref && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => window.open(previewHref, '_blank', 'noopener')}
                leftIcon={<ExternalLink className="h-4 w-4" />}
              >
                {t('codingProjects.run.openPreview', { defaultValue: 'Open preview' })}
              </Button>
            )}
          </div>
        </div>
      </Card>

      {previewHref && (
        <Card className="min-h-0 flex-1 overflow-hidden p-0">
          <iframe title={folderName} src={previewHref} className="h-full w-full border-0" />
        </Card>
      )}

      <Card className={`flex flex-col overflow-hidden ${showPreview ? 'shrink-0' : 'min-h-0 flex-1'}`}>
        <button
          type="button"
          onClick={() => setLogsOpen((o) => !o)}
          disabled={!showPreview}
          aria-expanded={!showPreview || logsOpen}
          className="flex items-center gap-2 px-3 py-2 text-left text-xs font-medium text-muted-foreground hover:text-foreground disabled:cursor-default disabled:hover:text-muted-foreground"
        >
          <Terminal className="h-3.5 w-3.5" />
          {t('codingProjects.run.logs', { defaultValue: 'Logs' })}
          {showPreview && (
            <ChevronDown
              className={`ml-auto h-3.5 w-3.5 transition-transform ${logsOpen ? 'rotate-180' : ''}`}
            />
          )}
        </button>
        {(!showPreview || logsOpen) && (
          <pre
            className={`min-h-0 overflow-auto border-t border-border p-3 font-mono text-[11px] leading-relaxed text-foreground/90 ${
              showPreview ? 'max-h-48' : 'flex-1'
            }`}
          >
            {logsError ? (
              <span className="text-rose-600">{logsError}</span>
            ) : lines.length === 0 ? (
              t('codingProjects.run.noLogs', { defaultValue: 'No log output yet.' })
            ) : (
              lines.join('\n')
            )}
            <div ref={logEndRef} />
          </pre>
        )}
      </Card>
    </div>
  );
}
