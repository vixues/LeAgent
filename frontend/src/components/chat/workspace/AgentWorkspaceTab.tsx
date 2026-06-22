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
import { useChatStore } from '@/stores/chat';
import { useCodeArtifactStore, type CodeArtifactEntry } from '@/stores/codeArtifact';
import { SessionHeader } from './code/SessionHeader';
import { ChangedFilesRail } from './code/ChangedFilesRail';
import { ArtifactsRail } from './code/ArtifactsRail';
import { AgentSessionTimeline } from './code/AgentSessionTimeline';
import { SessionTerminalDock } from './code/SessionTerminalDock';
import { eventKindMeta } from './code/eventMeta';

const EMPTY_CODE_ARTIFACT_IDS: string[] = [];
const EMPTY_CODE_ARTIFACTS: CodeArtifactEntry[] = [];

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
  const autoExpandedRef = useRef<Set<string>>(new Set());

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

  // --- Empty state ---

  if (events.length === 0) {
    return (
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

      <SessionTerminalDock
        events={terminalEvents}
        collapsed={terminalCollapsed}
        onToggle={() => setTerminalCollapsed((v) => !v)}
      />
    </div>
  );
}
