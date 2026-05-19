import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, ChevronDown, ChevronRight, Terminal } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui';
import { cn } from '@/lib/utils';
import type { Message } from '@/types/chat';
import { collectAgentTerminalLogs } from '@/lib/agentTerminalLogs';

interface AgentWorkspaceTerminalProps {
  messages: Message[];
  collapsed?: boolean;
  onToggle?: () => void;
  className?: string;
}

export function AgentWorkspaceTerminal({
  messages,
  collapsed: controlledCollapsed,
  onToggle,
  className,
}: AgentWorkspaceTerminalProps) {
  const { t } = useTranslation();
  const entries = useMemo(() => collectAgentTerminalLogs(messages), [messages]);
  const scrollRef = useRef<HTMLPreElement>(null);
  const [stickToBottom, setStickToBottom] = useState(true);
  const [internalCollapsed, setInternalCollapsed] = useState(true);
  const prevCountRef = useRef(entries.length);

  const isCollapsed = controlledCollapsed ?? internalCollapsed;
  const handleToggle = useCallback(
    () => (onToggle ?? (() => setInternalCollapsed((v) => !v)))(),
    [onToggle],
  );

  // Auto-expand when new output arrives
  useEffect(() => {
    if (entries.length > prevCountRef.current && isCollapsed) {
      handleToggle();
    }
    prevCountRef.current = entries.length;
  }, [entries.length, isCollapsed, handleToggle]);

  useEffect(() => {
    if (!stickToBottom || !scrollRef.current || isCollapsed) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [entries, stickToBottom, isCollapsed]);

  const hasTruncation = useMemo(
    () => entries.some((e) => e.stdoutTruncated || e.stderrTruncated),
    [entries],
  );

  const text = useMemo(() => {
    if (entries.length === 0) return '';
    return entries
      .map((e) => {
        const parts = [`[${e.toolName}]`];
        if (e.stdout.trim()) {
          parts.push(e.stdout.trimEnd());
          if (e.stdoutTruncated) parts.push('⚠ stdout truncated');
        }
        if (e.stderr.trim()) {
          parts.push(`stderr:\n${e.stderr.trimEnd()}`);
          if (e.stderrTruncated) parts.push('⚠ stderr truncated');
        }
        return parts.join('\n');
      })
      .join('\n\n');
  }, [entries]);

  return (
    <div
      className={cn(
        'shrink-0 flex flex-col rounded-lg border border-white/[0.06] bg-[#0c0c0e] text-[11px] text-zinc-200 transition-all',
        isCollapsed ? 'max-h-[34px]' : 'min-h-[100px] max-h-[38vh]',
        className,
      )}
      aria-label={t('chat.workspace.agent.terminalTitle', { defaultValue: 'Session output' })}
    >
      <div className="flex shrink-0 items-center">
        <button
          type="button"
          onClick={handleToggle}
          className="flex min-w-0 flex-1 items-center gap-2 px-2.5 py-2 font-medium text-zinc-400 hover:text-zinc-200 transition-colors"
        >
          {isCollapsed ? (
            <ChevronRight className="size-3 shrink-0" aria-hidden />
          ) : (
            <ChevronDown className="size-3 shrink-0" aria-hidden />
          )}
          <Terminal className="size-3.5 shrink-0 opacity-80" aria-hidden />
          <span className="truncate text-[10px] uppercase tracking-wide">
            {t('chat.workspace.agent.terminalTitle', { defaultValue: 'Session output' })}
          </span>
          {hasTruncation && (
            <AlertTriangle className="ml-auto size-3 shrink-0 text-amber-400/80" aria-label={
              t('chat.workspace.agent.terminalTruncated', { defaultValue: 'Output was truncated' })
            } />
          )}
          {entries.length > 0 && (
            <span className={cn('rounded-full bg-white/10 px-1.5 py-0.5 text-[9px] font-semibold tabular-nums text-zinc-400', !hasTruncation && 'ml-auto')}>
              {entries.length}
            </span>
          )}
        </button>
        {!isCollapsed && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger>
                <button
                  type="button"
                  className="mr-2 shrink-0 rounded px-1.5 py-0.5 text-[10px] text-zinc-500 hover:bg-white/5 hover:text-zinc-300 transition-colors"
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
        )}
      </div>

      {!isCollapsed && (
        <pre
          ref={scrollRef}
          className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap break-words border-t border-white/[0.06] px-2.5 py-2 font-mono leading-relaxed"
          onScroll={(ev) => {
            const el = ev.currentTarget;
            const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
            setStickToBottom(nearBottom);
          }}
        >
          {entries.length === 0 ? (
            <span className="text-zinc-500">
              {t('chat.workspace.agent.terminalEmpty', {
                defaultValue: 'No shell or script output in this session yet.',
              })}
            </span>
          ) : (
            text
          )}
        </pre>
      )}
    </div>
  );
}
