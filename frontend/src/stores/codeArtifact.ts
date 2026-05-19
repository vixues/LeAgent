import { create } from 'zustand';

export type CodeArtifactKind = 'execute' | 'file_write' | 'file_edit' | 'file_patch' | 'snippet';

export interface CodeArtifactEntry {
  artifactId: string;
  kind: CodeArtifactKind;
  language: string;
  originTool: string;
  targetPath?: string;
  syntaxValid?: boolean | null;
  diagnostics?: Array<{ message: string; line?: number; column?: number }>;
  sessionId: string;
  receivedAt: string;
}

interface CodeArtifactState {
  entries: Record<string, CodeArtifactEntry>;
  bySession: Record<string, string[]>;

  addEntry: (entry: CodeArtifactEntry) => void;
  listForSession: (sessionId: string) => CodeArtifactEntry[];
  clearForSession: (sessionId: string) => void;
}

export const useCodeArtifactStore = create<CodeArtifactState>()((set, get) => ({
  entries: {},
  bySession: {},

  addEntry: (entry) =>
    set((state) => {
      const sessionList = [...(state.bySession[entry.sessionId] ?? []), entry.artifactId];
      return {
        entries: { ...state.entries, [entry.artifactId]: entry },
        bySession: { ...state.bySession, [entry.sessionId]: sessionList },
      };
    }),

  listForSession: (sessionId) => {
    const s = get();
    const ids = s.bySession[sessionId] ?? [];
    return ids
      .map((id) => s.entries[id])
      .filter((entry): entry is CodeArtifactEntry => Boolean(entry));
  },

  clearForSession: (sessionId) =>
    set((state) => {
      const ids = state.bySession[sessionId] ?? [];
      const nextEntries = { ...state.entries };
      for (const id of ids) {
        delete nextEntries[id];
      }
      const nextBySession = { ...state.bySession };
      delete nextBySession[sessionId];
      return { entries: nextEntries, bySession: nextBySession };
    }),
}));
