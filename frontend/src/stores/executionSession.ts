import { create } from 'zustand';

export type SessionExecutionStatus = 'idle' | 'running' | 'blocked' | 'completed' | 'failed';

export interface CapabilityLogEntry {
  id: string;
  toolCallId: string;
  name: string;
  status: 'running' | 'success' | 'error' | 'awaiting_user';
  timestamp: string;
  error?: string;
}

/** Unified execution timeline entry for a chat session. */
export interface SessionExecutionEntry {
  runId: string;
  scope: string;
  parentRunId?: string | null;
  promptId?: string | null;
  status: SessionExecutionStatus;
  agentTaskId?: string;
  pauseToken?: Record<string, unknown> | null;
  capabilityLog: CapabilityLogEntry[];
  updatedAt: string;
}

export interface SessionExecutionHydrationRow {
  run_id: string;
  scope: string;
  parent_run_id?: string | null;
  prompt_id?: string | null;
  status?: string;
  pause_token?: Record<string, unknown> | null;
}

interface ExecutionSessionState {
  bySession: Record<string, SessionExecutionEntry>;
  upsertFromStarted: (
    sessionId: string,
    data: { runId: string; scope?: string; promptId?: string | null; parentRunId?: string | null },
  ) => void;
  setAgentTaskId: (sessionId: string, taskId: string) => void;
  setPromptId: (sessionId: string, promptId: string) => void;
  setStatus: (sessionId: string, status: SessionExecutionStatus) => void;
  setPauseToken: (sessionId: string, pauseToken: Record<string, unknown> | null) => void;
  hydrateExecutions: (sessionId: string, runs: SessionExecutionHydrationRow[]) => void;
  appendCapability: (sessionId: string, entry: CapabilityLogEntry) => void;
  updateCapability: (
    sessionId: string,
    toolCallId: string,
    patch: Partial<Pick<CapabilityLogEntry, 'status' | 'error' | 'name'>>,
  ) => void;
  markWorkflowDone: (
    sessionId: string,
    data?: { promptId?: string; runId?: string; success?: boolean },
  ) => void;
  clearSession: (sessionId: string) => void;
  remapSession: (oldSessionId: string, newSessionId: string) => void;
}

function mapHydrationStatus(raw?: string): SessionExecutionStatus {
  if (raw === 'blocked') return 'blocked';
  if (raw === 'failed') return 'failed';
  if (raw === 'completed') return 'completed';
  return 'running';
}

function mergeEntry(
  prev: SessionExecutionEntry | undefined,
  patch: Partial<SessionExecutionEntry> & { runId: string },
): SessionExecutionEntry {
  const now = new Date().toISOString();
  return {
    runId: patch.runId,
    scope: patch.scope ?? prev?.scope ?? 'chat_turn',
    parentRunId: patch.parentRunId ?? prev?.parentRunId,
    promptId: patch.promptId ?? prev?.promptId,
    status: patch.status ?? prev?.status ?? 'running',
    agentTaskId: patch.agentTaskId ?? prev?.agentTaskId,
    pauseToken: patch.pauseToken !== undefined ? patch.pauseToken : prev?.pauseToken,
    capabilityLog: patch.capabilityLog ?? prev?.capabilityLog ?? [],
    updatedAt: now,
  };
}

export const useExecutionSessionStore = create<ExecutionSessionState>((set, get) => ({
  bySession: {},

  upsertFromStarted: (sessionId, data) => {
    set((state) => {
      const prev = state.bySession[sessionId];
      return {
        bySession: {
          ...state.bySession,
          [sessionId]: mergeEntry(prev, {
            runId: data.runId,
            scope: data.scope,
            promptId: data.promptId,
            parentRunId: data.parentRunId,
            status: 'running',
            capabilityLog: prev?.capabilityLog ?? [],
          }),
        },
      };
    });
  },

  setAgentTaskId: (sessionId, taskId) => {
    const prev = get().bySession[sessionId];
    if (!prev) {
      set((state) => ({
        bySession: {
          ...state.bySession,
          [sessionId]: mergeEntry(undefined, {
            runId: taskId,
            scope: 'chat_turn',
            agentTaskId: taskId,
            status: 'running',
            capabilityLog: [],
          }),
        },
      }));
      return;
    }
    set((state) => ({
      bySession: {
        ...state.bySession,
        [sessionId]: mergeEntry(prev, { runId: prev.runId, agentTaskId: taskId }),
      },
    }));
  },

  setPromptId: (sessionId, promptId) => {
    set((state) => {
      const prev = state.bySession[sessionId];
      const base =
        prev ??
        mergeEntry(undefined, {
          runId: promptId,
          scope: 'workflow',
          status: 'running',
          capabilityLog: [],
        });
      return {
        bySession: {
          ...state.bySession,
          [sessionId]: mergeEntry(base, { runId: base.runId, promptId }),
        },
      };
    });
  },

  setStatus: (sessionId, status) => {
    const prev = get().bySession[sessionId];
    if (!prev) return;
    set((state) => ({
      bySession: {
        ...state.bySession,
        [sessionId]: mergeEntry(prev, { runId: prev.runId, status }),
      },
    }));
  },

  setPauseToken: (sessionId, pauseToken) => {
    const prev = get().bySession[sessionId];
    if (!prev) return;
    set((state) => ({
      bySession: {
        ...state.bySession,
        [sessionId]: mergeEntry(prev, {
          runId: prev.runId,
          pauseToken,
          status: pauseToken ? 'blocked' : prev.status,
        }),
      },
    }));
  },

  hydrateExecutions: (sessionId, runs) => {
    if (!runs.length) return;
    const primary = runs[0]!;
    set((state) => {
      const prev = state.bySession[sessionId];
      return {
        bySession: {
          ...state.bySession,
          [sessionId]: mergeEntry(prev, {
            runId: primary.run_id,
            scope: primary.scope,
            parentRunId: primary.parent_run_id,
            promptId: primary.prompt_id,
            status: mapHydrationStatus(primary.status),
            pauseToken: primary.pause_token ?? null,
            capabilityLog: prev?.capabilityLog ?? [],
          }),
        },
      };
    });
  },

  appendCapability: (sessionId, entry) => {
    set((state) => {
      const prev = state.bySession[sessionId];
      const base = prev ?? mergeEntry(undefined, {
        runId: entry.toolCallId,
        scope: 'chat_turn',
        status: 'running',
        capabilityLog: [],
      });
      const withoutDup = base.capabilityLog.filter((e) => e.toolCallId !== entry.toolCallId);
      return {
        bySession: {
          ...state.bySession,
          [sessionId]: mergeEntry(base, {
            runId: base.runId,
            capabilityLog: [...withoutDup, entry],
          }),
        },
      };
    });
  },

  updateCapability: (sessionId, toolCallId, patch) => {
    set((state) => {
      const prev = state.bySession[sessionId];
      if (!prev) return state;
      return {
        bySession: {
          ...state.bySession,
          [sessionId]: mergeEntry(prev, {
            runId: prev.runId,
            capabilityLog: prev.capabilityLog.map((e) =>
              e.toolCallId === toolCallId ? { ...e, ...patch } : e,
            ),
          }),
        },
      };
    });
  },

  markWorkflowDone: (sessionId, data) => {
    const prev = get().bySession[sessionId];
    if (!prev) return;
    set((state) => ({
      bySession: {
        ...state.bySession,
        [sessionId]: mergeEntry(prev, {
          runId: data?.runId ?? prev.runId,
          promptId: data?.promptId ?? prev.promptId,
          status: data?.success === false ? 'failed' : 'completed',
        }),
      },
    }));
  },

  clearSession: (sessionId) => {
    set((state) => {
      const next = { ...state.bySession };
      delete next[sessionId];
      return { bySession: next };
    });
  },

  remapSession: (oldSessionId, newSessionId) => {
    if (oldSessionId === newSessionId) return;
    set((state) => {
      const entry = state.bySession[oldSessionId];
      if (!entry) return state;
      const next = { ...state.bySession };
      delete next[oldSessionId];
      next[newSessionId] = { ...entry, updatedAt: new Date().toISOString() };
      return { bySession: next };
    });
  },
}));
