/**
 * Run / stop dev server, optional embedded preview, and logs — secondary to Files/Git.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ChevronDown,
  ExternalLink,
  PlayCircle,
  RefreshCw,
  Square,
  Terminal,
} from 'lucide-react';
import { Badge, Button, Card } from '@/components/ui';
import {
  CodingProject,
  RunResponse,
  useCodingProjectLogs,
  useCodingProjectStatus,
  useRunCodingProject,
  useStopCodingProject,
} from '@/hooks/useCodingProjects';
import {
  buildCodingProjectIframePreviewSrc,
  codingProjectRunPreviewInfoFromUnknown,
} from '@/lib/projectToolEnvelope';
import { resolveCodingProjectPreviewHref } from '@/lib/previewUrl';
import { CodingProjectStatusBadge } from './CodingProjectStatusBadge';

interface Props {
  project: CodingProject;
}

export function CodingProjectRunPanel({ project }: Props) {
  const { t } = useTranslation();
  const { data: status } = useCodingProjectStatus(project.id);
  const run = useRunCodingProject();
  const stop = useStopCodingProject();
  const [runInfo, setRunInfo] = useState<RunResponse | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const isRunning = !!status?.is_running || project.status === 'running';

  const { lines, error: logsError } = useCodingProjectLogs(project.id, {
    enabled: true,
    max: 1500,
  });

  const crashed =
    project.status === 'crashed' || status?.status === 'crashed';

  const errorMessages = [
    logsError ? `${t('codingProjects.run.logStreamError')}: ${logsError}` : null,
    run.isError ? String((run.error as Error)?.message ?? run.error) : null,
    stop.isError ? String((stop.error as Error)?.message ?? stop.error) : null,
  ].filter((x): x is string => Boolean(x));

  const previewUrl = runInfo?.preview_url ?? null;

  const handleRun = async () => {
    const resp = await run.mutateAsync(project.id);
    setRunInfo(resp);
  };

  const handleStop = async () => {
    await stop.mutateAsync(project.id);
    setRunInfo(null);
    setPreviewOpen(false);
  };

  const handleOpenExternal = () => {
    if (runInfo) {
      const info = codingProjectRunPreviewInfoFromUnknown(runInfo);
      if (info) {
        window.open(
          buildCodingProjectIframePreviewSrc(info),
          '_blank',
          'noopener,noreferrer',
        );
        return;
      }
    }
    if (!previewUrl) return;
    window.open(
      resolveCodingProjectPreviewHref(previewUrl),
      '_blank',
      'noopener,noreferrer',
    );
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 p-4 sm:p-5">
      {(crashed || errorMessages.length > 0) && (
        <div
          className="rounded-lg border border-rose-500/35 bg-rose-500/[0.08] px-3 py-2.5 text-sm text-rose-900 dark:text-rose-100"
          role="alert"
        >
          {crashed && (
            <p className="mb-1.5 font-medium">{t('codingProjects.run.crashedHint')}</p>
          )}
          {errorMessages.map((msg, idx) => (
            <p key={idx} className="break-all font-mono text-xs opacity-95">
              {msg}
            </p>
          ))}
        </div>
      )}

      <Card className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-base font-semibold truncate">{project.name}</h2>
              <CodingProjectStatusBadge status={status?.status ?? project.status} />
              <Badge
                variant={project.runtime_kind === 'fastapi' ? 'success' : project.runtime_kind === 'python' ? 'warning' : 'primary'}
                className="text-[10px]"
              >
                {project.runtime_kind}
              </Badge>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {!isRunning ? (
              <Button
                variant="primary"
                size="sm"
                onClick={handleRun}
                disabled={run.isPending}
                loading={run.isPending}
                leftIcon={<PlayCircle className="h-4 w-4" />}
              >
                {t('codingProjects.run.run')}
              </Button>
            ) : (
              <Button
                variant="danger"
                size="sm"
                onClick={handleStop}
                disabled={stop.isPending}
                loading={stop.isPending}
                leftIcon={<Square className="h-4 w-4" />}
              >
                {t('codingProjects.run.stop')}
              </Button>
            )}
            {isRunning && previewUrl && (
              <>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={handleOpenExternal}
                  leftIcon={<ExternalLink className="h-4 w-4" />}
                >
                  {t('codingProjects.run.openExternal')}
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setPreviewOpen((o) => !o)}
                  aria-expanded={previewOpen}
                  leftIcon={
                    <ChevronDown
                      className={`h-4 w-4 transition-transform ${previewOpen ? 'rotate-180' : ''}`}
                    />
                  }
                >
                  {t('codingProjects.run.expandPreview')}
                </Button>
              </>
            )}
          </div>
        </div>
      </Card>

      {previewOpen && isRunning && runInfo && (
        <PreviewSurface runInfo={runInfo} isRunning={isRunning} />
      )}

      <Card className="p-3">
        <div className="mb-2 flex items-center gap-2">
          <Terminal className="size-4" aria-hidden />
          <span className="text-sm font-medium">{t('codingProjects.run.logs')}</span>
        </div>
        <LogConsole
          lines={lines}
          isRunning={isRunning}
          crashed={crashed}
        />
      </Card>
    </div>
  );
}

interface PreviewSurfaceProps {
  runInfo: RunResponse;
  isRunning: boolean;
}

function PreviewSurface({ runInfo, isRunning }: PreviewSurfaceProps) {
  const { t } = useTranslation();
  const [iframeKey, setIframeKey] = useState(0);

  const previewInfo = codingProjectRunPreviewInfoFromUnknown(runInfo);
  const iframeSrc = previewInfo ? buildCodingProjectIframePreviewSrc(previewInfo) : '';
  const runtimeKind = runInfo.runtime_kind;

  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between border-b border-border bg-muted/40 px-3 py-2">
        <div className="text-xs text-muted-foreground">
          {runtimeKind === 'fastapi'
            ? t('codingProjects.run.fastapiPreviewHint')
            : t('codingProjects.run.frontendPreviewHint')}
        </div>
        <Button
          variant="ghost"
          size="sm"
          disabled={!isRunning || !iframeSrc}
          onClick={() => setIframeKey((k) => k + 1)}
        >
          <RefreshCw className="size-3.5" />
        </Button>
      </div>
      <div className="max-h-96 min-h-[16rem] bg-background">
        {isRunning && iframeSrc ? (
          <iframe
            key={iframeKey}
            src={iframeSrc}
            className="h-full min-h-[16rem] w-full border-0"
            sandbox="allow-scripts allow-same-origin allow-popups allow-forms allow-modals"
            referrerPolicy="no-referrer"
            title="coding-project-preview"
          />
        ) : (
          <div className="flex h-full min-h-[16rem] w-full items-center justify-center text-sm text-muted-foreground">
            <PlayCircle className="mr-2 size-5" aria-hidden />
            {t('codingProjects.run.runToPreview')}
          </div>
        )}
      </div>
    </Card>
  );
}

interface LogConsoleProps {
  lines: ReturnType<typeof useCodingProjectLogs>['lines'];
  isRunning: boolean;
  crashed: boolean;
}

function LogConsole({ lines, isRunning, crashed }: LogConsoleProps) {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    containerRef.current.scrollTop = containerRef.current.scrollHeight;
  }, [lines]);

  const display = useMemo(() => lines.slice(-500), [lines]);

  if (display.length === 0) {
    return (
      <div className="rounded-md border border-border bg-zinc-950/95 px-3 py-6 text-center font-mono text-xs text-zinc-300">
        {isRunning
          ? t('codingProjects.run.logsEmpty')
          : crashed
            ? t('codingProjects.run.logsIdleCrashed')
            : t('codingProjects.run.logsIdle')}
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="h-56 overflow-auto rounded-md border border-border bg-zinc-950/95 px-3 py-2 font-mono text-xs text-zinc-300"
    >
      {display.map((line) => (
        <div
          key={`${line.seq}-${line.ts}`}
          className={
            line.stream === 'stderr'
              ? 'break-all whitespace-pre-wrap text-rose-300'
              : 'break-all whitespace-pre-wrap'
          }
        >
          {line.text}
        </div>
      ))}
    </div>
  );
}
