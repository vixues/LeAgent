import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type Language = 'zh-CN' | 'en-US' | 'ja-JP';
export type EditorLayout = 'horizontal' | 'vertical' | 'tabs';
export type NodeSize = 'compact' | 'default' | 'large';

export interface EditorSettings {
  autoSaveEnabled: boolean;
  autoSaveInterval: number;
  snapToGrid: boolean;
  gridSize: number;
  showMiniMap: boolean;
  showNodeLabels: boolean;
  animateConnections: boolean;
  nodeSize: NodeSize;
  layout: EditorLayout;
  defaultZoom: number;
  fitViewOnLoad: boolean;
}

export interface NotificationSettings {
  enabled: boolean;
  sound: boolean;
  desktop: boolean;
  flowComplete: boolean;
  flowError: boolean;
  mentions: boolean;
}

export interface PrivacySettings {
  shareUsageData: boolean;
  shareCrashReports: boolean;
  storeHistoryLocally: boolean;
  historyRetentionDays: number;
}

export interface AccessibilitySettings {
  reduceMotion: boolean;
  highContrast: boolean;
  fontSize: 'small' | 'medium' | 'large';
  keyboardNavigation: boolean;
}

export interface AppSettings {
  language: Language;
  editor: EditorSettings;
  notifications: NotificationSettings;
  privacy: PrivacySettings;
  accessibility: AccessibilitySettings;
}

interface SettingsState {
  settings: AppSettings;
  isLoading: boolean;

  updateSettings: (updates: Partial<AppSettings>) => void;
  updateEditorSettings: (updates: Partial<EditorSettings>) => void;
  updateNotificationSettings: (updates: Partial<NotificationSettings>) => void;
  updatePrivacySettings: (updates: Partial<PrivacySettings>) => void;
  updateAccessibilitySettings: (updates: Partial<AccessibilitySettings>) => void;
  
  setLanguage: (language: Language) => void;
  getLanguage: () => Language;
  
  resetToDefaults: () => void;
  resetEditorDefaults: () => void;
  
  exportSettings: () => string;
  importSettings: (settingsJson: string) => boolean;
}

const DEFAULT_EDITOR_SETTINGS: EditorSettings = {
  autoSaveEnabled: true,
  autoSaveInterval: 30000,
  snapToGrid: true,
  gridSize: 20,
  showMiniMap: true,
  showNodeLabels: true,
  animateConnections: true,
  nodeSize: 'default',
  layout: 'horizontal',
  defaultZoom: 1,
  fitViewOnLoad: true,
};

const DEFAULT_NOTIFICATION_SETTINGS: NotificationSettings = {
  enabled: true,
  sound: true,
  desktop: false,
  flowComplete: true,
  flowError: true,
  mentions: true,
};

const DEFAULT_PRIVACY_SETTINGS: PrivacySettings = {
  shareUsageData: false,
  shareCrashReports: true,
  storeHistoryLocally: true,
  historyRetentionDays: 30,
};

const DEFAULT_ACCESSIBILITY_SETTINGS: AccessibilitySettings = {
  reduceMotion: false,
  highContrast: false,
  fontSize: 'medium',
  keyboardNavigation: true,
};

const DEFAULT_SETTINGS: AppSettings = {
  language: 'zh-CN',
  editor: DEFAULT_EDITOR_SETTINGS,
  notifications: DEFAULT_NOTIFICATION_SETTINGS,
  privacy: DEFAULT_PRIVACY_SETTINGS,
  accessibility: DEFAULT_ACCESSIBILITY_SETTINGS,
};

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set, get) => ({
      settings: DEFAULT_SETTINGS,
      isLoading: false,

      updateSettings: (updates) =>
        set((state) => ({
          settings: { ...state.settings, ...updates },
        })),

      updateEditorSettings: (updates) =>
        set((state) => ({
          settings: {
            ...state.settings,
            editor: { ...state.settings.editor, ...updates },
          },
        })),

      updateNotificationSettings: (updates) =>
        set((state) => ({
          settings: {
            ...state.settings,
            notifications: { ...state.settings.notifications, ...updates },
          },
        })),

      updatePrivacySettings: (updates) =>
        set((state) => ({
          settings: {
            ...state.settings,
            privacy: { ...state.settings.privacy, ...updates },
          },
        })),

      updateAccessibilitySettings: (updates) =>
        set((state) => ({
          settings: {
            ...state.settings,
            accessibility: { ...state.settings.accessibility, ...updates },
          },
        })),

      setLanguage: (language) =>
        set((state) => ({
          settings: { ...state.settings, language },
        })),

      getLanguage: () => get().settings.language,

      resetToDefaults: () => set({ settings: DEFAULT_SETTINGS }),

      resetEditorDefaults: () =>
        set((state) => ({
          settings: {
            ...state.settings,
            editor: DEFAULT_EDITOR_SETTINGS,
          },
        })),

      exportSettings: () => JSON.stringify(get().settings, null, 2),

      importSettings: (settingsJson) => {
        try {
          const imported = JSON.parse(settingsJson) as Partial<AppSettings>;
          set((state) => ({
            settings: {
              ...state.settings,
              ...imported,
              editor: { ...state.settings.editor, ...imported.editor },
              notifications: { ...state.settings.notifications, ...imported.notifications },
              privacy: { ...state.settings.privacy, ...imported.privacy },
              accessibility: { ...state.settings.accessibility, ...imported.accessibility },
            },
          }));
          return true;
        } catch {
          return false;
        }
      },
    }),
    {
      name: 'leagent-settings',
    }
  )
);
