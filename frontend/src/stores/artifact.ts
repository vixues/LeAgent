import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { apiClient } from '@/api/client';
import type { Artifact, ArtifactStore } from '@/types/artifact';

export interface SessionCanvasArtifactDTO {
  id: string;
  canvas_id: string;
  revision: number;
  title: string;
  content_type: string;
  preview_path: string;
  message_id: string | null;
  trust: string;
}

export const useArtifactStore = create<ArtifactStore>()(
  persist(
    (set) => ({
      artifacts: {},
      pinnedIds: [],
      openArtifactId: null,
      openTabIds: [],
      activeTabId: null,

      addArtifact: (artifact) =>
        set((state) => ({
          artifacts: { ...state.artifacts, [artifact.id]: artifact },
        })),

      removeArtifact: (id) =>
        set((state) => {
          const next = { ...state.artifacts };
          delete next[id];
          return {
            artifacts: next,
            pinnedIds: state.pinnedIds.filter((pid) => pid !== id),
            openArtifactId: state.openArtifactId === id ? null : state.openArtifactId,
            openTabIds: state.openTabIds.filter((tid) => tid !== id),
            activeTabId: state.activeTabId === id
              ? state.openTabIds.filter((tid) => tid !== id)[0] ?? null
              : state.activeTabId,
          };
        }),

      openArtifact: (id) =>
        set((state) => ({
          openArtifactId: id,
          openTabIds: state.openTabIds.includes(id)
            ? state.openTabIds
            : [...state.openTabIds, id],
          activeTabId: id,
        })),

      closeArtifact: () => set({ openArtifactId: null }),

      openTab: (id) =>
        set((state) => ({
          openTabIds: state.openTabIds.includes(id)
            ? state.openTabIds
            : [...state.openTabIds, id],
          activeTabId: id,
          openArtifactId: id,
        })),

      closeTab: (id) =>
        set((state) => {
          const next = state.openTabIds.filter((tid) => tid !== id);
          const isActive = state.activeTabId === id;
          return {
            openTabIds: next,
            activeTabId: isActive ? (next[next.length - 1] ?? null) : state.activeTabId,
            openArtifactId:
              state.openArtifactId === id
                ? (next[next.length - 1] ?? null)
                : state.openArtifactId,
          };
        }),

      setActiveTab: (id) =>
        set({ activeTabId: id, openArtifactId: id }),

      pinArtifact: (id) =>
        set((state) => ({
          pinnedIds: state.pinnedIds.includes(id)
            ? state.pinnedIds
            : [...state.pinnedIds, id],
        })),

      unpinArtifact: (id) =>
        set((state) => ({
          pinnedIds: state.pinnedIds.filter((pid) => pid !== id),
        })),

      clearSessionArtifacts: (sessionId) =>
        set((state) => {
          const next: Record<string, Artifact> = {};
          for (const [k, v] of Object.entries(state.artifacts)) {
            if (v.sessionId !== sessionId) next[k] = v;
          }
          const remaining = new Set(Object.keys(next));
          return {
            artifacts: next,
            pinnedIds: state.pinnedIds.filter((id) => remaining.has(id)),
            openArtifactId:
              state.openArtifactId && !remaining.has(state.openArtifactId)
                ? null
                : state.openArtifactId,
            openTabIds: state.openTabIds.filter((id) => remaining.has(id)),
            activeTabId:
              state.activeTabId && !remaining.has(state.activeTabId)
                ? null
                : state.activeTabId,
          };
        }),

      remapArtifactsMessageId: (sessionId, oldMessageId, newMessageId) => {
        if (oldMessageId === newMessageId) return;
        set((state) => {
          const next: Record<string, Artifact> = {};
          for (const [k, v] of Object.entries(state.artifacts)) {
            if (v.sessionId === sessionId && v.messageId === oldMessageId) {
              next[k] = { ...v, messageId: newMessageId };
            } else {
              next[k] = v;
            }
          }
          return { artifacts: next };
        });
      },
    }),
    {
      name: 'leagent-artifacts',
      partialize: (state) => ({
        artifacts: state.artifacts,
        pinnedIds: state.pinnedIds,
      }),
    },
  ),
);

/** Merge server-stored canvases into the artifact store (history reload / new device). */
export async function hydrateSessionCanvasArtifacts(sessionId: string): Promise<void> {
  try {
    const items = await apiClient.get<SessionCanvasArtifactDTO[]>(
      `/canvas/by-session/${sessionId}`,
    );
    if (!Array.isArray(items) || items.length === 0) return;
    const { addArtifact } = useArtifactStore.getState();
    for (const a of items) {
      addArtifact({
        id: a.id,
        type: 'html',
        title: a.title,
        content: '',
        createdAt: new Date().toISOString(),
        sessionId,
        messageId: a.message_id ?? undefined,
        metadata: {
          previewPath: a.preview_path,
          canvasId: a.canvas_id,
          revision: a.revision,
          trust: a.trust ?? 'hosted',
          contentType: a.content_type,
        },
      });
    }
  } catch {
    // Canvas disabled or offline
  }
}
