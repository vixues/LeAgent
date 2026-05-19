import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { generateId } from '@/lib/utils';

export interface FeatureFlags {
  enablePlayground: boolean;
  enableWebhooks: boolean;
  enableScheduledFlows: boolean;
  enableCollaboration: boolean;
  enableAIAssistant: boolean;
  enableAdvancedEditing: boolean;
  enableDarkMode: boolean;
  enableExperimentalFeatures: boolean;
  maxFlowNodes: number;
  maxConcurrentExecutions: number;
}

interface LoadingState {
  id: string;
  key: string;
  message?: string;
  startedAt: number;
}

interface UtilityState {
  clientId: string;
  awaitingBotResponse: boolean;
  featureFlags: FeatureFlags;
  isOnline: boolean;
  isSidebarOpen: boolean;
  isCommandPaletteOpen: boolean;
  loadingStates: LoadingState[];
  lastActivityAt: number;

  setClientId: (id: string) => void;
  generateClientId: () => string;
  setAwaitingBotResponse: (awaiting: boolean) => void;
  setFeatureFlags: (flags: Partial<FeatureFlags>) => void;
  isFeatureEnabled: (feature: keyof FeatureFlags) => boolean;
  setIsOnline: (online: boolean) => void;
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;
  setCommandPaletteOpen: (open: boolean) => void;
  toggleCommandPalette: () => void;
  
  startLoading: (key: string, message?: string) => string;
  stopLoading: (id: string) => void;
  stopLoadingByKey: (key: string) => void;
  isLoading: (key?: string) => boolean;
  getLoadingMessage: (key: string) => string | undefined;
  
  updateActivity: () => void;
  getIdleTime: () => number;
}

const DEFAULT_FEATURE_FLAGS: FeatureFlags = {
  enablePlayground: true,
  enableWebhooks: true,
  enableScheduledFlows: true,
  enableCollaboration: false,
  enableAIAssistant: true,
  enableAdvancedEditing: true,
  enableDarkMode: true,
  enableExperimentalFeatures: false,
  maxFlowNodes: 100,
  maxConcurrentExecutions: 5,
};

export const useUtilityStore = create<UtilityState>()(
  persist(
    (set, get) => ({
      clientId: generateId(),
      awaitingBotResponse: false,
      featureFlags: DEFAULT_FEATURE_FLAGS,
      isOnline: typeof navigator !== 'undefined' ? navigator.onLine : true,
      isSidebarOpen: true,
      isCommandPaletteOpen: false,
      loadingStates: [],
      lastActivityAt: Date.now(),

      setClientId: (clientId) => set({ clientId }),

      generateClientId: () => {
        const newId = generateId();
        set({ clientId: newId });
        return newId;
      },

      setAwaitingBotResponse: (awaitingBotResponse) => set({ awaitingBotResponse }),

      setFeatureFlags: (flags) =>
        set((state) => ({
          featureFlags: { ...state.featureFlags, ...flags },
        })),

      isFeatureEnabled: (feature) => {
        const value = get().featureFlags[feature];
        return typeof value === 'boolean' ? value : value > 0;
      },

      setIsOnline: (isOnline) => set({ isOnline }),

      setSidebarOpen: (isSidebarOpen) => set({ isSidebarOpen }),

      toggleSidebar: () =>
        set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),

      setCommandPaletteOpen: (isCommandPaletteOpen) => set({ isCommandPaletteOpen }),

      toggleCommandPalette: () =>
        set((state) => ({ isCommandPaletteOpen: !state.isCommandPaletteOpen })),

      startLoading: (key, message) => {
        const id = generateId();
        set((state) => ({
          loadingStates: [
            ...state.loadingStates,
            { id, key, message, startedAt: Date.now() },
          ],
        }));
        return id;
      },

      stopLoading: (id) =>
        set((state) => ({
          loadingStates: state.loadingStates.filter((ls) => ls.id !== id),
        })),

      stopLoadingByKey: (key) =>
        set((state) => ({
          loadingStates: state.loadingStates.filter((ls) => ls.key !== key),
        })),

      isLoading: (key) => {
        const { loadingStates } = get();
        if (!key) return loadingStates.length > 0;
        return loadingStates.some((ls) => ls.key === key);
      },

      getLoadingMessage: (key) =>
        get().loadingStates.find((ls) => ls.key === key)?.message,

      updateActivity: () => set({ lastActivityAt: Date.now() }),

      getIdleTime: () => Date.now() - get().lastActivityAt,
    }),
    {
      name: 'leagent-utility',
      partialize: (state) => ({
        clientId: state.clientId,
        featureFlags: state.featureFlags,
        isSidebarOpen: state.isSidebarOpen,
      }),
    }
  )
);

if (typeof window !== 'undefined') {
  window.addEventListener('online', () => useUtilityStore.getState().setIsOnline(true));
  window.addEventListener('offline', () => useUtilityStore.getState().setIsOnline(false));
}
