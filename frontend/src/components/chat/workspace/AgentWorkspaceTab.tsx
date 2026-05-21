import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import {
  Brackets,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ClipboardCopy,
  Code2,
  Copy,
  Eye,
  FileCode2,
  FileText,
  Image as ImageIcon,
  Loader2,
  Pencil,
  Play,
  WrapText,
  XCircle,
} from 'lucide-react';
import { CodeBlock } from '@/components/common/CodeBlock';
import { Badge, Button, Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui';
import { ChatImage } from '@/components/chat/media/ChatImage';
import { cn } from '@/lib/utils';
import { getFileExtensionIcon } from './artifactIcon';
import { EMPTY_MESSAGE_LIST } from '@/lib/emptyChatMessages';
import {
  collectProjectPathsWithOps,
  collectActivitySummary,
  resolvePathPreview,
  type PathOperation,
  type PathWithOperation,
  type AgentActivityEntry,
} from '@/lib/projectToolEnvelope';
import { pickCanvasHtmlPreview } from '@/lib/canvasStreamPreview';
import { pickCodeExecutionSourcePreview } from '@/lib/codeExecutionStreamPreview';
import {
  extractNestedPreviewText,
  languageForNestedPreview,
} from '@/lib/nestedAgentStreamPreview';
import { formatAgentPathLabel } from '@/lib/agentPathDisplay';
import { collectAgentImageArtifacts, type AgentImageArtifact } from '@/lib/agentImageArtifacts';
import { useChatStore } from '@/stores/chat';
import { useCodeArtifactStore, type CodeArtifactEntry, type CodeArtifactKind } from '@/stores/codeArtifact';
import { extToLanguage } from '@/pages/FolderPage/project/extToLanguage';
import type { ToolCall } from '@/types/chat';
import { AgentWorkspaceCodeExecutionPanel } from './AgentWorkspaceCodeExecutionPanel';
import { AgentWorkspaceTerminal } from './AgentWorkspaceTerminal';

const EMPTY_CODE_ARTIFACT_IDS: string[] = [];

const OP_ICONS: Record<PathOperation, typeof Eye> = {
  read: Eye,
  write: Pencil,
  edit: Pencil,
  execute: Play,
  unknown: FileText,
};

const OP_LABELS: Record<PathOperation, string> = {
  read: 'R',
  write: 'W',
  edit: 'E',
  execute: 'X',
  unknown: '?',
};

const OP_COLORS: Record<PathOperation, string> = {
  read: 'bg-sky-500/15 text-sky-600 dark:text-sky-400',
  write: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  edit: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  execute: 'bg-violet-500/15 text-violet-600 dark:text-violet-400',
  unknown: 'bg-zinc-500/15 text-zinc-500',
};

export function AgentWorkspaceTab() {
  const { t } = useTranslation();
  const currentSessionId = useChatStore((s) => s.currentSessionId);
  const messages = useChatStore((s) =>
    currentSessionId ? s.messages[currentSessionId] ?? EMPTY_MESSAGE_LIST : EMPTY_MESSAGE_LIST,
  );

  // --- Derived data ---

  const pathsWithOps = useMemo(() => collectProjectPathsWithOps(messages), [messages]);
  const activity = useMemo(() => collectActivitySummary(messages), [messages]);
  const imageArtifacts = useMemo(() => collectAgentImageArtifacts(messages), [messages]);
  const codeArtifactEntries = useCodeArtifactStore((s) => s.entries);
  const codeArtifactIds = useCodeArtifactStore((s) =>
    currentSessionId
      ? (s.bySession[currentSessionId] ?? EMPTY_CODE_ARTIFACT_IDS)
      : EMPTY_CODE_ARTIFACT_IDS,
  );
  const codeArtifacts = useMemo(
    () =>
      codeArtifactIds
        .map((id) => codeArtifactEntries[id])
        .filter((entry): entry is CodeArtifactEntry => Boolean(entry)),
    [codeArtifactEntries, codeArtifactIds],
  );

  const pathsKey = useMemo(
    () => pathsWithOps.map((p) => p.path).join('\u0001'),
    [pathsWithOps],
  );

  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [wordWrap, setWordWrap] = useState(false);
  const [activityOpen, setActivityOpen] = useState(true);
  const [terminalCollapsed, setTerminalCollapsed] = useState(true);

  useEffect(() => {
    if (pathsWithOps.length === 0) {
      setSelectedPath(null);
      return;
    }
    setSelectedPath((prev) => {
      if (prev && pathsWithOps.some((p) => p.path === prev)) return prev;
      return pathsWithOps[pathsWithOps.length - 1]?.path ?? null;
    });
  }, [pathsKey]);

  const preview = useMemo(() => {
    if (!selectedPath) return { kind: 'none' as const, text: '' };
    return resolvePathPreview(messages, selectedPath);
  }, [messages, selectedPath]);

  const selectedOp = useMemo(
    () => pathsWithOps.find((p) => p.path === selectedPath)?.operation ?? 'unknown',
    [pathsWithOps, selectedPath],
  );

  const canvasToolCall = useMemo((): ToolCall | null => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const m = messages[i];
      if (m?.role !== 'assistant') continue;
      for (const tc of m.toolCalls ?? []) {
        if (tc?.name !== 'canvas_publish') continue;
        if (tc.status === 'success') continue;
        if (
          tc.status === 'running' ||
          tc.status === 'awaiting_user' ||
          tc.status === 'error' ||
          (typeof tc.argumentsRaw === 'string' && tc.argumentsRaw.length > 0)
        ) {
          return tc;
        }
      }
    }
    return null;
  }, [messages]);

  const runningCodingAgent = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const m = messages[i];
      if (m?.role !== 'assistant') continue;
      for (const tc of m.toolCalls ?? []) {
        if (tc?.name === 'coding_agent' && (tc.status === 'running' || tc.status === 'pending')) {
          return true;
        }
      }
    }
    return false;
  }, [messages]);

  const canvasHtmlPreview = useMemo(() => {
    if (!canvasToolCall) return '';
    const partial =
      canvasToolCall.arguments && typeof canvasToolCall.arguments === 'object'
        ? canvasToolCall.arguments
        : {};
    return pickCanvasHtmlPreview(canvasToolCall.argumentsRaw ?? '', partial);
  }, [canvasToolCall]);

  /** Latest `code_execution` in the thread (including completed) so the panel persists. */
  const latestCodeExecutionToolCall = useMemo((): ToolCall | null => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      const m = messages[i];
      if (m?.role !== 'assistant') continue;
      const tcs = m.toolCalls ?? [];
      for (let j = tcs.length - 1; j >= 0; j -= 1) {
        const tc = tcs[j];
        if (tc?.name === 'code_execution') return tc;
      }
    }
    return null;
  }, [messages]);

  const codeExecutionSourcePreview = useMemo(() => {
    if (!latestCodeExecutionToolCall) return '';
    const partial =
      latestCodeExecutionToolCall.arguments && typeof latestCodeExecutionToolCall.arguments === 'object'
        ? latestCodeExecutionToolCall.arguments
        : {};
    return pickCodeExecutionSourcePreview(
      latestCodeExecutionToolCall.argumentsRaw ?? '',
      partial,
    );
  }, [latestCodeExecutionToolCall]);

  const lineCount = useMemo(
    () => (preview.text ? preview.text.split('\n').length : 0),
    [preview.text],
  );

  const showCodePreview =
    Boolean(selectedPath) && preview.kind !== 'none' && Boolean(preview.text);
  const showNoPreviewLink =
    !canvasToolCall &&
    !latestCodeExecutionToolCall &&
    Boolean(selectedPath) &&
    (!preview.text || preview.kind === 'none');

  const activitySummaryText = useMemo(() => {
    const edits = activity.filter((a) => a.operation === 'write' || a.operation === 'edit').length;
    const reads = activity.filter((a) => a.operation === 'read').length;
    const execs = activity.filter((a) => a.operation === 'execute').length;
    const parts: string[] = [];
    if (edits > 0) parts.push(`${edits} ${t('chat.workspace.agent.modified', { defaultValue: 'modified' })}`);
    if (reads > 0) parts.push(`${reads} ${t('chat.workspace.agent.readOps', { defaultValue: 'read' })}`);
    if (execs > 0) parts.push(`${execs} ${t('chat.workspace.agent.executions', { defaultValue: 'executions' })}`);
    return parts.join(', ');
  }, [activity, t]);

  // --- Empty state ---

  if (
    pathsWithOps.length === 0 &&
    activity.length === 0 &&
    !runningCodingAgent &&
    !canvasToolCall &&
    !latestCodeExecutionToolCall
  ) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
        <div className="flex size-12 items-center justify-center rounded-xl bg-surface-sunken/60 border border-border-subtle/40">
          <FileCode2 className="size-5 text-muted-foreground/50" />
        </div>
        <p className="max-w-[220px] text-xs leading-relaxed text-muted-foreground">
          {t('chat.workspace.agent.pickPath', {
            defaultValue: 'Code activity will appear here once the agent starts working on files.',
          })}
        </p>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-2.5 chat-sessions-scroll">
      {/* Running indicator */}
      {runningCodingAgent && (
        <div className="flex items-center gap-2.5 rounded-lg border border-primary/20 bg-primary/[0.06] px-3 py-2.5">
          <span className="relative flex size-2">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary/60" />
            <span className="relative inline-flex size-2 rounded-full bg-primary" />
          </span>
          <span className="text-[11px] font-medium text-primary/90">
            {t('chat.workspace.agent.runningHint', { defaultValue: 'Coding agent running…' })}
          </span>
          <Loader2 className="ml-auto size-3 shrink-0 animate-spin text-primary/50" aria-hidden />
        </div>
      )}

      {/* Activity Summary */}
      {activity.length > 0 && (
        <ActivitySummarySection
          activity={activity}
          summaryText={activitySummaryText}
          open={activityOpen}
          onToggle={() => setActivityOpen((v) => !v)}
        />
      )}

      {/* Code Artifacts */}
      {codeArtifacts.length > 0 && <CodeArtifactsSection artifacts={codeArtifacts} />}

      {/* File List */}
      {pathsWithOps.length > 0 && (
        <FileListSection
          paths={pathsWithOps}
          selectedPath={selectedPath}
          onSelect={setSelectedPath}
        />
      )}

      {/* Canvas HTML Live Preview */}
      {canvasToolCall && (
        <div className="flex flex-col rounded-lg border border-border-subtle/50 bg-surface-sunken/40 overflow-hidden">
          <div className="px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            {t('chat.workspace.agent.canvasStreamTitle', { defaultValue: 'Canvas HTML (live)' })}
          </div>
          <div className="max-h-[30vh] overflow-auto">
            <CodeBlock
              code={canvasHtmlPreview || '…'}
              language="html"
              showLineNumbers={false}
              showLanguage={false}
              showCopyButton
              className="border-0 rounded-none text-[11px]"
            />
          </div>
        </div>
      )}

      {/* Code Preview */}
      {showCodePreview && (
        <div className="flex flex-col rounded-lg border border-border-subtle/50 bg-surface-sunken/40 overflow-hidden">
          {/* Preview header */}
          <div className="flex items-center gap-2 px-3 py-2">
            <Badge variant={selectedOp === 'read' ? 'info' : selectedOp === 'execute' ? 'primary' : 'warning'} size="sm" className="shrink-0 text-[9px] uppercase font-bold">
              {OP_LABELS[selectedOp]}
            </Badge>
            <span
              className="min-w-0 flex-1 truncate font-mono text-[11px] text-muted-foreground"
              title={selectedPath ?? ''}
            >
              {selectedPath}
            </span>
            <span className="text-[10px] tabular-nums text-muted-foreground/60">
              {lineCount} line{lineCount !== 1 ? 's' : ''}
            </span>
          </div>

          {/* Action bar */}
          <div className="flex items-center gap-0.5 border-t border-border-subtle/40 bg-surface/30 px-2 py-1">
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className={cn('h-6 w-6', wordWrap && 'bg-primary/10 text-primary')}
                    aria-label={t('chat.workspace.agent.wordWrap', { defaultValue: 'Toggle word wrap' })}
                    aria-pressed={wordWrap}
                    onClick={() => setWordWrap((v) => !v)}
                  >
                    <WrapText className="h-3 w-3" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="bottom">{t('chat.workspace.agent.wordWrap', { defaultValue: 'Toggle word wrap' })}</TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    aria-label={t('chat.workspace.agent.copyContents', { defaultValue: 'Copy contents' })}
                    onClick={() => void navigator.clipboard?.writeText(preview.text)}
                  >
                    <ClipboardCopy className="h-3 w-3" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="bottom">{t('chat.workspace.agent.copyContents', { defaultValue: 'Copy contents' })}</TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    aria-label={t('chat.workspace.agent.copyPath', { defaultValue: 'Copy path' })}
                    onClick={() =>
                      selectedPath ? void navigator.clipboard?.writeText(selectedPath) : undefined
                    }
                  >
                    <Copy className="h-3 w-3" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="bottom">{t('chat.workspace.agent.copyPath', { defaultValue: 'Copy path' })}</TooltipContent>
              </Tooltip>
            </TooltipProvider>

            {(preview.kind === 'write' || preview.kind === 'edit') && (
              <Badge variant="warning" size="sm" className="ml-1">
                {preview.kind === 'write'
                  ? t('chat.workspace.agent.badgeFromWrite', { defaultValue: 'from write' })
                  : t('chat.workspace.agent.badgeFromEdit', { defaultValue: 'from edit' })}
              </Badge>
            )}
          </div>

          {/* Code body */}
          <div className="max-h-[45vh] overflow-auto">
            <CodeBlock
              code={preview.text}
              language={extToLanguage(selectedPath ?? '')}
              showLineNumbers
              showLanguage={false}
              showCopyButton={false}
              className={cn('border-0 rounded-none', wordWrap && '[&_pre]:whitespace-pre-wrap')}
            />
          </div>
        </div>
      )}

      {/* No-preview fallback */}
      {showNoPreviewLink && (
        <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-border-subtle/50 bg-surface-sunken/40 p-6 text-center">
          <p className="max-w-sm text-[12px] leading-relaxed text-muted-foreground">
            {t('chat.workspace.agent.noPreview', {
              defaultValue: 'No preview available for this file. Open the Folders page to browse.',
            })}
          </p>
          <Link
            to="/folders"
            className="text-[12px] font-medium text-primary underline-offset-4 hover:underline"
          >
            {t('chat.workspace.agent.openFoldersPage', { defaultValue: 'Open Folders' })}
          </Link>
        </div>
      )}

      {/* Image Artifacts */}
      {imageArtifacts.length > 0 && <ImageArtifactsSection images={imageArtifacts} />}

      {/* Nested coding-agent live preview (SSE) */}
      <NestedCodingLivePreviewSection />

      {latestCodeExecutionToolCall && (
        <AgentWorkspaceCodeExecutionPanel
          toolCall={latestCodeExecutionToolCall}
          sourceText={codeExecutionSourcePreview}
        />
      )}

      {/* Terminal */}
      <AgentWorkspaceTerminal
        messages={messages}
        collapsed={terminalCollapsed}
        onToggle={() => setTerminalCollapsed((v) => !v)}
      />
    </div>
  );
}

// ─── Nested coding-agent live preview ─────────────────────────────────

function NestedCodingLivePreviewSection() {
  const { t } = useTranslation();
  const currentSessionId = useChatStore((s) => s.currentSessionId);
  const nested = useChatStore((s) =>
    currentSessionId ? (s.nestedAgentPreviewBySession[currentSessionId] ?? null) : null,
  );
  const [open, setOpen] = useState(true);

  if (!nested) return null;

  const previewText = extractNestedPreviewText(
    nested.toolName,
    nested.argumentsRaw,
    nested.argumentsPartial,
  );
  const lang = languageForNestedPreview(nested.toolName, nested.argumentsPartial);
  const pathHint =
    typeof nested.argumentsPartial?.path === 'string' ? nested.argumentsPartial.path : undefined;

  return (
    <div className="flex flex-col rounded-lg border border-border-subtle/50 bg-surface-sunken/40 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-surface/40"
      >
        {open ? (
          <ChevronDown className="size-3 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-3 shrink-0 text-muted-foreground" />
        )}
        <Brackets className="size-3.5 shrink-0 text-muted-foreground/70" aria-hidden />
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          {t('chat.workspace.agent.nestedCodingPreviewTitle', {
            defaultValue: 'Nested agent (live)',
          })}
        </span>
        <span className="ml-auto truncate font-mono text-[10px] tabular-nums text-muted-foreground/70">
          {nested.toolName}
        </span>
      </button>
      {open && (
        <>
          {pathHint ? (
            <div className="border-t border-border-subtle/40 px-3 py-1 font-mono text-[10px] text-muted-foreground truncate">
              {pathHint}
            </div>
          ) : null}
          <div className="max-h-[38vh] overflow-auto border-t border-border-subtle/40">
            <CodeBlock
              code={previewText || '…'}
              language={lang}
              showLineNumbers={nested.toolName !== 'project_apply_patch'}
              showLanguage={false}
              showCopyButton
              className="border-0 rounded-none text-[11px]"
            />
          </div>
        </>
      )}
    </div>
  );
}

// ─── Activity Summary ─────────────────────────────────────────────────

function ActivitySummarySection({
  activity,
  summaryText,
  open,
  onToggle,
}: {
  activity: AgentActivityEntry[];
  summaryText: string;
  open: boolean;
  onToggle: () => void;
}) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col rounded-lg border border-border-subtle/50 bg-surface-sunken/40 overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="flex items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-surface/40"
      >
        {open ? (
          <ChevronDown className="size-3 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-3 shrink-0 text-muted-foreground" />
        )}
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          {t('chat.workspace.agent.activityTitle', { defaultValue: 'Activity' })}
        </span>
        {summaryText && (
          <span className="ml-auto text-[10px] tabular-nums text-muted-foreground/60">
            {summaryText}
          </span>
        )}
      </button>
      {open && (
        <div className="max-h-[min(40vh,280px)] overflow-y-auto border-t border-border-subtle/40">
          <ul className="py-1 space-y-px">
            {activity.map((entry, i) => {
              const Icon = OP_ICONS[entry.operation];
              return (
                <li
                  key={`${entry.tool}-${i}`}
                  className="flex items-center gap-2 rounded-md px-3 py-1.5 text-[11px] text-foreground/80 transition-colors hover:bg-surface/30"
                >
                  <Icon className={cn('size-3 shrink-0', OP_COLORS[entry.operation].split(' ').slice(1).join(' '))} aria-hidden />
                  <span className="min-w-0 flex-1 truncate">{entry.summary}</span>
                  <span
                    className={cn(
                      'shrink-0 rounded px-1 py-px text-[8px] font-bold uppercase leading-none',
                      OP_COLORS[entry.operation],
                    )}
                  >
                    {OP_LABELS[entry.operation]}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

// ─── File List ────────────────────────────────────────────────────────

function FileListSection({
  paths,
  selectedPath,
  onSelect,
}: {
  paths: PathWithOperation[];
  selectedPath: string | null;
  onSelect: (path: string) => void;
}) {
  const { t } = useTranslation();
  const [filesOpen, setFilesOpen] = useState(true);

  const fileCountText = useMemo(() => {
    const n = paths.length;
    return t('chat.workspace.agent.fileCount', { count: n, defaultValue: `${n} file${n !== 1 ? 's' : ''}` });
  }, [paths.length, t]);

  return (
    <div className="flex flex-col rounded-lg border border-border-subtle/50 bg-surface-sunken/40 overflow-hidden">
      <button
        type="button"
        onClick={() => setFilesOpen((v) => !v)}
        className="flex items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-surface/40"
      >
        {filesOpen ? (
          <ChevronDown className="size-3 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-3 shrink-0 text-muted-foreground" />
        )}
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          {t('chat.workspace.agent.filesTitle', { defaultValue: 'Files' })}
        </span>
        <span className="ml-auto text-[10px] tabular-nums text-muted-foreground/60">
          {fileCountText}
        </span>
      </button>
      {filesOpen && (
        <div className="max-h-[min(40vh,280px)] overflow-y-auto border-t border-border-subtle/40">
          <ul className="flex flex-col gap-0.5 p-1">
            {paths.map(({ path, operation }) => {
              const active = path === selectedPath;
              const fileName = formatAgentPathLabel(path);
              return (
                <li key={path}>
                  <button
                    type="button"
                    onClick={() => onSelect(path)}
                    title={path}
                    className={cn(
                      'flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] transition-colors',
                      active
                        ? 'bg-surface text-foreground shadow-sm ring-1 ring-primary/20'
                        : 'text-muted-foreground hover:bg-surface-sunken hover:text-foreground',
                    )}
                  >
                    <span className="flex-shrink-0">
                      {getFileExtensionIcon(fileName)}
                    </span>
                    <span className="min-w-0 flex-1 truncate font-mono">{fileName}</span>
                    <span
                      className={cn(
                        'shrink-0 rounded px-1 py-px text-[8px] font-bold uppercase leading-none',
                        OP_COLORS[operation],
                      )}
                    >
                      {OP_LABELS[operation]}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

// ─── Code Artifacts ───────────────────────────────────────────────────

const KIND_LABELS: Record<CodeArtifactKind, string> = {
  execute: 'chat.workspace.agent.codeArtifact.kinds.execute',
  file_write: 'chat.workspace.agent.codeArtifact.kinds.file_write',
  file_edit: 'chat.workspace.agent.codeArtifact.kinds.file_edit',
  file_patch: 'chat.workspace.agent.codeArtifact.kinds.file_patch',
  snippet: 'chat.workspace.agent.codeArtifact.kinds.snippet',
};

const KIND_COLORS: Record<CodeArtifactKind, string> = {
  execute: 'bg-violet-500/15 text-violet-600 dark:text-violet-400',
  file_write: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  file_edit: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  file_patch: 'bg-sky-500/15 text-sky-600 dark:text-sky-400',
  snippet: 'bg-zinc-500/15 text-zinc-500',
};

function CodeArtifactsSection({ artifacts }: { artifacts: CodeArtifactEntry[] }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(true);

  return (
    <div className="flex flex-col rounded-lg border border-border-subtle/50 bg-surface-sunken/40 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-surface/40"
      >
        {open ? (
          <ChevronDown className="size-3 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-3 shrink-0 text-muted-foreground" />
        )}
        <Code2 className="size-3.5 shrink-0 text-muted-foreground/70" aria-hidden />
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          {t('chat.workspace.agent.codeArtifact.title', { defaultValue: 'Code Artifacts' })}
        </span>
        <span className="ml-auto text-[10px] tabular-nums text-muted-foreground/60">
          {artifacts.length}
        </span>
      </button>
      {open && (
        <div className="max-h-[min(40vh,280px)] overflow-y-auto border-t border-border-subtle/40">
          <ul className="py-1 space-y-px">
            {artifacts.map((entry) => (
              <li
                key={entry.artifactId}
                className="flex items-center gap-2 rounded-md px-3 py-1.5 text-[11px] text-foreground/80 transition-colors hover:bg-surface/30"
              >
                <span
                  className={cn(
                    'shrink-0 rounded px-1 py-px text-[8px] font-bold uppercase leading-none',
                    KIND_COLORS[entry.kind] ?? KIND_COLORS.snippet,
                  )}
                >
                  {t(KIND_LABELS[entry.kind] ?? KIND_LABELS.snippet, {
                    defaultValue: entry.kind,
                  })}
                </span>
                <span className="min-w-0 flex-1 truncate font-mono">
                  {entry.targetPath ?? entry.originTool}
                </span>
                <span className="shrink-0 text-[9px] text-muted-foreground/60">
                  {entry.language}
                </span>
                {entry.syntaxValid === true && (
                  <CheckCircle2 className="size-3 shrink-0 text-emerald-500" aria-label={
                    t('chat.workspace.agent.codeArtifact.syntaxValid', { defaultValue: 'Syntax OK' })
                  } />
                )}
                {entry.syntaxValid === false && (
                  <XCircle className="size-3 shrink-0 text-rose-500" aria-label={
                    t('chat.workspace.agent.codeArtifact.syntaxError', { defaultValue: 'Syntax Error' })
                  } />
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ─── Image Artifacts ──────────────────────────────────────────────────

function ImageArtifactsSection({ images }: { images: AgentImageArtifact[] }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(true);

  return (
    <div className="flex flex-col rounded-lg border border-border-subtle/50 bg-surface-sunken/40 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-surface/40"
      >
        {open ? (
          <ChevronDown className="size-3 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-3 shrink-0 text-muted-foreground" />
        )}
        <ImageIcon className="size-3.5 shrink-0 text-muted-foreground/70" aria-hidden />
        <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          {t('chat.workspace.agent.imagesTitle', {
            defaultValue: `Images (${images.length})`,
            count: images.length,
          })}
        </span>
      </button>
      {open && (
        <div className="grid grid-cols-2 gap-1.5 border-t border-border-subtle/40 px-2.5 py-2.5">
          {images.map((img) => (
            <div
              key={img.id}
              className="group overflow-hidden rounded-md border border-border-subtle/40 bg-black/5 dark:bg-white/5"
            >
              <div className="aspect-square overflow-hidden">
                <ChatImage
                  src={img.previewUrl}
                  alt={img.fileName ?? 'Generated image'}
                  className="h-full w-full rounded-none border-0 bg-transparent object-cover shadow-none"
                />
              </div>
              <div className="space-y-0.5 border-t border-border-subtle/40 px-2 py-1.5">
                {img.fileName && (
                  <div className="truncate text-[10px] text-muted-foreground" title={img.fileName}>
                    {img.fileName}
                  </div>
                )}
                {img.sha256 && (
                  <div className="font-mono text-[9px] text-muted-foreground/70">
                    sha256:{img.sha256.slice(0, 12)}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
