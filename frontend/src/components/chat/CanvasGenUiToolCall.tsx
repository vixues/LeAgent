import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Check,
  ChevronDown,
  ChevronRight,
  LayoutGrid,
  Loader2,
  AlertCircle,
  Sparkles,
  MessageCircleQuestion,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { redactLargeRawToolArguments } from '@/lib/toolCallArgsDisplay';
import {
  pickCanvasPreviewPathFromMetadata,
} from '@/lib/previewUrl';
import type { ToolCall } from '@/types/chat';
import { useArtifactStore } from '@/stores/artifact';
import { GenUiInline } from '@/components/canvas/GenUiInline';

const GEN_UI_TOOL_NAMES = new Set(['emit_ui_tree', 'emit_ui_patch', 'canvas_publish']);

function countGenUiNodes(node: { children?: unknown[] } | null | undefined): number {
  if (!node) return 0;
  let n = 1;
  const ch = node.children;
  if (Array.isArray(ch)) {
    for (const c of ch) {
      if (c && typeof c === 'object') n += countGenUiNodes(c as { children?: unknown[] });
    }
  }
  return n;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return null;
    try {
      const parsed = JSON.parse(trimmed) as unknown;
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>;
      }
    } catch {
      return null;
    }
  }
  return null;
}

function summarizeCanvasPublishResult(result: unknown): {
  title?: string;
  mode?: string;
  previewPath?: string;
  canvasId?: string;
} {
  const d = asRecord(result);
  if (!d) return {};
  // Live SSE stores structured `data`; history may nest under `data` or use camelCase.
  const nested = asRecord(d.data);
  const source = nested ?? d;
  const canvasIdRaw = source.canvas_id ?? source.canvasId;
  return {
    title: typeof source.title === 'string' ? source.title : undefined,
    mode:
      typeof source.content_type === 'string'
        ? source.content_type
        : typeof source.contentType === 'string'
          ? source.contentType
          : undefined,
    previewPath: pickCanvasPreviewPathFromMetadata(source) ?? undefined,
    canvasId: typeof canvasIdRaw === 'string' && canvasIdRaw ? canvasIdRaw : undefined,
  };
}

function summarizeEmitUiTreeResult(result: unknown): { nodeCount?: number } {
  if (!result || typeof result !== 'object') return {};
  const d = result as Record<string, unknown>;
  const payload = d.payload;
  if (!payload || typeof payload !== 'object') return {};
  const tree = (payload as Record<string, unknown>).tree;
  if (!tree || typeof tree !== 'object') return {};
  const root = (tree as Record<string, unknown>).root;
  if (!root || typeof root !== 'object') return {};
  return { nodeCount: countGenUiNodes(root as { children?: unknown[] }) };
}

function genUiToolStatusIcon(status: ToolCall['status']) {
  switch (status) {
    case 'pending':
      return (
        <Loader2 className="h-3.5 w-3.5 text-muted-foreground-tertiary animate-spin" />
      );
    case 'running':
      return <Loader2 className="h-3.5 w-3.5 text-sky-500 animate-spin" />;
    case 'awaiting_user':
      return (
        <MessageCircleQuestion
          className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400"
          aria-hidden
        />
      );
    case 'success':
      return <Check className="h-3.5 w-3.5 text-mint-500" />;
    case 'error':
      return <AlertCircle className="h-3.5 w-3.5 text-red-500" />;
  }
}

export function isGenerativeCanvasTool(name: string): boolean {
  return GEN_UI_TOOL_NAMES.has(name);
}

interface CanvasGenUiToolCallProps {
  toolCall: ToolCall;
  sessionId: string | null | undefined;
  messageId: string;
  /** When true, render streamed Gen UI under this row (last successful emit_ui_tree only). */
  showGenUiInline?: boolean;
}

export function CanvasGenUiToolCall({
  toolCall,
  sessionId,
  messageId,
  showGenUiInline = false,
}: CanvasGenUiToolCallProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);

  const displayArguments = useMemo(
    () => redactLargeRawToolArguments(toolCall.arguments, t),
    [toolCall.arguments, t],
  );

  const formatValue = (value: unknown): string =>
    typeof value === 'string' ? value : JSON.stringify(value, null, 2);

  const runningLabel = useMemo(() => {
    if (toolCall.name === 'canvas_publish') {
      return t('chat.genUiPublishingCanvas', { defaultValue: 'Publishing canvas…' });
    }
    if (toolCall.name === 'emit_ui_patch') {
      return t('chat.genUiApplyingPatch', { defaultValue: 'Updating UI…' });
    }
    return t('chat.genUiBuildingUi', { defaultValue: 'Building UI…' });
  }, [toolCall.name, t]);

  const successSummary = useMemo(() => {
    if (toolCall.status !== 'success' || toolCall.result === undefined) return null;
    if (toolCall.name === 'canvas_publish') {
      const s = summarizeCanvasPublishResult(toolCall.result);
      return {
        line: s.title
          ? t('chat.genUiCanvasPublished', {
              defaultValue: 'Canvas published: {{title}}',
              title: s.title,
            })
          : t('chat.genUiCanvasPublishedShort', { defaultValue: 'Canvas published' }),
        mode: s.mode,
      };
    }
    if (toolCall.name === 'emit_ui_tree') {
      const { nodeCount } = summarizeEmitUiTreeResult(toolCall.result);
      if (nodeCount != null) {
        return {
          line: t('chat.genUiTreeEmitted', {
            defaultValue: 'Generative UI ready ({{count}} nodes)',
            count: nodeCount,
          }),
        };
      }
      return { line: t('chat.genUiTreeEmittedShort', { defaultValue: 'Generative UI ready' }) };
    }
    if (toolCall.name === 'emit_ui_patch') {
      return { line: t('chat.genUiPatchApplied', { defaultValue: 'UI patch applied' }) };
    }
    return null;
  }, [toolCall.name, toolCall.status, toolCall.result, t]);

  const publishSummary = useMemo(
    () =>
      toolCall.name === 'canvas_publish'
        ? summarizeCanvasPublishResult(toolCall.result)
        : {},
    [toolCall.name, toolCall.result],
  );

  // Canvas companion SSE stores preview on the artifact; tool result may be a
  // truncated JSON string without a top-level preview_path after reload.
  const htmlArtifact = useArtifactStore((s) => {
    const htmlArts = Object.values(s.artifacts).filter((a) => a.type === 'html');
    const byMessage = htmlArts.find((a) => a.messageId === messageId);
    if (byMessage) return byMessage;
    const canvasId = publishSummary.canvasId;
    if (canvasId) {
      const byCanvas = htmlArts.find(
        (a) =>
          a.metadata?.canvasId === canvasId ||
          a.metadata?.canvas_id === canvasId,
      );
      if (byCanvas) return byCanvas;
    }
    if (sessionId) {
      const inSession = htmlArts.filter((a) => a.sessionId === sessionId);
      if (inSession.length === 1) return inSession[0];
    }
    return undefined;
  });

  const artifactPreviewPath = htmlArtifact
    ? pickCanvasPreviewPathFromMetadata(
        htmlArtifact.metadata as Record<string, unknown> | undefined,
      )
    : null;

  const publishPreviewPath = publishSummary.previewPath ?? artifactPreviewPath ?? undefined;

  const canvasTitle =
    (typeof htmlArtifact?.title === 'string' && htmlArtifact.title.trim()) ||
    (typeof publishSummary.title === 'string' && publishSummary.title.trim()) ||
    '';

  const canOpenCanvas =
    toolCall.name === 'canvas_publish' && Boolean(htmlArtifact || publishPreviewPath);

  const openCanvasLabel = canvasTitle
    ? t('chat.genUiOpenCanvasNamed', {
        defaultValue: 'Open canvas: {{title}}',
        title: canvasTitle,
      })
    : t('chat.genUiOpenCanvas', { defaultValue: 'Open canvas' });

  const openCanvas = () => {
    if (htmlArtifact) {
      useArtifactStore.getState().openTab(htmlArtifact.id);
      return;
    }
    const store = useArtifactStore.getState();
    const match = Object.values(store.artifacts).find(
      (a) => a.messageId === messageId && a.type === 'html',
    );
    if (match) {
      store.openTab(match.id);
      return;
    }
    // Recreate a panel tab from the tool result when the in-memory artifact is gone.
    if (publishPreviewPath) {
      const id =
        publishSummary.canvasId && publishSummary.canvasId.length > 0
          ? `canvas-${publishSummary.canvasId}`
          : `canvas-${messageId}`;
      store.addArtifact({
        id,
        type: 'html',
        title: canvasTitle || 'Canvas',
        content: '',
        createdAt: new Date().toISOString(),
        sessionId: sessionId ?? undefined,
        messageId,
        metadata: {
          previewPath: publishPreviewPath,
          canvasId: publishSummary.canvasId,
          trust: 'hosted',
          contentType: publishSummary.mode ?? 'html',
        },
      });
      store.openTab(id);
    }
  };

  const statusIcon = genUiToolStatusIcon(toolCall.status);
  const showMeta =
    (toolCall.status === 'pending' || toolCall.status === 'running') ||
    (toolCall.status === 'success' && successSummary) ||
    (toolCall.status === 'error' && toolCall.error);

  const iconButtonClass = cn(
    'flex h-7 w-7 shrink-0 items-center justify-center rounded-md',
    'text-muted-foreground transition-colors',
    'hover:bg-muted/40 hover:text-foreground',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40 focus-visible:ring-offset-2 focus-visible:ring-offset-background',
  );

  return (
    <div className="space-y-1.5">
      <div className="flex min-h-7 min-w-0 items-center gap-1">
        <button
          type="button"
          className={cn(iconButtonClass, !expanded && 'opacity-40')}
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          aria-label={t('chat.toolStrip.toggleDetailsAria')}
        >
          {expanded ? (
            <ChevronDown
              className="h-3.5 w-3.5 text-muted-foreground-tertiary flex-shrink-0"
              aria-hidden
            />
          ) : (
            <ChevronRight
              className="h-3.5 w-3.5 text-muted-foreground-tertiary flex-shrink-0"
              aria-hidden
            />
          )}
        </button>

        <button
          type="button"
          className={cn(
            'flex h-7 min-w-0 max-w-[14rem] items-center gap-1 rounded-md px-1.5 py-1 text-left text-xs outline-none transition-colors',
            'text-muted-foreground hover:text-foreground hover:bg-muted/40',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-400/50 focus-visible:ring-offset-2 focus-visible:ring-offset-background',
            expanded && 'bg-muted/50 text-foreground',
          )}
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          aria-pressed={expanded}
        >
          <Sparkles className="h-3 w-3 flex-shrink-0 text-sky-500" aria-hidden />
          <span className="min-w-0 flex-1 truncate font-medium text-foreground">
            {toolCall.name}
          </span>
          {toolCall.duration_ms !== undefined &&
            toolCall.status !== 'running' &&
            toolCall.status !== 'awaiting_user' && (
              <span className="mr-0.5 shrink-0 tabular-nums text-[10px] text-muted-foreground-tertiary">
                {toolCall.duration_ms}ms
              </span>
            )}
          {statusIcon}
        </button>

        {canOpenCanvas && (
          <button
            type="button"
            className={cn(
              'flex h-7 min-w-0 max-w-[16rem] items-center gap-1.5 rounded-md px-1.5 py-1 text-left text-xs outline-none transition-colors',
              'text-muted-foreground hover:text-foreground hover:bg-muted/40',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/40 focus-visible:ring-offset-2 focus-visible:ring-offset-background',
            )}
            onClick={openCanvas}
            aria-label={openCanvasLabel}
            title={openCanvasLabel}
          >
            {canvasTitle ? (
              <span className="min-w-0 truncate font-medium text-foreground">{canvasTitle}</span>
            ) : null}
            <span className="shrink-0 text-sky-600 dark:text-sky-400">
              {t('chat.genUiOpenCanvasAction', { defaultValue: 'Open' })}
            </span>
          </button>
        )}
      </div>

      {showMeta && !expanded && (
        <div className="pl-8 space-y-1">
          {(toolCall.status === 'pending' || toolCall.status === 'running') && (
            <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <LayoutGrid className="h-3 w-3 flex-shrink-0 opacity-70" />
              <span>{runningLabel}</span>
            </div>
          )}

          {toolCall.status === 'success' && successSummary && (
            <div className="space-y-0.5">
              <p className="text-[11px] font-medium text-foreground">{successSummary.line}</p>
              {successSummary.mode && (
                <p className="text-[10px] text-muted-foreground">
                  {t('chat.genUiMode', { defaultValue: 'Mode' })}: {successSummary.mode}
                </p>
              )}
            </div>
          )}

          {toolCall.status === 'error' && toolCall.error && (
            <p
              className="text-[11px] text-red-800 dark:text-red-200 line-clamp-2 break-all"
              title={toolCall.error}
            >
              {toolCall.error}
            </p>
          )}
        </div>
      )}

      {expanded && (
        <div className="no-scrollbar max-h-[min(50vh,22rem)] overflow-y-auto overscroll-contain space-y-2 px-1 py-1.5 pl-8">
          {(toolCall.status === 'pending' || toolCall.status === 'running') && (
            <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <LayoutGrid className="h-3 w-3 flex-shrink-0 opacity-70" />
              <span>{runningLabel}</span>
            </div>
          )}

          {toolCall.status === 'success' && successSummary && (
            <div className="space-y-0.5">
              <p className="text-[11px] font-medium text-foreground">{successSummary.line}</p>
              {successSummary.mode && (
                <p className="text-[10px] text-muted-foreground">
                  {t('chat.genUiMode', { defaultValue: 'Mode' })}: {successSummary.mode}
                </p>
              )}
            </div>
          )}

          <div>
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              {t('chat.toolParameters')}
            </div>
            {displayArguments === undefined ? (
              <div className="rounded-md bg-surface-sunken p-2 text-[11px] text-muted-foreground">
                {t('chat.toolArgsRawHidden', {
                  defaultValue: 'Large raw tool arguments omitted from display.',
                })}
              </div>
            ) : (
              <div className="no-scrollbar overflow-x-auto rounded-md bg-surface-sunken p-2">
                <pre className="whitespace-pre-wrap font-mono text-[11px] text-foreground">
                  {formatValue(displayArguments)}
                </pre>
              </div>
            )}
          </div>

          {toolCall.result !== undefined && (
            <div>
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                {t('chat.toolResult')}
              </div>
              <div className="no-scrollbar max-h-48 overflow-x-auto overflow-y-auto rounded-md bg-surface-sunken p-2">
                <pre className="whitespace-pre-wrap font-mono text-[11px] text-foreground">
                  {formatValue(toolCall.result)}
                </pre>
              </div>
            </div>
          )}

          {toolCall.error && (
            <div>
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
      )}

      {showGenUiInline && sessionId && (
        <GenUiInline sessionId={sessionId} messageId={messageId} className="mt-2" />
      )}
    </div>
  );
}
