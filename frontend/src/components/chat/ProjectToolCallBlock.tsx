import { useEffect, useMemo, useRef, useState, type MouseEvent } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertCircle,
  ChevronDown,
  ChevronRight,
  FileCode2,
  Loader2,
  RefreshCw,
  Square,
  Wrench,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  extractDocProcessorPreviewText,
  extractDocProcessorPath,
  isDocProcessorTool,
} from '@/lib/docProcessorStreamPreview';
import {
  changedFilesList,
  extractCodingProjectId,
  fmtJson,
  isProjectFamilyTool,
  parseActivity,
  strArg,
} from '@/lib/projectToolEnvelope';
import type { ToolCall } from '@/types/chat';
import {
  type CodingProjectStatus,
  useCodingProjectStatus,
  useRunCodingProject,
  useStopCodingProject,
} from '@/hooks/useCodingProjects';
import { useChatStore } from '@/stores/chat';
import { useArtifactStore } from '@/stores/artifact';
import { useLayoutStore } from '@/stores/layout';

export { isProjectFamilyTool };

/** Open the chat right workspace on the Agent tab (coding project preview lives there). */
export function focusChatWorkspaceForCodingProjectPreview() {
  useLayoutStore.getState().setWorkspaceOpen(true);
  useLayoutStore.getState().setWorkspaceTab('preview');
  useArtifactStore.getState().closeArtifact();
  useArtifactStore.setState({ activeTabId: null });
}

function coerceCodingProjectStatus(s: unknown): CodingProjectStatus {
  if (typeof s !== 'string') return 'idle';
  const allowed: CodingProjectStatus[] = [
    'idle',
    'starting',
    'running',
    'stopping',
    'crashed',
  ];
  return allowed.includes(s as CodingProjectStatus) ? (s as CodingProjectStatus) : 'idle';
}

function lineCount(s: string): number {
  if (!s) return 0;
  return s.split('\n').length;
}

interface ProjectToolCallBlockProps {
  toolCall: ToolCall;
  /** When set, successful ``coding_project_run`` registers for session cleanup on leave. */
  sessionId?: string | null;
}

/**
 * Rich tool bubble for ``project_*``, ``coding_project_*``, and ``coding_agent``:
 * paths, diff-ish layouts, and coding-agent activity when present.
 */
export function ProjectToolCallBlock({ toolCall, sessionId }: ProjectToolCallBlockProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const name = toolCall.name;
  const args = toolCall.arguments ?? {};

  const isCodingProjectRun = name === 'coding_project_run';
  const codingProjectId = isCodingProjectRun
    ? (extractCodingProjectId(toolCall.result) ?? strArg(args, 'project_id')).trim()
    : '';
  const pollCodingProject =
    isCodingProjectRun && toolCall.status === 'success' && codingProjectId.length > 0;

  const { data: cpStatus } = useCodingProjectStatus(codingProjectId || undefined, {
    enabled: pollCodingProject,
  });
  const runCp = useRunCodingProject();
  const stopCp = useStopCodingProject();
  const registerCodingProjectForSession = useChatStore(
    (s) => s.registerCodingProjectForSession,
  );

  const codingRunPrevStatusRef = useRef<ToolCall['status'] | null>(null);
  const codingRunPrevIsRunningRef = useRef<boolean | null>(null);
  const openedWorkspaceForCodingRunRef = useRef<string | null>(null);

  // Always register the project id for session cleanup / preview fallback, even when this
  // tool-call came from history or when the user restarts via API (no new tool-call message).
  useEffect(() => {
    if (!sessionId || !isCodingProjectRun) return;
    const id = codingProjectId || extractCodingProjectId(toolCall.result);
    if (id) registerCodingProjectForSession(sessionId, id);
  }, [
    sessionId,
    isCodingProjectRun,
    codingProjectId,
    toolCall.result,
    registerCodingProjectForSession,
  ]);

  /** After a live ``coding_project_run`` succeeds, surface the right workspace (not on history hydrate). */
  useEffect(() => {
    if (!isCodingProjectRun || !sessionId) return;

    const prev = codingRunPrevStatusRef.current;
    codingRunPrevStatusRef.current = toolCall.status;

    if (toolCall.status !== 'success') return;

    const pid = extractCodingProjectId(toolCall.result) ?? strArg(args, 'project_id').trim();
    if (!pid) return;

    if (prev === null) return;
    if (prev === 'success') return;

    const key = `${sessionId}:${toolCall.id}`;
    if (openedWorkspaceForCodingRunRef.current === key) return;
    openedWorkspaceForCodingRunRef.current = key;
    focusChatWorkspaceForCodingProjectPreview();
  }, [
    isCodingProjectRun,
    sessionId,
    toolCall.status,
    toolCall.id,
    toolCall.result,
    args,
  ]);

  /** When the polled status flips into running, surface the preview tab (covers restart clicks). */
  useEffect(() => {
    if (!pollCodingProject || !sessionId) return;
    const prev = codingRunPrevIsRunningRef.current;
    const now =
      !!cpStatus?.is_running ||
      cpStatus?.status === 'running' ||
      cpStatus?.status === 'starting';
    codingRunPrevIsRunningRef.current = now;

    // First mount = don't auto-open on history hydrate.
    if (prev === null) return;
    if (prev) return;
    if (!now) return;

    const key = `${sessionId}:${codingProjectId}:running`;
    if (openedWorkspaceForCodingRunRef.current === key) return;
    openedWorkspaceForCodingRunRef.current = key;
    focusChatWorkspaceForCodingProjectPreview();
  }, [pollCodingProject, sessionId, codingProjectId, cpStatus?.is_running, cpStatus?.status]);

  const inlineRunChrome = useMemo(() => {
    if (!pollCodingProject) return null;
    const rawStatus =
      toolCall.result && typeof toolCall.result === 'object' && !Array.isArray(toolCall.result)
        ? (toolCall.result as Record<string, unknown>).status
        : undefined;
    const badgeStatus = cpStatus?.status ?? coerceCodingProjectStatus(rawStatus);
    const isRunning =
      !!cpStatus?.is_running ||
      badgeStatus === 'running' ||
      badgeStatus === 'starting';

    const handleStop = (e: MouseEvent<HTMLButtonElement>) => {
      e.preventDefault();
      e.stopPropagation();
      void stopCp.mutateAsync(codingProjectId);
    };
    const handleRestart = (e: MouseEvent<HTMLButtonElement>) => {
      e.preventDefault();
      e.stopPropagation();
      void runCp.mutateAsync(codingProjectId).then((resp) => {
        if (sessionId && resp?.project_id) {
          registerCodingProjectForSession(sessionId, String(resp.project_id));
        }
        focusChatWorkspaceForCodingProjectPreview();
      });
    };

    const statusLabel = t(`codingProjects.status.${badgeStatus}`);

    return (
      <div
        className="flex shrink-0 items-center gap-1.5"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => e.stopPropagation()}
      >
        <span
          className="max-w-[5.5rem] truncate text-[10px] text-muted-foreground-tertiary"
          title={statusLabel}
        >
          {statusLabel}
        </span>
        {isRunning ? (
          <button
            type="button"
            className={cn(
              'rounded-lg p-1.5 text-muted-foreground-tertiary transition-colors',
              'hover:bg-surface-sunken hover:text-foreground',
              'disabled:cursor-not-allowed disabled:opacity-50',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40',
            )}
            aria-label={t('codingProjects.run.stop')}
            title={t('codingProjects.run.stop')}
            disabled={stopCp.isPending}
            onClick={handleStop}
          >
            {stopCp.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
            ) : (
              <Square className="h-3.5 w-3.5" strokeWidth={2} aria-hidden />
            )}
          </button>
        ) : (
          <button
            type="button"
            className={cn(
              'rounded-lg p-1.5 text-muted-foreground-tertiary transition-colors',
              'hover:bg-surface-sunken hover:text-foreground',
              'disabled:cursor-not-allowed disabled:opacity-50',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40',
            )}
            aria-label={t('codingProjects.run.restart')}
            title={t('codingProjects.run.restart')}
            disabled={runCp.isPending}
            onClick={handleRestart}
          >
            {runCp.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" strokeWidth={2} aria-hidden />
            )}
          </button>
        )}
      </div>
    );
  }, [
    pollCodingProject,
    toolCall.result,
    cpStatus?.status,
    cpStatus?.is_running,
    codingProjectId,
    stopCp.isPending,
    runCp.isPending,
    stopCp.mutateAsync,
    runCp.mutateAsync,
    t,
  ]);

  const toolDisplayName = t(`chat.toolNames.${name}`, {
    defaultValue: name.replace(/_/g, ' '),
  });

  const statusConfig = {
    pending: {
      icon: <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />,
      border: 'border-border-subtle',
      bg: 'bg-surface-sunken/30',
    },
    running: {
      icon: <Loader2 className="h-3.5 w-3.5 animate-spin text-primary-500" />,
      border: 'border-primary-200 dark:border-primary-800',
      bg: 'bg-primary-50/30 dark:bg-primary-950/20',
    },
    awaiting_user: {
      icon: <Loader2 className="h-3.5 w-3.5 animate-spin text-amber-500" />,
      border: 'border-amber-200 dark:border-amber-800',
      bg: 'bg-amber-50/30 dark:bg-amber-950/20',
    },
    success: {
      icon: <FileCode2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />,
      border: 'border-border-subtle',
      bg: 'bg-surface-sunken/30',
    },
    error: {
      icon: <AlertCircle className="h-3.5 w-3.5 text-red-500" />,
      border: 'border-red-200 dark:border-red-800',
      bg: 'bg-red-50/40 dark:bg-red-900/10',
    },
  };

  const config = statusConfig[toolCall.status];
  const activity = useMemo(() => parseActivity(toolCall.result), [toolCall.result]);
  const changedFiles = useMemo(() => changedFilesList(toolCall.result), [toolCall.result]);

  const headerPath =
    name === 'coding_agent'
      ? ''
      : strArg(args, 'path') ||
        strArg(args, 'project_path') ||
        strArg(args, 'file_path') ||
        '';

  const body = useMemo(() => {
    if (isDocProcessorTool(name)) {
      const filePath =
        strArg(args, 'file_path') ||
        extractDocProcessorPath(toolCall.argumentsRaw ?? '', args);
      const op = strArg(args, 'operation');
      const partial = args;
      const streamBody =
        toolCall.status === 'running' || toolCall.status === 'pending'
          ? extractDocProcessorPreviewText(
              name,
              toolCall.argumentsRaw ?? '',
              partial,
            )
          : '';
      const bodyText =
        name === 'text_processor'
          ? strArg(args, 'data') || streamBody
          : strArg(args, 'content') || streamBody;
      const n = lineCount(bodyText);
      return (
        <div className="space-y-2">
          {filePath ? (
            <div className="text-[11px] font-mono text-foreground truncate" title={filePath}>
              {filePath}
              {op ? (
                <span className="ml-1.5 text-muted-foreground-tertiary">({op})</span>
              ) : null}
              {n > 0 ? (
                <span className="ml-1 text-muted-foreground-tertiary">
                  ({t('chat.projectTool.lines', { defaultValue: '{{count}} lines', count: n })})
                </span>
              ) : null}
            </div>
          ) : null}
          {(toolCall.status === 'running' || toolCall.status === 'pending') &&
          streamBody &&
          streamBody !== bodyText ? (
            <p className="text-[10px] text-primary/80">
              {t('chat.projectTool.streaming', { defaultValue: 'Streaming content…' })}
            </p>
          ) : null}
          <pre
            className={cn(
              'max-h-56 overflow-auto rounded-md p-2 font-mono text-[10px] whitespace-pre-wrap break-words',
              toolCall.status === 'running' || toolCall.status === 'pending'
                ? 'bg-primary-50/40 dark:bg-primary-950/20 border border-primary/20'
                : 'bg-surface-sunken',
            )}
          >
            {bodyText || (toolCall.status === 'running' ? '…' : '—')}
          </pre>
          {toolCall.result !== undefined ? (
            <details className="rounded-md border border-border-subtle/60">
              <summary className="cursor-pointer px-2 py-1 text-[10px] text-muted-foreground">
                {t('chat.projectTool.rawResult', { defaultValue: 'Raw result' })}
              </summary>
              <pre className="max-h-40 overflow-auto border-t border-border-subtle/60 p-2 font-mono text-[10px] whitespace-pre-wrap break-words">
                {fmtJson(toolCall.result)}
              </pre>
            </details>
          ) : null}
        </div>
      );
    }

    if (name === 'project_edit') {
      const path = strArg(args, 'path');
      const oldS = strArg(args, 'old_string');
      const newS = strArg(args, 'new_string');
      return (
        <div className="space-y-2">
          {path ? (
            <div className="text-[11px] font-mono text-foreground truncate" title={path}>
              {path}
            </div>
          ) : null}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 min-h-0">
            <div className="min-h-0">
              <div className="text-[9px] font-semibold uppercase text-muted-foreground mb-0.5">
                {t('chat.projectTool.old', { defaultValue: 'Before' })}
              </div>
              <pre className="max-h-40 overflow-auto rounded-md bg-red-500/5 dark:bg-red-950/20 p-2 font-mono text-[10px] whitespace-pre-wrap break-words border border-red-500/10">
                {oldS || '—'}
              </pre>
            </div>
            <div className="min-h-0">
              <div className="text-[9px] font-semibold uppercase text-muted-foreground mb-0.5">
                {t('chat.projectTool.new', { defaultValue: 'After' })}
              </div>
              <pre className="max-h-40 overflow-auto rounded-md bg-emerald-500/5 dark:bg-emerald-950/20 p-2 font-mono text-[10px] whitespace-pre-wrap break-words border border-emerald-500/10">
                {newS || '—'}
              </pre>
            </div>
          </div>
        </div>
      );
    }

    if (name === 'project_write') {
      const path = strArg(args, 'path');
      const content = strArg(args, 'content');
      const n = lineCount(content);
      return (
        <div className="space-y-2">
          {path ? (
            <div className="text-[11px] font-mono text-foreground truncate" title={path}>
              {path}{' '}
              <span className="text-muted-foreground-tertiary">
                ({t('chat.projectTool.lines', { defaultValue: '{{count}} lines', count: n })})
              </span>
            </div>
          ) : null}
          <pre className="max-h-56 overflow-auto rounded-md bg-surface-sunken p-2 font-mono text-[10px] whitespace-pre-wrap break-words">
            {content || '—'}
          </pre>
        </div>
      );
    }

    if (name === 'project_apply_patch') {
      const diff = strArg(args, 'diff');
      return (
        <div className="space-y-2">
          <details className="rounded-md border border-border-subtle/80 bg-surface-sunken/50">
            <summary className="cursor-pointer select-none px-2 py-1.5 text-[10px] font-medium text-muted-foreground hover:text-foreground">
              {t('chat.projectTool.unifiedDiff', { defaultValue: 'Unified diff' })}{' '}
              <span className="text-muted-foreground-tertiary">
                ({t('chat.projectTool.lines', { defaultValue: '{{count}} lines', count: lineCount(diff) })})
              </span>
            </summary>
            <pre className="max-h-72 overflow-auto border-t border-border-subtle/60 p-2 font-mono text-[10px] whitespace-pre-wrap break-words">
              {diff || '—'}
            </pre>
          </details>
        </div>
      );
    }

    if (name === 'project_read') {
      const path = strArg(args, 'path');
      const resText =
        typeof toolCall.result === 'string'
          ? toolCall.result
          : toolCall.result !== undefined
            ? fmtJson(toolCall.result)
            : '';
      return (
        <div className="space-y-2">
          {path ? (
            <div className="text-[11px] font-mono text-foreground truncate" title={path}>
              {path}
            </div>
          ) : null}
          {resText ? (
            <pre className="max-h-64 overflow-auto rounded-md bg-surface-sunken p-2 font-mono text-[10px] whitespace-pre-wrap break-words">
              {resText}
            </pre>
          ) : (
            <p className="text-[10px] text-muted-foreground-tertiary italic">
              {t('chat.projectTool.noResultYet', { defaultValue: 'No output yet.' })}
            </p>
          )}
        </div>
      );
    }

    if (name === 'coding_agent') {
      const prompt = strArg(args, 'prompt');
      const preview = prompt.length > 400 ? `${prompt.slice(0, 400)}…` : prompt;
      return (
        <div className="space-y-3">
          <div>
            <div className="text-[9px] font-semibold uppercase text-muted-foreground mb-0.5">
              {t('chat.projectTool.task', { defaultValue: 'Task' })}
            </div>
            <p className="text-[11px] text-foreground whitespace-pre-wrap break-words leading-snug">
              {preview || '—'}
            </p>
          </div>
          {changedFiles.length > 0 ? (
            <div>
              <div className="text-[9px] font-semibold uppercase text-muted-foreground mb-0.5">
                {t('chat.projectTool.changedFiles', { defaultValue: 'Changed paths' })}
              </div>
              <ul className="max-h-32 overflow-y-auto space-y-0.5 font-mono text-[10px] text-foreground/90">
                {changedFiles.map((p) => (
                  <li key={p} className="truncate" title={p}>
                    {p}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {activity.length > 0 ? (
            <div>
              <div className="text-[9px] font-semibold uppercase text-muted-foreground mb-1">
                {t('chat.projectTool.activity', { defaultValue: 'Activity' })}
              </div>
              <ul className="max-h-40 overflow-y-auto space-y-1 border-l border-border-subtle pl-2">
                {activity.map((row, i) => (
                  <li key={i} className="text-[10px] text-muted-foreground">
                    <span className="font-medium text-foreground">{row.tool ?? '?'}</span>
                    {row.path ? (
                      <span className="ml-1 font-mono truncate block" title={row.path}>
                        {row.path}
                      </span>
                    ) : null}
                    {row.summary ? (
                      <span className="block text-muted-foreground-tertiary mt-0.5">{row.summary}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {toolCall.result !== undefined && (
            <details className="rounded-md border border-border-subtle/60">
              <summary className="cursor-pointer px-2 py-1 text-[10px] text-muted-foreground">
                {t('chat.projectTool.rawResult', { defaultValue: 'Raw result' })}
              </summary>
              <pre className="max-h-48 overflow-auto border-t border-border-subtle/60 p-2 font-mono text-[10px] whitespace-pre-wrap break-words">
                {fmtJson(toolCall.result)}
              </pre>
            </details>
          )}
        </div>
      );
    }

    if (name === 'coding_project_run') {
      const res = toolCall.result;
      let preview = '';
      let portLine = '';
      if (res && typeof res === 'object' && !Array.isArray(res)) {
        const o = res as Record<string, unknown>;
        if (typeof o.preview_url === 'string') preview = o.preview_url;
        if (typeof o.port === 'number') portLine = String(o.port);
        else if (typeof o.port === 'string') portLine = o.port;
      }
      return (
        <div className="space-y-2">
          {(preview || portLine) && (
            <div className="space-y-1 rounded-md border border-border-subtle/60 bg-surface-sunken/40 px-2 py-1.5 text-[11px]">
              {portLine ? (
                <div className="font-mono text-foreground">
                  {t('chat.projectTool.devServerPort', {
                    defaultValue: 'Port {{port}}',
                    port: portLine,
                  })}
                </div>
              ) : null}
              {preview ? (
                <a
                  href={preview}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="break-all text-primary-600 underline dark:text-primary-400"
                >
                  {preview}
                </a>
              ) : null}
            </div>
          )}
          <details className="rounded-md border border-border-subtle/60">
            <summary className="cursor-pointer px-2 py-1 text-[10px] text-muted-foreground">
              {t('chat.projectTool.rawResult', { defaultValue: 'Raw result' })}
            </summary>
            <pre className="max-h-48 overflow-auto border-t border-border-subtle/60 p-2 font-mono text-[10px] whitespace-pre-wrap break-words">
              {fmtJson(toolCall.result)}
            </pre>
          </details>
        </div>
      );
    }

    /* Default: other project_* / coding_project_* */
    const summaryArg =
      strArg(args, 'pattern') ||
      strArg(args, 'glob') ||
      strArg(args, 'argv') ||
      headerPath;
    return (
      <div className="space-y-2">
        {summaryArg ? (
          <div className="text-[11px] font-mono text-foreground break-all">{summaryArg}</div>
        ) : null}
        <div className="text-[10px] text-muted-foreground-tertiary">
          {t('chat.toolParameters')}
        </div>
        <pre className="max-h-40 overflow-auto rounded-md bg-surface-sunken p-2 font-mono text-[10px] whitespace-pre-wrap break-words">
          {fmtJson(args)}
        </pre>
        {toolCall.result !== undefined ? (
          <>
            <div className="text-[10px] text-muted-foreground-tertiary">{t('chat.toolResult')}</div>
            <pre className="max-h-48 overflow-auto rounded-md bg-surface-sunken p-2 font-mono text-[10px] whitespace-pre-wrap break-words">
              {fmtJson(toolCall.result)}
            </pre>
          </>
        ) : null}
      </div>
    );
  }, [name, args, toolCall, t, headerPath]);

  return (
    <div
      className={cn(
        'rounded-lg border text-xs transition-colors',
        config.border,
        config.bg,
      )}
    >
      {inlineRunChrome ? (
        <div className="group flex w-full min-w-0 items-center gap-1.5 px-2 py-1.5">
          <button
            type="button"
            className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
            onClick={() => setExpanded(!expanded)}
            aria-expanded={expanded}
          >
            <span
              className={cn(
                'flex h-3.5 w-3.5 flex-shrink-0 items-center justify-center transition-opacity duration-150',
                expanded
                  ? 'opacity-100'
                  : 'opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100',
              )}
            >
              {expanded ? (
                <ChevronDown className="h-3 w-3 text-muted-foreground-tertiary" aria-hidden />
              ) : (
                <ChevronRight className="h-3 w-3 text-muted-foreground-tertiary" aria-hidden />
              )}
            </span>
            <Wrench className="h-3 w-3 flex-shrink-0 text-muted-foreground" />
            <span className="min-w-0 flex-1 truncate font-medium text-foreground">{toolDisplayName}</span>
            {headerPath ? (
              <span className="hidden min-w-0 max-w-[28%] truncate font-mono text-[10px] text-muted-foreground-tertiary sm:inline">
                {headerPath}
              </span>
            ) : null}
            {toolCall.duration_ms !== undefined &&
              toolCall.status !== 'running' &&
              toolCall.status !== 'awaiting_user' && (
                <span className="mr-0.5 shrink-0 tabular-nums text-[10px] text-muted-foreground-tertiary">
                  {toolCall.duration_ms}ms
                </span>
              )}
          </button>
          {inlineRunChrome}
          <span className="flex-shrink-0">{config.icon}</span>
        </div>
      ) : (
        <button
          type="button"
          className="group flex w-full items-center gap-1.5 px-2 py-1.5 text-left"
          onClick={() => setExpanded(!expanded)}
          aria-expanded={expanded}
        >
          <span
            className={cn(
              'flex h-3.5 w-3.5 flex-shrink-0 items-center justify-center transition-opacity duration-150',
              expanded
                ? 'opacity-100'
                : 'opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100',
            )}
          >
            {expanded ? (
              <ChevronDown className="h-3 w-3 text-muted-foreground-tertiary" aria-hidden />
            ) : (
              <ChevronRight className="h-3 w-3 text-muted-foreground-tertiary" aria-hidden />
            )}
          </span>
          <Wrench className="h-3 w-3 flex-shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1 truncate font-medium text-foreground">{toolDisplayName}</span>
          {headerPath ? (
            <span className="hidden sm:inline max-w-[45%] truncate font-mono text-[10px] text-muted-foreground-tertiary">
              {headerPath}
            </span>
          ) : null}
          {toolCall.duration_ms !== undefined &&
            toolCall.status !== 'running' &&
            toolCall.status !== 'awaiting_user' && (
              <span className="mr-0.5 shrink-0 tabular-nums text-[10px] text-muted-foreground-tertiary">
                {toolCall.duration_ms}ms
              </span>
            )}
          {config.icon}
        </button>
      )}

      {expanded && <div className="space-y-2 px-2 pb-2 border-t border-border-subtle/40 pt-2">{body}</div>}

      {toolCall.error && (
        <div className="px-2 pb-2">
          <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-red-500">
            {t('chat.toolError')}
          </div>
          <div className="rounded-md bg-red-50 p-2 dark:bg-red-900/20">
            <pre className="whitespace-pre-wrap font-mono text-[11px] text-red-600 dark:text-red-400">
              {toolCall.error}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
