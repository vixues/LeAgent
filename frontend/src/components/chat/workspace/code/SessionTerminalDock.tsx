import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, ChevronDown, ChevronRight, Terminal } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui';
import type { AgentSessionEvent } from '@/lib/agentSessionEvents';

interface SessionTerminalDockProps {
  events: AgentSessionEvent[];
  collapsed: boolean;
  onToggle: () => void;
  className?: string;
}

const ANSI_ESCAPE_RE = /\u001b\[[0-9;]*[A-Za-z]/g;

function stripAnsi(value: string): string {
  return value.replace(ANSI_ESCAPE_RE, '');
}

function promptFor(event: AgentSessionEvent): string {
  if (event.kind === 'shell') return event.label;
  if (event.kind === 'code_exec') return 'python';
  if (event.kind === 'project_run') return 'dev server';
  return event.label;
}

export function SessionTerminalDock({
  events,
  collapsed,
  onToggle,
  className,
}: SessionTerminalDockProps) {
  const { t } = useTranslation();
  const scrollRef = useRef<HTMLDivElement>(null);
  const [stickToBottom, setStickToBottom] = useState(true);
  const prevCountRef = useRef(events.length);

  const hasTruncation = useMemo(
    () => events.some((e) => e.stdoutTruncated || e.stderrTruncated),
    [events],
  );

  // Auto-expand when new command output arrives.
  useEffect(() => {
    if (events.length > prevCountRef.current && collapsed) {
      onToggle();
    }
    prevCountRef.current = events.length;
  }, [events.length, collapsed, onToggle]);

  useEffect(() => {
    if (!stickToBottom || !scrollRef.current || collapsed) return;
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [events, stickToBottom, collapsed]);

  return (
    <div
      className={cn(
        'flex shrink-0 flex-col rounded-lg border border-white/[0.06] bg-[#0c0c0e] text-[11px] text-zinc-200 transition-all',
        collapsed ? 'max-h-[34px]' : 'min-h-[110px] max-h-[40vh]',
        className,
      )}
      aria-label={t('chat.workspace.agent.terminalTitle', { defaultValue: 'Session output' })}
    >
      <div className="flex shrink-0 items-center">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={!collapsed}
          className="flex min-w-0 flex-1 items-center gap-2 px-2.5 py-2 font-medium text-zinc-400 transition-colors hover:text-zinc-200"
        >
          {collapsed ? (
            <ChevronRight className="size-3 shrink-0" aria-hidden />
          ) : (
            <ChevronDown className="size-3 shrink-0" aria-hidden />
          )}
          <Terminal className="size-3.5 shrink-0 opacity-80" aria-hidden />
          <span className="truncate text-[10px] uppercase tracking-wide">
            {t('chat.workspace.agent.terminalTitle', { defaultValue: 'Session output' })}
          </span>
          {hasTruncation && (
            <AlertTriangle
              className="ml-auto size-3 shrink-0 text-amber-400/80"
              aria-label={t('chat.workspace.agent.terminalTruncated', {
                defaultValue: 'Output was truncated',
              })}
            />
          )}
          {events.length > 0 && (
            <span
              className={cn(
                'rounded-full bg-white/10 px-1.5 py-0.5 text-[9px] font-semibold tabular-nums text-zinc-400',
                !hasTruncation && 'ml-auto',
              )}
            >
              {events.length}
            </span>
          )}
        </button>
        {!collapsed && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger>
                <button
                  type="button"
                  className="mr-2 shrink-0 rounded px-1.5 py-0.5 text-[10px] text-zinc-500 transition-colors hover:bg-white/5 hover:text-zinc-300"
                  onClick={() => setStickToBottom((v) => !v)}
                >
                  {stickToBottom
                    ? t('chat.workspace.agent.terminalStick', { defaultValue: 'Scroll: tail' })
                    : t('chat.workspace.agent.terminalFree', { defaultValue: 'Scroll: free' })}
                </button>
              </TooltipTrigger>
              <TooltipContent side="bottom">
                {t('chat.workspace.agent.scrollTail', {
                  defaultValue: 'Auto-scroll to latest output',
                })}
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
      </div>

      {!collapsed && (
        <div
          ref={scrollRef}
          className="min-h-0 flex-1 overflow-auto border-t border-white/[0.06] px-2.5 py-2 font-mono leading-relaxed"
          onScroll={(ev) => {
            const el = ev.currentTarget;
            const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
            setStickToBottom(nearBottom);
          }}
        >
          {events.length === 0 ? (
            <span className="text-zinc-500">
              {t('chat.workspace.agent.terminalEmpty', {
                defaultValue: 'No shell or script output in this session yet.',
              })}
            </span>
          ) : (
            <div className="space-y-2">
              {events.map((event) => {
                const stdout = event.stdout ? stripAnsi(event.stdout).trimEnd() : '';
                const stderr = event.stderr ? stripAnsi(event.stderr).trimEnd() : '';
                return (
                  <div key={event.id}>
                    <div className="flex items-center gap-1.5 text-zinc-500">
                      <span className="text-emerald-400/80">$</span>
                      <span className="truncate">{promptFor(event)}</span>
                    </div>
                    {stdout && (
                      <pre className="whitespace-pre-wrap break-words text-zinc-200">{stdout}</pre>
                    )}
                    {event.stdoutTruncated && (
                      <div className="text-[10px] text-amber-400/70">
                        {t('chat.workspace.agent.stdoutTruncated', {
                          defaultValue: '⚠ stdout truncated',
                        })}
                      </div>
                    )}
                    {stderr && (
                      <pre className="whitespace-pre-wrap break-words text-rose-400">{stderr}</pre>
                    )}
                    {event.stderrTruncated && (
                      <div className="text-[10px] text-amber-400/70">
                        {t('chat.workspace.agent.stderrTruncated', {
                          defaultValue: '⚠ stderr truncated',
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
