/**
 * Dev-server run/stop/logs for a project-mode folder (folder-scoped API).
 */
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ExternalLink, PlayCircle, Square, Terminal } from 'lucide-react';
import { Badge, Button, Card } from '@/components/ui';
import {
  useFolderProjectStatus,
  useRunFolderProject,
  useStopFolderProject,
  useFolderProjectLogs,
  type FolderProjectRunResponse,
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
  const [runInfo, setRunInfo] = useState<FolderProjectRunResponse | null>(null);
  const { lines, error: logsError } = useFolderProjectLogs(folderId, { enabled: true });
  const logEndRef = useRef<HTMLDivElement>(null);

  const isRunning = Boolean(status?.is_running);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [lines]);

  const handleRun = async () => {
    const resp = await run.mutateAsync(folderId);
    setRunInfo(resp);
  };

  const handleStop = async () => {
    await stop.mutateAsync(folderId);
    setRunInfo(null);
  };

  const previewUrl = runInfo?.preview_url ?? null;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 p-4 sm:p-5">
      <Card className="p-4">
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
            {previewUrl && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() =>
                  window.open(resolveCodingProjectPreviewHref(previewUrl), '_blank', 'noopener')
                }
                leftIcon={<ExternalLink className="h-4 w-4" />}
              >
                {t('codingProjects.run.openPreview', { defaultValue: 'Open preview' })}
              </Button>
            )}
          </div>
        </div>
      </Card>

      {previewUrl && isRunning && (
        <Card className="min-h-[240px] flex-1 overflow-hidden p-0">
          <iframe
            title={folderName}
            src={resolveCodingProjectPreviewHref(previewUrl)}
            className="h-full min-h-[320px] w-full border-0"
          />
        </Card>
      )}

      <Card className="flex min-h-[200px] flex-1 flex-col overflow-hidden">
        <div className="flex items-center gap-2 border-b border-border px-3 py-2 text-xs font-medium text-muted-foreground">
          <Terminal className="h-3.5 w-3.5" />
          {t('codingProjects.run.logs', { defaultValue: 'Logs' })}
        </div>
        <pre className="flex-1 overflow-auto p-3 font-mono text-[11px] leading-relaxed text-foreground/90">
          {logsError ? (
            <span className="text-rose-600">{logsError}</span>
          ) : lines.length === 0 ? (
            t('codingProjects.run.noLogs', { defaultValue: 'No log output yet.' })
          ) : (
            lines.join('\n')
          )}
          <div ref={logEndRef} />
        </pre>
      </Card>
    </div>
  );
}
