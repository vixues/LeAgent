/**
 * Professional session terminal dock (xterm.js).
 *
 * Two sources feed one dock, split into tabs:
 *  - **Shell** — completed tool outputs from the session timeline plus the
 *    live `tool_output_delta` SSE stream (`useTerminalStore`), rendered in
 *    a real xterm terminal (ANSI colors, monospace grid, scrollback).
 *  - **Dev server** — the coding-project run log SSE, unified into the same
 *    dock instead of a separate panel.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Server,
  Terminal as TerminalIcon,
} from 'lucide-react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/stores/chat';
import { useChatDraftStore } from '@/stores/chatDraft';
import { useTerminalStore, selectSessionChunks, type TerminalChunk } from '@/stores/terminal';
import { useCodingProjectLogs } from '@/hooks/useCodingProjects';
import type { AgentSessionEvent } from '@/lib/agentSessionEvents';

interface SessionTerminalDockProps {
  events: AgentSessionEvent[];
  collapsed: boolean;
  onToggle: () => void;
  className?: string;
}

type DockTab = 'shell' | 'dev';

const XTERM_THEME = {
  background: '#0c0c0e',
  foreground: '#d4d4d8',
  cursor: '#a1a1aa',
  selectionBackground: '#3f3f46',
  black: '#18181b',
  red: '#f87171',
  green: '#34d399',
  yellow: '#fbbf24',
  blue: '#60a5fa',
  magenta: '#c084fc',
  cyan: '#22d3ee',
  white: '#e4e4e7',
};

const GREEN = '\x1b[32m';
const RED = '\x1b[31m';
const DIM = '\x1b[2m';
const RESET = '\x1b[0m';

function promptFor(event: AgentSessionEvent): string {
  if (event.kind === 'shell') return event.label;
  if (event.kind === 'code_exec') return 'python';
  if (event.kind === 'project_run') return 'dev server';
  return event.label;
}

function writeBlock(term: Terminal, text: string, color = '') {
  const normalized = text.replace(/\r?\n/g, '\r\n');
  term.write(color ? `${color}${normalized}${RESET}` : normalized);
  if (!normalized.endsWith('\r\n')) term.write('\r\n');
}

export function SessionTerminalDock({
  events,
  collapsed,
  onToggle,
  className,
}: SessionTerminalDockProps) {
  const { t } = useTranslation();
  const [tab, setTab] = useState<DockTab>('shell');
  const prevCountRef = useRef(events.length);

  const currentSessionId = useChatStore((s) => s.currentSessionId);
  const projectFolderId = useChatDraftStore((s) => s.projectFolderId);
  const connect = useTerminalStore((s) => s.connect);
  const chunks = useTerminalStore((s) => selectSessionChunks(s, currentSessionId));
  const liveCallCount = useTerminalStore((s) => {
    if (!currentSessionId) return 0;
    return s.liveCalls[currentSessionId]?.size ?? 0;
  });

  // Live SSE subscription for the active session.
  useEffect(() => {
    if (currentSessionId) connect(currentSessionId);
  }, [currentSessionId, connect]);

  // Dev-server logs, unified into the dock.
  const devLogs = useCodingProjectLogs(projectFolderId ?? null, {
    enabled: Boolean(projectFolderId) && tab === 'dev' && !collapsed,
  });

  const hasTruncation = useMemo(
    () => events.some((e) => e.stdoutTruncated || e.stderrTruncated),
    [events],
  );

  // Auto-expand when new command output arrives (historical or live).
  useEffect(() => {
    if (events.length > prevCountRef.current && collapsed) onToggle();
    prevCountRef.current = events.length;
  }, [events.length, collapsed, onToggle]);

  const prevLiveRef = useRef(liveCallCount);
  useEffect(() => {
    if (liveCallCount > prevLiveRef.current && collapsed) onToggle();
    prevLiveRef.current = liveCallCount;
  }, [liveCallCount, collapsed, onToggle]);

  /* ─── xterm lifecycle ─────────────────────────────────────── */
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const writtenEventIdsRef = useRef<Set<string>>(new Set());
  const liveCallIdsRef = useRef<Set<string>>(new Set());
  const writtenSeqRef = useRef(0);
  const openPromptCallRef = useRef<string | null>(null);

  const disposeTerm = useCallback(() => {
    termRef.current?.dispose();
    termRef.current = null;
    fitRef.current = null;
    writtenEventIdsRef.current = new Set();
    writtenSeqRef.current = 0;
    openPromptCallRef.current = null;
  }, []);

  // (Re)create the terminal when the dock body is visible on the shell tab.
  useEffect(() => {
    if (collapsed || tab !== 'shell') {
      disposeTerm();
      return;
    }
    const el = containerRef.current;
    if (!el || termRef.current) return;

    const term = new Terminal({
      convertEol: false,
      disableStdin: true,
      fontSize: 11,
      fontFamily:
        'ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace',
      theme: XTERM_THEME,
      scrollback: 5000,
      cursorBlink: false,
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(el);
    try {
      fit.fit();
    } catch {
      /* container not measurable yet */
    }
    termRef.current = term;
    fitRef.current = fit;

    const resizeObserver = new ResizeObserver(() => {
      try {
        fitRef.current?.fit();
      } catch {
        /* ignore */
      }
    });
    resizeObserver.observe(el);

    return () => {
      resizeObserver.disconnect();
      disposeTerm();
    };
  }, [collapsed, tab, disposeTerm, currentSessionId]);

  // Replay historical events + append live chunks.
  useEffect(() => {
    const term = termRef.current;
    if (!term || collapsed || tab !== 'shell') return;

    // Calls streamed live are skipped in the historical replay to avoid
    // rendering the same output twice once the tool_result lands.
    for (const chunk of chunks) liveCallIdsRef.current.add(chunk.tool_call_id);

    for (const event of events) {
      if (writtenEventIdsRef.current.has(event.id)) continue;
      writtenEventIdsRef.current.add(event.id);
      if (event.toolCallId && liveCallIdsRef.current.has(event.toolCallId)) continue;
      term.write(`${GREEN}$ ${RESET}${DIM}${promptFor(event)}${RESET}\r\n`);
      if (event.stdout) writeBlock(term, event.stdout.trimEnd());
      if (event.stdoutTruncated) {
        writeBlock(
          term,
          t('chat.workspace.agent.stdoutTruncated', { defaultValue: '⚠ stdout truncated' }),
          DIM,
        );
      }
      if (event.stderr) writeBlock(term, event.stderr.trimEnd(), RED);
      if (event.stderrTruncated) {
        writeBlock(
          term,
          t('chat.workspace.agent.stderrTruncated', { defaultValue: '⚠ stderr truncated' }),
          DIM,
        );
      }
    }

    // Live chunk tail.
    const newChunks = chunks.filter((c) => c.seq > writtenSeqRef.current);
    for (const chunk of newChunks) {
      writtenSeqRef.current = Math.max(writtenSeqRef.current, chunk.seq);
      writeLiveChunk(term, chunk, openPromptCallRef);
    }
  }, [events, chunks, collapsed, tab, t]);

  /* ─── render ──────────────────────────────────────────────── */
  const shellBadge = events.length + liveCallCount;

  return (
    <div
      className={cn(
        'flex shrink-0 flex-col rounded-lg border border-white/[0.06] bg-[#0c0c0e] text-[11px] text-zinc-200 transition-all',
        collapsed ? 'max-h-[34px]' : 'min-h-[140px] max-h-[40vh]',
        className,
      )}
      aria-label={t('chat.workspace.agent.terminalTitle', { defaultValue: 'Session output' })}
    >
      <div className="flex shrink-0 items-center">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={!collapsed}
          className="flex min-w-0 items-center gap-2 px-2.5 py-2 font-medium text-zinc-400 transition-colors hover:text-zinc-200"
        >
          {collapsed ? (
            <ChevronRight className="size-3 shrink-0" aria-hidden />
          ) : (
            <ChevronDown className="size-3 shrink-0" aria-hidden />
          )}
          <TerminalIcon className="size-3.5 shrink-0 opacity-80" aria-hidden />
          <span className="truncate text-[10px] uppercase tracking-wide">
            {t('chat.workspace.agent.terminalTitle', { defaultValue: 'Session output' })}
          </span>
        </button>

        {!collapsed && (
          <div className="flex items-center gap-0.5 pl-1">
            <button
              type="button"
              onClick={() => setTab('shell')}
              className={cn(
                'rounded px-2 py-0.5 text-[10px] font-medium transition-colors',
                tab === 'shell'
                  ? 'bg-white/10 text-zinc-100'
                  : 'text-zinc-500 hover:text-zinc-300',
              )}
            >
              {t('chat.workspace.agent.terminalTabShell', { defaultValue: 'Shell' })}
              {shellBadge > 0 && (
                <span className="ml-1 tabular-nums text-zinc-500">{shellBadge}</span>
              )}
            </button>
            {projectFolderId && (
              <button
                type="button"
                onClick={() => setTab('dev')}
                className={cn(
                  'flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-medium transition-colors',
                  tab === 'dev'
                    ? 'bg-white/10 text-zinc-100'
                    : 'text-zinc-500 hover:text-zinc-300',
                )}
              >
                <Server className="size-3" aria-hidden />
                {t('chat.workspace.agent.terminalTabDev', { defaultValue: 'Dev server' })}
              </button>
            )}
          </div>
        )}

        <div className="ml-auto flex items-center gap-1.5 pr-2">
          {liveCallCount > 0 && (
            <span className="flex items-center gap-1 text-[10px] text-emerald-400/90">
              <span className="size-1.5 animate-pulse rounded-full bg-emerald-400" />
              {t('chat.workspace.agent.terminalLive', { defaultValue: 'live' })}
            </span>
          )}
          {hasTruncation && (
            <AlertTriangle
              className="size-3 shrink-0 text-amber-400/80"
              aria-label={t('chat.workspace.agent.terminalTruncated', {
                defaultValue: 'Output was truncated',
              })}
            />
          )}
        </div>
      </div>

      {!collapsed && tab === 'shell' && (
        <div className="relative min-h-0 flex-1 border-t border-white/[0.06]">
          {events.length === 0 && chunks.length === 0 && (
            <span className="absolute left-3 top-2 z-10 text-zinc-500">
              {t('chat.workspace.agent.terminalEmpty', {
                defaultValue: 'No shell or script output in this session yet.',
              })}
            </span>
          )}
          <div ref={containerRef} className="h-full min-h-[110px] w-full px-1 py-1" />
        </div>
      )}

      {!collapsed && tab === 'dev' && (
        <div className="min-h-0 flex-1 overflow-auto border-t border-white/[0.06] px-2.5 py-2 font-mono leading-relaxed">
          {devLogs.lines.length === 0 ? (
            <span className="text-zinc-500">
              {devLogs.error
                ? devLogs.error
                : t('chat.workspace.agent.terminalDevEmpty', {
                    defaultValue: 'No dev-server output yet.',
                  })}
            </span>
          ) : (
            devLogs.lines.map((line) => (
              <div
                key={line.seq}
                className={cn(
                  'whitespace-pre-wrap break-words',
                  line.stream === 'stderr' ? 'text-rose-400' : 'text-zinc-200',
                )}
              >
                {line.text}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

/** Write one live chunk, emitting a prompt header when a new call starts. */
function writeLiveChunk(
  term: Terminal,
  chunk: TerminalChunk,
  openPromptCallRef: { current: string | null },
) {
  if (chunk.done) {
    if (openPromptCallRef.current === chunk.tool_call_id) {
      const code = chunk.exit_code ?? 0;
      const color = code === 0 ? GREEN : RED;
      term.write(`\r\n${DIM}${color}↳ exit ${code}${RESET}\r\n`);
      openPromptCallRef.current = null;
    }
    return;
  }
  if (openPromptCallRef.current !== chunk.tool_call_id) {
    term.write(
      `${GREEN}$ ${RESET}${DIM}${chunk.tool_name || chunk.source}${RESET}\r\n`,
    );
    openPromptCallRef.current = chunk.tool_call_id;
  }
  const color = chunk.stream === 'stderr' ? RED : '';
  const normalized = chunk.data.replace(/(?<!\r)\n/g, '\r\n');
  term.write(color ? `${color}${normalized}${RESET}` : normalized);
}
