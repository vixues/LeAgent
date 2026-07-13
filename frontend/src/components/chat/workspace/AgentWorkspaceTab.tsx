import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FileCode2 } from 'lucide-react';
import { EMPTY_MESSAGE_LIST } from '@/lib/emptyChatMessages';
import {
  collectAgentSessionEvents,
  collectArtifacts,
  collectTerminalEvents,
  collectTouchedFiles,
  summarizeSessionEvents,
  type AgentEventKind,
  type AgentSessionEvent,
} from '@/lib/agentSessionEvents';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/stores/chat';
import { useCodeArtifactStore, type CodeArtifactEntry } from '@/stores/codeArtifact';
import { useChangeReviews } from '@/hooks/useChangeReviews';
import { SessionHeader } from './code/SessionHeader';
import { ChangedFilesRail } from './code/ChangedFilesRail';
import { ArtifactsRail } from './code/ArtifactsRail';
import { AgentSessionTimeline } from './code/AgentSessionTimeline';
import { SessionTerminalDock } from './code/SessionTerminalDock';
import { RunGroupsView } from './code/RunGroupsView';
import { ReviewQueueView } from './code/ReviewQueueView';
import { eventKindMeta } from './code/eventMeta';
import { ChatTraceInspector } from '@/components/chat/ChatTraceInspector';
import { useExecutionSessionStore } from '@/stores/executionSession';

const EMPTY_CODE_ARTIFACT_IDS: string[] = [];
const EMPTY_CODE_ARTIFACTS: CodeArtifactEntry[] = [];

type CodeSubTab = 'activity' | 'runs' | 'review' | 'trace';

/** Canonical ordering for the filter chip strip. */
const KIND_ORDER: AgentEventKind[] = [
  'read',
  'write',
  'edit',
  'patch',
  'doc_gen',
  'code_exec',
  'shell',
  'project_run',
  'canvas',
  'nested_agent',
];

function buildSessionLog(events: AgentSessionEvent[]): string {
  return events
    .map((ev) => {
      const meta = eventKindMeta(ev.kind);
      const header = `› ${meta.verb} ${ev.label}`.trim();
      const body = ev.diff
        ? `--- before\n${ev.diff.before}\n+++ after\n${ev.diff.after}`
        : ev.code ?? '';
      const out = [ev.stdout, ev.stderr].filter(Boolean).join('\n');
      return [header, body, out].filter((s) => s && s.trim().length > 0).join('\n');
    })
    .join('\n\n');
}

export function AgentWorkspaceTab() {
  const { t } = useTranslation();
  const currentSessionId = useChatStore((s) => s.currentSessionId);
  const messages = useChatStore((s) =>
    currentSessionId ? s.messages[currentSessionId] ?? EMPTY_MESSAGE_LIST : EMPTY_MESSAGE_LIST,
  );
  const nestedPreview = useChatStore((s) =>
    currentSessionId ? (s.nestedAgentPreviewBySession[currentSessionId] ?? null) : null,
  );

  const codeArtifactEntries = useCodeArtifactStore((s) => s.entries);
  const codeArtifactIds = useCodeArtifactStore((s) =>
    currentSessionId
      ? (s.bySession[currentSessionId] ?? EMPTY_CODE_ARTIFACT_IDS)
      : EMPTY_CODE_ARTIFACT_IDS,
  );
  const codeArtifacts = useMemo(
    () =>
      codeArtifactIds.length === 0
        ? EMPTY_CODE_ARTIFACTS
        : codeArtifactIds
            .map((id) => codeArtifactEntries[id])
            .filter((entry): entry is CodeArtifactEntry => Boolean(entry)),
    [codeArtifactEntries, codeArtifactIds],
  );

  const events = useMemo(
    () => collectAgentSessionEvents(messages, codeArtifacts, nestedPreview),
    [messages, codeArtifacts, nestedPreview],
  );

  const summary = useMemo(() => summarizeSessionEvents(events), [events]);
  const touchedFiles = useMemo(() => collectTouchedFiles(events), [events]);
  const terminalEvents = useMemo(() => collectTerminalEvents(events), [events]);
  const artifacts = useMemo(() => collectArtifacts(events), [events]);

  const availableKinds = useMemo(() => {
    const present = new Set(events.map((e) => e.kind));
    return KIND_ORDER.filter((k) => present.has(k));
  }, [events]);

  const running = summary.runningCount > 0 || Boolean(nestedPreview);

  // --- Interaction state (this tab is the controller) ---

  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set());
  const [wrap, setWrap] = useState(false);
  const [selectedKinds, setSelectedKinds] = useState<Set<AgentEventKind>>(() => new Set());
  const [scrollTargetId, setScrollTargetId] = useState<string | null>(null);
  const [terminalCollapsed, setTerminalCollapsed] = useState(true);
  const [subTab, setSubTab] = useState<CodeSubTab>('activity');
  const autoExpandedRef = useRef<Set<string>>(new Set());
  const runId = useExecutionSessionStore((s) =>
    currentSessionId ? s.bySession[currentSessionId]?.runId || null : null,
  );

  const pendingReviews = useChangeReviews(currentSessionId);
  const pendingReviewCount = useMemo(
    () => (pendingReviews.data ?? []).filter((r) => r.status === 'pending').length,
    [pendingReviews.data],
  );

  // Auto-expand newly-streaming events once (does not fight a manual collapse).
  useEffect(() => {
    const toExpand: string[] = [];
    for (const ev of events) {
      if (ev.streaming && !autoExpandedRef.current.has(ev.id)) {
        autoExpandedRef.current.add(ev.id);
        toExpand.push(ev.id);
      }
    }
    if (toExpand.length > 0) {
      setExpandedIds((prev) => {
        const next = new Set(prev);
        toExpand.forEach((id) => next.add(id));
        return next;
      });
    }
  }, [events]);

  const filteredEvents = useMemo(() => {
    if (selectedKinds.size === 0) return events;
    return events.filter((e) => selectedKinds.has(e.kind));
  }, [events, selectedKinds]);

  const isExpanded = useCallback((id: string) => expandedIds.has(id), [expandedIds]);

  const handleToggle = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleExpandAll = useCallback(() => {
    setExpandedIds(new Set(filteredEvents.map((e) => e.id)));
  }, [filteredEvents]);

  const handleCollapseAll = useCallback(() => {
    setExpandedIds(new Set());
  }, []);

  const handleToggleFilter = useCallback((kind: AgentEventKind) => {
    setSelectedKinds((prev) => {
      const next = new Set(prev);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });
  }, []);

  const handleSelectFile = useCallback((eventId: string) => {
    setSubTab('activity');
    setExpandedIds((prev) => {
      if (prev.has(eventId)) return prev;
      const next = new Set(prev);
      next.add(eventId);
      return next;
    });
    setScrollTargetId(eventId);
  }, []);

  const handleCopySession = useCallback(() => {
    const log = buildSessionLog(events);
    if (log) void navigator.clipboard?.writeText(log);
  }, [events]);

  const handleTerminalToggle = useCallback(() => {
    setTerminalCollapsed((v) => !v);
  }, []);

  const subTabs = (
    <div className="flex shrink-0 items-center gap-0.5">
      {(
        [
          ['activity', t('chat.workspace.agent.subtabs.activity', { defaultValue: 'Activity' })],
          ['runs', t('chat.workspace.agent.subtabs.runs', { defaultValue: 'Runs' })],
          ['trace', t('chat.workspace.agent.subtabs.trace', { defaultValue: 'Trace' })],
          ['review', t('chat.workspace.agent.subtabs.review', { defaultValue: 'Review' })],
        ] as [CodeSubTab, string][]
      ).map(([id, label]) => (
        <button
          key={id}
          type="button"
          onClick={() => setSubTab(id)}
          className={cn(
            'rounded-md px-2 py-1 text-[11px] font-medium transition-colors',
            subTab === id
              ? 'bg-surface-sunken text-foreground'
              : 'text-muted-foreground hover:text-foreground',
          )}
          aria-pressed={subTab === id}
        >
          {label}
          {id === 'review' && pendingReviewCount > 0 && (
            <span className="ml-1 rounded-full bg-amber-500/20 px-1.5 py-0.5 text-[9px] font-semibold tabular-nums text-amber-600 dark:text-amber-400">
              {pendingReviewCount}
            </span>
          )}
        </button>
      ))}
    </div>
  );

  const tracePanel =
    subTab === 'trace' && currentSessionId ? (
      <div className="chat-sessions-scroll -mr-1 flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto pr-1">
        <p className="text-[11px] leading-relaxed text-muted-foreground-tertiary">
          {t('chat.workspace.agent.trace.hint')}
        </p>
        <ChatTraceInspector sessionId={currentSessionId} runId={runId} />
      </div>
    ) : null;

  // Trace is durable session metadata — always available even without code events.
  if (subTab === 'trace') {
    return (
      <div className="flex min-h-0 flex-1 flex-col gap-1.5 p-2">
        {subTabs}
        {tracePanel ?? (
          <p className="p-4 text-xs text-muted-foreground">
            {t('chat.execution.panel.traceEmpty')}
          </p>
        )}
      </div>
    );
  }

  if (events.length === 0) {
    return (
      <div className="flex min-h-0 flex-1 flex-col gap-1.5 p-2">
        {subTabs}
        <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8 text-center">
          <div className="flex size-12 items-center justify-center rounded-xl border border-border-subtle/40 bg-surface-sunken/60">
            <FileCode2 className="size-5 text-muted-foreground/50" />
          </div>
          <p className="max-w-[220px] text-xs leading-relaxed text-muted-foreground">
            {t('chat.workspace.agent.pickPath', {
              defaultValue: 'Code activity will appear here once the agent starts working on files.',
            })}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-1.5 p-2">
      <SessionHeader
        summary={summary}
        running={running}
        wrap={wrap}
        onWrapToggle={() => setWrap((v) => !v)}
        onExpandAll={handleExpandAll}
        onCollapseAll={handleCollapseAll}
        onCopySession={handleCopySession}
        availableKinds={availableKinds}
        selectedKinds={selectedKinds}
        onToggleFilter={handleToggleFilter}
      />

      <ChangedFilesRail files={touchedFiles} onSelect={handleSelectFile} />

      <ArtifactsRail artifacts={artifacts} />

      {subTabs}

      {subTab === 'activity' && (
        <div className="chat-sessions-scroll -mr-1 min-h-0 flex-1 overflow-y-auto pr-1">
          <AgentSessionTimeline
            events={filteredEvents}
            isExpanded={isExpanded}
            onToggle={handleToggle}
            wrap={wrap}
            scrollTargetId={scrollTargetId}
            onScrolled={() => setScrollTargetId(null)}
          />
        </div>
      )}

      {subTab === 'runs' && (
        <RunGroupsView events={filteredEvents} onSelectEvent={handleSelectFile} />
      )}

      {subTab === 'review' && <ReviewQueueView />}

      <SessionTerminalDock
        events={terminalEvents}
        collapsed={terminalCollapsed}
        onToggle={handleTerminalToggle}
      />
    </div>
  );
}
