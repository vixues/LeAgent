/**
 * Run-grouped execution records: every agent turn (run) becomes a
 * collapsible group of tool events with per-run counts, duration, and
 * error badges. The latest run auto-expands and auto-scrolls into view.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleDashed,
  Loader2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { AgentSessionEvent } from '@/lib/agentSessionEvents';
import { eventKindMeta } from './eventMeta';

interface RunGroupsViewProps {
  events: AgentSessionEvent[];
  /** Jump back to the Activity timeline focused on one event. */
  onSelectEvent: (eventId: string) => void;
}

interface RunGroup {
  /** messageIndex encoded in `event.order` (order = msgIdx * 1000 + toolIdx). */
  turnIndex: number;
  events: AgentSessionEvent[];
  errorCount: number;
  runningCount: number;
  durationMs: number;
}

function groupByRun(events: AgentSessionEvent[]): RunGroup[] {
  const byTurn = new Map<number, AgentSessionEvent[]>();
  for (const ev of events) {
    const turn = Math.floor(ev.order / 1000);
    const arr = byTurn.get(turn);
    if (arr) arr.push(ev);
    else byTurn.set(turn, [ev]);
  }
  return [...byTurn.entries()]
    .sort(([a], [b]) => a - b)
    .map(([turnIndex, evs]) => ({
      turnIndex,
      events: evs,
      errorCount: evs.filter((e) => e.status === 'error').length,
      runningCount: evs.filter((e) => e.status === 'running' || e.streaming).length,
      durationMs: evs.reduce((acc, e) => acc + (e.durationMs ?? 0), 0),
    }));
}

function formatDuration(ms: number): string {
  if (ms <= 0) return '';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function RunGroupsView({ events, onSelectEvent }: RunGroupsViewProps) {
  const { t } = useTranslation();
  const groups = useMemo(() => groupByRun(events), [events]);
  const [collapsed, setCollapsed] = useState<Set<number>>(() => new Set());
  const bottomRef = useRef<HTMLDivElement>(null);
  const lastGroupKeyRef = useRef<number>(-1);

  // Auto-focus: when a new run appears, keep it expanded and scroll to it.
  useEffect(() => {
    const last = groups[groups.length - 1];
    if (!last) return;
    if (last.turnIndex !== lastGroupKeyRef.current) {
      lastGroupKeyRef.current = last.turnIndex;
      setCollapsed((prev) => {
        if (!prev.has(last.turnIndex)) return prev;
        const next = new Set(prev);
        next.delete(last.turnIndex);
        return next;
      });
      bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [groups]);

  if (groups.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center p-6 text-xs text-muted-foreground">
        {t('chat.workspace.agent.runs.empty', {
          defaultValue: 'No execution records yet.',
        })}
      </div>
    );
  }

  return (
    <div className="chat-sessions-scroll -mr-1 min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1">
      {groups.map((group, i) => {
        const isCollapsed = collapsed.has(group.turnIndex);
        const running = group.runningCount > 0;
        return (
          <div
            key={group.turnIndex}
            className="rounded-lg border border-border-subtle/50 bg-surface-sunken/40"
          >
            <button
              type="button"
              onClick={() =>
                setCollapsed((prev) => {
                  const next = new Set(prev);
                  if (next.has(group.turnIndex)) next.delete(group.turnIndex);
                  else next.add(group.turnIndex);
                  return next;
                })
              }
              className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-[11px]"
              aria-expanded={!isCollapsed}
            >
              {isCollapsed ? (
                <ChevronRight className="size-3 shrink-0 text-muted-foreground" aria-hidden />
              ) : (
                <ChevronDown className="size-3 shrink-0 text-muted-foreground" aria-hidden />
              )}
              {running ? (
                <Loader2 className="size-3 shrink-0 animate-spin text-primary" aria-hidden />
              ) : group.errorCount > 0 ? (
                <AlertTriangle className="size-3 shrink-0 text-amber-500" aria-hidden />
              ) : (
                <CheckCircle2 className="size-3 shrink-0 text-emerald-500" aria-hidden />
              )}
              <span className="font-medium text-foreground">
                {t('chat.workspace.agent.runs.runTitle', {
                  defaultValue: 'Run {{index}}',
                  index: i + 1,
                })}
              </span>
              <span className="text-muted-foreground">
                {t('chat.workspace.agent.runs.toolCount', {
                  defaultValue: '{{count}} tools',
                  count: group.events.length,
                })}
              </span>
              {group.errorCount > 0 && (
                <span className="rounded bg-rose-500/15 px-1 py-0.5 text-[9px] font-semibold text-rose-500">
                  {t('chat.workspace.agent.runs.errorCount', {
                    defaultValue: '{{count}} failed',
                    count: group.errorCount,
                  })}
                </span>
              )}
              <span className="ml-auto tabular-nums text-muted-foreground-tertiary">
                {formatDuration(group.durationMs)}
              </span>
            </button>

            {!isCollapsed && (
              <div className="border-t border-border-subtle/40 py-0.5">
                {group.events.map((ev) => {
                  const meta = eventKindMeta(ev.kind);
                  const Icon = meta.icon;
                  return (
                    <button
                      key={ev.id}
                      type="button"
                      onClick={() => onSelectEvent(ev.id)}
                      className="flex w-full items-center gap-2 px-2.5 py-1 text-left text-[11px] transition-colors hover:bg-surface-sunken"
                    >
                      <span
                        className={cn(
                          'flex size-4 shrink-0 items-center justify-center rounded',
                          meta.accent,
                        )}
                      >
                        <Icon className="size-2.5" aria-hidden />
                      </span>
                      <span className="min-w-0 flex-1 truncate text-foreground/90">
                        {ev.label}
                      </span>
                      {ev.status === 'running' || ev.streaming ? (
                        <Loader2
                          className="size-3 shrink-0 animate-spin text-primary"
                          aria-hidden
                        />
                      ) : ev.status === 'error' ? (
                        <AlertTriangle className="size-3 shrink-0 text-rose-500" aria-hidden />
                      ) : ev.status === 'pending' ? (
                        <CircleDashed
                          className="size-3 shrink-0 text-muted-foreground"
                          aria-hidden
                        />
                      ) : null}
                      {typeof ev.durationMs === 'number' && ev.durationMs > 0 && (
                        <span className="shrink-0 tabular-nums text-[10px] text-muted-foreground-tertiary">
                          {formatDuration(ev.durationMs)}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
