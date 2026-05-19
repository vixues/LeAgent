import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Check,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  LayoutGrid,
  Loader2,
  AlertCircle,
  Sparkles,
  MessageCircleQuestion,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { redactLargeRawToolArguments } from '@/lib/toolCallArgsDisplay';
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

function summarizeCanvasPublishResult(result: unknown): {
  title?: string;
  mode?: string;
  previewPath?: string;
} {
  if (!result || typeof result !== 'object') return {};
  const d = result as Record<string, unknown>;
  return {
    title: typeof d.title === 'string' ? d.title : undefined,
    mode: typeof d.content_type === 'string' ? d.content_type : undefined,
    previewPath: typeof d.preview_path === 'string' ? d.preview_path : undefined,
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

  const statusConfig = {
    pending: {
      icon: <Loader2 className="h-4 w-4 text-muted-foreground-tertiary animate-spin" />,
      border: 'border-border-subtle',
      bg: '',
    },
    running: {
      icon: <Loader2 className="h-4 w-4 text-sky-500 animate-spin" />,
      border: 'border-sky-200 dark:border-sky-800',
      bg: 'bg-sky-50/40 dark:bg-sky-900/10',
    },
    awaiting_user: {
      icon: (
        <MessageCircleQuestion className="h-4 w-4 text-amber-600 dark:text-amber-400" aria-hidden />
      ),
      border: 'border-amber-200 dark:border-amber-800',
      bg: 'bg-amber-50/40 dark:bg-amber-900/10',
    },
    success: {
      icon: <Check className="h-4 w-4 text-mint-500" />,
      border: 'border-mint-200 dark:border-mint-800',
      bg: 'bg-mint-50/40 dark:bg-mint-900/10',
    },
    error: {
      icon: <AlertCircle className="h-4 w-4 text-red-500" />,
      border: 'border-red-200 dark:border-red-800',
      bg: 'bg-red-50/40 dark:bg-red-900/10',
    },
  };

  const config = statusConfig[toolCall.status];
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

  const openCanvasPanel = () => {
    const artifacts = useArtifactStore.getState().artifacts;
    const match = Object.values(artifacts).find(
      (a) => a.messageId === messageId && a.type === 'html',
    );
    if (match) {
      useArtifactStore.getState().openTab(match.id);
    }
  };

  const canOpenCanvas =
    toolCall.name === 'canvas_publish' &&
    toolCall.status === 'success' &&
    summarizeCanvasPublishResult(toolCall.result).previewPath;

  return (
    <div>
      <div
        className={cn(
          'rounded-xl border text-sm transition-colors',
          config.border,
          config.bg,
        )}
      >
        <button
          type="button"
          className="w-full flex items-center gap-2.5 px-3 py-2.5 text-left"
          aria-expanded={expanded}
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? (
            <ChevronDown className="h-4 w-4 text-muted-foreground-tertiary flex-shrink-0" />
          ) : (
            <ChevronRight className="h-4 w-4 text-muted-foreground-tertiary flex-shrink-0" />
          )}
          <Sparkles className="h-4 w-4 text-sky-500 flex-shrink-0" aria-hidden />
          <span className="flex-1 font-medium text-foreground text-sm">{toolCall.name}</span>
          {toolCall.duration_ms !== undefined &&
            toolCall.status !== 'running' &&
            toolCall.status !== 'awaiting_user' && (
            <span className="text-xs text-muted-foreground-tertiary mr-1 tabular-nums">
              {toolCall.duration_ms}ms
            </span>
          )}
          {config.icon}
        </button>

        {(toolCall.status === 'pending' || toolCall.status === 'running') && (
          <div className="px-3 pb-2.5 -mt-1 flex items-center gap-2 text-xs text-muted-foreground">
            <LayoutGrid className="h-3.5 w-3.5 flex-shrink-0 opacity-70" />
            <span>{runningLabel}</span>
          </div>
        )}

        {toolCall.status === 'success' && successSummary && (
          <div className="px-3 pb-2.5 -mt-1 space-y-1.5">
            <p className="text-xs text-foreground font-medium">{successSummary.line}</p>
            {successSummary.mode && (
              <p className="text-[11px] text-muted-foreground">
                {t('chat.genUiMode', { defaultValue: 'Mode' })}: {successSummary.mode}
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              {canOpenCanvas && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    openCanvasPanel();
                  }}
                  className="inline-flex items-center gap-1 text-[11px] font-medium text-sky-600 dark:text-sky-400 hover:underline"
                >
                  <ExternalLink className="h-3 w-3" />
                  {t('chat.genUiOpenInPanel', { defaultValue: 'Open in panel' })}
                </button>
              )}
            </div>
          </div>
        )}

        {toolCall.status === 'error' && toolCall.error && (
          <div className="px-3 pb-2.5 -mt-1">
            {expanded ? (
              <div
                role="alert"
                className="rounded-lg border border-red-200 dark:border-red-800 bg-red-50/80 dark:bg-red-950/30 px-2.5 py-2 text-xs text-red-800 dark:text-red-200 max-h-64 overflow-y-auto whitespace-pre-wrap break-words"
              >
                {toolCall.error}
              </div>
            ) : (
              <p
                className="rounded-lg border border-red-200/80 dark:border-red-800/80 bg-red-50/50 dark:bg-red-950/20 px-2.5 py-1.5 text-xs text-red-800 dark:text-red-200 line-clamp-2 break-all"
                title={toolCall.error}
              >
                {toolCall.error}
              </p>
            )}
          </div>
        )}

        {expanded && (
          <div className="px-3 pb-3 space-y-2.5 border-t border-border-subtle/60 pt-2.5">
            <div>
              <div className="text-xs font-semibold text-muted-foreground mb-1.5">
                {t('chat.toolParameters')}
              </div>
              {displayArguments === undefined ? (
                <div className="rounded-lg bg-surface-sunken p-2.5 text-xs text-muted-foreground">
                  {t('chat.toolArgsRawHidden', {
                    defaultValue: 'Large raw tool arguments omitted from display.',
                  })}
                </div>
              ) : (
                <div className="bg-surface-sunken rounded-lg p-2.5 overflow-x-auto">
                  <pre className="text-xs text-foreground whitespace-pre-wrap font-mono">
                    {formatValue(displayArguments)}
                  </pre>
                </div>
              )}
            </div>

            {toolCall.result !== undefined && (
              <div>
                <div className="text-xs font-semibold text-muted-foreground mb-1.5">
                  {t('chat.toolResult')}
                </div>
                <div className="bg-surface-sunken rounded-lg p-2.5 overflow-x-auto max-h-48 overflow-y-auto">
                  <pre className="text-xs text-foreground whitespace-pre-wrap font-mono">
                    {formatValue(toolCall.result)}
                  </pre>
                </div>
              </div>
            )}

            {toolCall.error && toolCall.status !== 'error' && (
              <div>
                <div className="text-xs font-semibold text-red-500 mb-1.5">
                  {t('chat.toolError')}
                </div>
                <div className="bg-red-50 dark:bg-red-900/20 rounded-lg p-2.5">
                  <pre className="text-xs text-red-600 dark:text-red-400 whitespace-pre-wrap font-mono">
                    {toolCall.error}
                  </pre>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {showGenUiInline && sessionId && (
        <GenUiInline sessionId={sessionId} messageId={messageId} className="mt-2" />
      )}
    </div>
  );
}
