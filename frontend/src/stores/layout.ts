import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type WorkspaceTab = 'files' | 'agent' | 'preview' | 'snippets' | 'memory';

const VALID_WORKSPACE_TABS: WorkspaceTab[] = ['files', 'agent', 'preview', 'snippets', 'memory'];

export function isWorkspaceTab(value: unknown): value is WorkspaceTab {
  return typeof value === 'string' && (VALID_WORKSPACE_TABS as readonly string[]).includes(value);
}

interface LayoutStore {
  sidebarCollapsed: boolean;
  chatHistoryOpen: boolean;
  workspaceOpen: boolean;
  workspaceTab: WorkspaceTab;
  focusMode: boolean;

  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleChatHistory: () => void;
  setChatHistoryOpen: (open: boolean) => void;
  toggleWorkspace: () => void;
  setWorkspaceOpen: (open: boolean) => void;
  setWorkspaceTab: (tab: WorkspaceTab) => void;
  toggleFocusMode: () => void;
  setFocusMode: (on: boolean) => void;
}

export const useLayoutStore = create<LayoutStore>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      chatHistoryOpen: false,
      workspaceOpen: false,
      workspaceTab: 'files',
      focusMode: false,

      toggleSidebar: () =>
        set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
      setSidebarCollapsed: (collapsed) =>
        set({ sidebarCollapsed: collapsed }),
      toggleChatHistory: () =>
        set((state) => ({ chatHistoryOpen: !state.chatHistoryOpen })),
      setChatHistoryOpen: (open) =>
        set({ chatHistoryOpen: open }),
      toggleWorkspace: () =>
        set((state) => ({ workspaceOpen: !state.workspaceOpen })),
      setWorkspaceOpen: (open) =>
        set({ workspaceOpen: open }),
      setWorkspaceTab: (tab) =>
        set({ workspaceTab: tab }),
      toggleFocusMode: () =>
        set((state) => ({ focusMode: !state.focusMode })),
      setFocusMode: (on) =>
        set({ focusMode: on }),
    }),
    {
      name: 'leagent-layout',
      version: 1,
      migrate: (persisted, fromVersion) => {
        const p = persisted as { workspaceTab?: string };
        if (fromVersion === 0 && p?.workspaceTab === 'folders') {
          return { ...p, workspaceTab: 'agent' };
        }
        return persisted;
      },
      partialize: (state) => ({
        sidebarCollapsed: state.sidebarCollapsed,
        chatHistoryOpen: state.chatHistoryOpen,
        workspaceOpen: state.workspaceOpen,
        workspaceTab: state.workspaceTab,
        focusMode: state.focusMode,
      }),
    }
  )
);
