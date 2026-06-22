import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { apiClient } from '@/api/client';
import {
  namespacedPersistName,
  registerNamespacedStore,
} from '@/lib/persistNamespace';
import type { ChatProject } from '@/types/chat';

const CHAT_PROJECTS_STORE_BASE = 'leagent-chat-projects';
registerNamespacedStore(CHAT_PROJECTS_STORE_BASE);
const TOKEN_STORAGE_KEY = 'leagent-chat-project-unlocks';

interface ChatProjectResponse {
  id: string;
  user_id: string;
  workspace_id?: string | null;
  name: string;
  description?: string | null;
  design_context?: string | null;
  settings?: string | null;
  has_password: boolean;
  is_locked: boolean;
  session_count: number;
  created_at: string;
  updated_at: string;
}

interface UnlockResponse {
  project_id: string;
  token: string;
  expires_at: number;
}

interface StoredUnlockToken {
  token: string;
  expiresAt: number;
}

interface ChatProjectsStore {
  projects: ChatProject[];
  currentProjectId: string | null;
  isLoading: boolean;
  error: string | null;

  fetchProjects: () => Promise<void>;
  createProject: (input: {
    name: string;
    description?: string | null;
    designContext?: string | null;
    password?: string | null;
  }) => Promise<string>;
  updateProject: (
    projectId: string,
    input: {
      name?: string;
      description?: string | null;
      designContext?: string | null;
      password?: string | null;
      clearPassword?: boolean;
    },
  ) => Promise<void>;
  deleteProject: (projectId: string) => Promise<void>;
  unlockProject: (projectId: string, password: string) => Promise<void>;
  selectProject: (projectId: string | null) => void;
  getUnlockToken: (projectId?: string | null) => string | null;
  isProjectUnlocked: (projectId?: string | null) => boolean;
  clearProjectUnlock: (projectId: string) => void;
}

function mapProject(p: ChatProjectResponse): ChatProject {
  return {
    id: p.id,
    userId: p.user_id,
    workspaceId: p.workspace_id,
    name: p.name,
    description: p.description,
    designContext: p.design_context,
    settings: p.settings,
    hasPassword: p.has_password,
    isLocked: p.is_locked,
    sessionCount: p.session_count,
    createdAt: p.created_at,
    updatedAt: p.updated_at,
  };
}

function readTokens(): Record<string, StoredUnlockToken> {
  try {
    const raw = window.sessionStorage.getItem(TOKEN_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, StoredUnlockToken>;
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function writeTokens(tokens: Record<string, StoredUnlockToken>) {
  try {
    window.sessionStorage.setItem(TOKEN_STORAGE_KEY, JSON.stringify(tokens));
  } catch {
    /* sessionStorage can be unavailable in hardened browsers */
  }
}

function getStoredToken(projectId?: string | null): string | null {
  if (!projectId || typeof window === 'undefined') return null;
  const tokens = readTokens();
  const entry = tokens[projectId];
  if (!entry) return null;
  if (entry.expiresAt * 1000 <= Date.now()) {
    delete tokens[projectId];
    writeTokens(tokens);
    return null;
  }
  return entry.token;
}

function storeToken(projectId: string, token: string, expiresAt: number) {
  const tokens = readTokens();
  tokens[projectId] = { token, expiresAt };
  writeTokens(tokens);
}

function removeToken(projectId: string) {
  const tokens = readTokens();
  delete tokens[projectId];
  writeTokens(tokens);
}

function projectHeaders(projectId?: string | null): Record<string, string> | undefined {
  const token = getStoredToken(projectId);
  return token ? { 'X-Chat-Project-Token': token } : undefined;
}

export function getChatProjectUnlockToken(projectId?: string | null): string | null {
  return getStoredToken(projectId);
}

export function getChatProjectHeaders(projectId?: string | null): Record<string, string> | undefined {
  return projectHeaders(projectId);
}

export const useChatProjectStore = create<ChatProjectsStore>()(
  persist(
    (set, get) => ({
      projects: [],
      currentProjectId: null,
      isLoading: false,
      error: null,

      fetchProjects: async () => {
        set({ isLoading: true, error: null });
        try {
          const res = await apiClient.get<ChatProjectResponse[]>('/chat-projects');
          set({ projects: res.map(mapProject), isLoading: false });
        } catch (error) {
          set({
            isLoading: false,
            error: error instanceof Error ? error.message : 'Failed to load projects',
          });
        }
      },

      createProject: async (input) => {
        const res = await apiClient.post<ChatProjectResponse>('/chat-projects', {
          name: input.name,
          description: input.description,
          design_context: input.designContext,
          password: input.password || undefined,
        });
        const project = mapProject(res);
        set((state) => ({
          projects: [project, ...state.projects.filter((p) => p.id !== project.id)],
          currentProjectId: project.id,
        }));
        return project.id;
      },

      updateProject: async (projectId, input) => {
        const res = await apiClient.patch<ChatProjectResponse>(
          `/chat-projects/${projectId}`,
          {
            name: input.name,
            description: input.description,
            design_context: input.designContext,
            password: input.password || undefined,
            clear_password: input.clearPassword,
          },
        );
        const project = mapProject(res);
        if (input.clearPassword || input.password) {
          removeToken(projectId);
        }
        set((state) => ({
          projects: state.projects.map((p) => (p.id === projectId ? project : p)),
        }));
      },

      deleteProject: async (projectId) => {
        await apiClient.delete<void>(`/chat-projects/${projectId}`);
        removeToken(projectId);
        set((state) => ({
          projects: state.projects.filter((p) => p.id !== projectId),
          currentProjectId:
            state.currentProjectId === projectId ? null : state.currentProjectId,
        }));
      },

      unlockProject: async (projectId, password) => {
        const res = await apiClient.post<UnlockResponse>(
          `/chat-projects/${projectId}/unlock`,
          { password },
        );
        storeToken(projectId, res.token, res.expires_at);
        set((state) => ({
          projects: state.projects.map((p) =>
            p.id === projectId ? { ...p, isLocked: false } : p,
          ),
        }));
      },

      selectProject: (projectId) => {
        set({ currentProjectId: projectId });
      },

      getUnlockToken: (projectId) => getStoredToken(projectId ?? get().currentProjectId),
      isProjectUnlocked: (projectId) => {
        const id = projectId ?? get().currentProjectId;
        if (!id) return true;
        const project = get().projects.find((p) => p.id === id);
        return !project?.hasPassword || Boolean(getStoredToken(id));
      },
      clearProjectUnlock: (projectId) => {
        removeToken(projectId);
        set((state) => ({
          projects: state.projects.map((p) =>
            p.id === projectId && p.hasPassword ? { ...p, isLocked: true } : p,
          ),
        }));
      },
    }),
    {
      name: namespacedPersistName(CHAT_PROJECTS_STORE_BASE),
      partialize: (state) => ({
        projects: state.projects,
        currentProjectId: state.currentProjectId,
      }),
    },
  ),
);
