import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CheckCircle2, ChevronDown, ChevronRight, ClipboardCopy, XCircle } from 'lucide-react';
import hljs from 'highlight.js';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui';
import { cn } from '@/lib/utils';
import type { ToolCall } from '@/types/chat';

const PYTHON = 'python';

interface AgentWorkspaceCodeExecutionPanelProps {
  toolCall: ToolCall | null;
  sourceText: string;
  className?: string;
}

function highlightPythonLine(line: string): string {
  try {
    if (hljs.getLanguage(PYTHON)) {
      return hljs.highlight(line || ' ', { language: PYTHON }).value;
    }
    return hljs.highlightAuto(line || ' ').value;
  } catch {
    return line;
  }
}

/**
 * Visual shell matches the sibling Canvas HTML / Code Preview blocks rendered
 * by `AgentWorkspaceTab`: a soft `bg-surface-sunken/40` card with a small
 * uppercase header strip, and an inner code body that mirrors the
 * `CodeBlock` component (`bg-gray-50 dark:bg-surface`, compact horizontal
 * padding on `pre`, gray gutter). Tail-scroll and copy sit on the header row
 * like `AgentWorkspaceTerminal`.
 */
export function AgentWorkspaceCodeExecutionPanel({
  toolCall,
  sourceText,
  className,
}: AgentWorkspaceCodeExecutionPanelProps) {
  const { t } = useTranslation();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [collapsed, setCollapsed] = useState(true);
  const [stickToBottom, setStickToBottom] = useState(true);
  const prevIdRef = useRef<string | undefined>(undefined);
  const prevRawLenRef = useRef(0);

  const displayBody = sourceText.trim().length > 0 ? sourceText : '';

  const lines = useMemo(() => {
    if (!displayBody) return [];
    return displayBody.split('\n');
  }, [displayBody]);

  const lineCount = lines.length;

  useEffect(() => {
    const id = toolCall?.id;
    const rawLen = typeof toolCall?.argumentsRaw === 'string' ? toolCall.argumentsRaw.length : 0;
    const idChanged = id !== undefined && id !== prevIdRef.current;
    const grew = rawLen > prevRawLenRef.current && rawLen > 0;
    if (idChanged || grew) {
      setCollapsed(false);
    }
    prevIdRef.current = id;
    prevRawLenRef.current = rawLen;
  }, [toolCall?.id, toolCall?.argumentsRaw]);

  useEffect(() => {
    if (!stickToBottom || !scrollRef.current || collapsed) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [displayBody, stickToBottom, collapsed]);

  const handleToggle = useCallback(() => setCollapsed((v) => !v), []);

  const handleCopy = useCallback(() => {
    if (displayBody) void navigator.clipboard?.writeText(displayBody);
  }, [displayBody]);

  const title = t('chat.workspace.agent.codeExecutionStreamTitle', {
    defaultValue: 'Code execution (live)',
  });

  const artifactId = useMemo(() => {
    const result = toolCall?.result;
    if (result && typeof result === 'object' && !Array.isArray(result)) {
      const r = result as Record<string, unknown>;
      return typeof r.artifact_id === 'string' ? r.artifact_id : null;
    }
    return null;
  }, [toolCall?.result]);

  const resultEnvelope = useMemo(() => {
    const result = toolCall?.result;
    if (result && typeof result === 'object' && !Array.isArray(result)) {
      return result as Record<string, unknown>;
    }
    return null;
  }, [toolCall?.result]);

  const syntaxValid = useMemo(() => {
    if (resultEnvelope?.syntax_diagnostics && Array.isArray(resultEnvelope.syntax_diagnostics) && (resultEnvelope.syntax_diagnostics as unknown[]).length > 0) {
      return false;
    }
    return null;
  }, [resultEnvelope]);

  const errorType = useMemo(() => {
    if (!resultEnvelope) return null;
    const et = resultEnvelope.error_type;
    return typeof et === 'string' ? et : null;
  }, [resultEnvelope]);

  const isSuccess = useMemo(() => {
    if (!resultEnvelope) return null;
    return resultEnvelope.status === 'ok';
  }, [resultEnvelope]);

  return (
    <div
      className={cn(
        'flex flex-col rounded-lg border border-border-subtle/50 bg-surface-sunken/40 overflow-hidden',
        className,
      )}
      aria-label={title}
    >
      {/* Header — collapse + title + tail scroll / copy (aligned with AgentWorkspaceTerminal) */}
      <div className="flex w-full min-w-0 shrink-0 items-center gap-1">
        <button
          type="button"
          onClick={handleToggle}
          aria-expanded={!collapsed}
          className="flex min-w-0 flex-1 items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-surface/40"
        >
          {collapsed ? (
            <ChevronRight className="size-3 shrink-0 text-muted-foreground" aria-hidden />
          ) : (
            <ChevronDown className="size-3 shrink-0 text-muted-foreground" aria-hidden />
          )}
          <span className="min-w-0 flex-1 truncate text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            {title}
          </span>
          {isSuccess === true && (
            <CheckCircle2 className="size-3 shrink-0 text-emerald-500" aria-label={
              t('chat.workspace.agent.codeArtifact.success', { defaultValue: 'Success' })
            } />
          )}
          {errorType && (
            <>
              <XCircle className="size-3 shrink-0 text-rose-500" aria-label={
                t('chat.workspace.agent.codeArtifact.error', { defaultValue: 'Error' })
              } />
              <span className="shrink-0 text-[9px] font-medium uppercase text-rose-400">
                {errorType}
              </span>
            </>
          )}
          {syntaxValid === false && !errorType && (
            <XCircle className="size-3 shrink-0 text-rose-500" aria-label={
              t('chat.workspace.agent.codeArtifact.syntaxError', { defaultValue: 'Syntax Error' })
            } />
          )}
          {artifactId && (
            <span className="shrink-0 font-mono text-[9px] text-muted-foreground/50" title={artifactId}>
              {artifactId.slice(0, 8)}
            </span>
          )}
          {lineCount > 0 && (
            <span className="ml-auto shrink-0 text-[10px] tabular-nums text-muted-foreground/60">
              {lineCount} line{lineCount !== 1 ? 's' : ''}
            </span>
          )}
        </button>
        {!collapsed && displayBody.length > 0 && (
          <>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger>
                  <button
                    type="button"
                    className={cn(
                      'shrink-0 rounded px-1.5 py-0.5 text-[10px] text-muted-foreground/70 transition-colors',
                      'hover:bg-surface hover:text-foreground',
                    )}
                    onClick={() => setStickToBottom((v) => !v)}
                  >
                    {stickToBottom
                      ? t('chat.workspace.agent.terminalStick', { defaultValue: 'Scroll: tail' })
                      : t('chat.workspace.agent.terminalFree', { defaultValue: 'Scroll: free' })}
                  </button>
                </TooltipTrigger>
                <TooltipContent side="bottom">
                  {t('chat.workspace.agent.scrollTail', { defaultValue: 'Auto-scroll to latest output' })}
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger>
                  <button
                    type="button"
                    className={cn(
                      'mr-2 shrink-0 inline-flex items-center rounded p-1 text-muted-foreground/70 transition-colors',
                      'hover:bg-surface hover:text-foreground',
                    )}
                    aria-label={t('chat.workspace.agent.copyContents', { defaultValue: 'Copy contents' })}
                    onClick={handleCopy}
                  >
                    <ClipboardCopy className="size-3" aria-hidden />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="bottom">
                  {t('chat.workspace.agent.copyContents', { defaultValue: 'Copy contents' })}
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </>
        )}
      </div>

      {!collapsed && (
        <>
          {/* Code body — same chrome as `CodeBlock` */}
          <div
            ref={scrollRef}
            className={cn(
              'workspace-code-hljs min-h-0 flex-1 overflow-auto',
              'border-t border-gray-200 dark:border-gray-700',
              'bg-gray-50 dark:bg-surface',
              'max-h-[38vh] min-h-[100px]',
            )}
            onScroll={(ev) => {
              const el = ev.currentTarget;
              const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
              setStickToBottom(nearBottom);
            }}
          >
            {displayBody ? (
              <pre className="m-0 px-2 py-4 text-sm leading-relaxed">
                <code className="hljs language-python !bg-transparent">
                  <table className="w-full border-collapse">
                    <tbody>
                      {lines.map((line, index) => {
                        const lineNumber = index + 1;
                        return (
                          <tr key={`${lineNumber}-${index}`}>
                            <td
                              className={cn(
                                'select-none pr-2 text-right align-top',
                                'text-gray-500 dark:text-gray-600',
                                'border-r border-gray-200 dark:border-gray-700',
                              )}
                              style={{ minWidth: '2.25rem' }}
                            >
                              {lineNumber}
                            </td>
                            <td className="pl-2 align-top whitespace-pre-wrap break-words">
                              <span
                                className="block w-full min-w-0 bg-transparent !bg-transparent"
                                dangerouslySetInnerHTML={{
                                  __html: highlightPythonLine(line),
                                }}
                              />
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </code>
              </pre>
            ) : (
              <div className="p-4 text-[12px] text-muted-foreground">
                {t('chat.workspace.agent.codeExecutionEmpty', {
                  defaultValue: 'Waiting for source…',
                })}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
