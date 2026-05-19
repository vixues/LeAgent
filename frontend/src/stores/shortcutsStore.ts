import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface KeyboardShortcut {
  id: string;
  name: string;
  description?: string;
  keys: string[];
  category: ShortcutCategory;
  action: string;
  isEnabled: boolean;
  isCustom?: boolean;
}

export type ShortcutCategory = 
  | 'general'
  | 'editor'
  | 'flow'
  | 'navigation'
  | 'view'
  | 'file'
  | 'debug';

export interface ShortcutContext {
  isEditorFocused: boolean;
  isInputFocused: boolean;
  isModalOpen: boolean;
  activePanel?: string;
}

type ShortcutHandler = (context: ShortcutContext) => void | boolean;

interface ShortcutsState {
  shortcuts: KeyboardShortcut[];
  handlers: Map<string, ShortcutHandler>;
  isEnabled: boolean;
  context: ShortcutContext;

  registerHandler: (action: string, handler: ShortcutHandler) => void;
  unregisterHandler: (action: string) => void;
  
  updateShortcut: (id: string, keys: string[]) => void;
  resetShortcut: (id: string) => void;
  resetAllShortcuts: () => void;
  
  enableShortcut: (id: string) => void;
  disableShortcut: (id: string) => void;
  toggleShortcut: (id: string) => void;
  
  setEnabled: (enabled: boolean) => void;
  setContext: (context: Partial<ShortcutContext>) => void;
  
  getShortcut: (id: string) => KeyboardShortcut | undefined;
  getShortcutByAction: (action: string) => KeyboardShortcut | undefined;
  getShortcutsByCategory: (category: ShortcutCategory) => KeyboardShortcut[];
  
  executeShortcut: (keys: string[]) => boolean;
  formatKeys: (keys: string[]) => string;
  parseKeyEvent: (event: KeyboardEvent) => string[];
  
  hasConflict: (keys: string[], excludeId?: string) => KeyboardShortcut | undefined;
  addCustomShortcut: (shortcut: Omit<KeyboardShortcut, 'id' | 'isCustom'>) => string;
  removeCustomShortcut: (id: string) => void;
}

const DEFAULT_SHORTCUTS: KeyboardShortcut[] = [
  { id: 'save', name: 'Save', keys: ['Ctrl', 'S'], category: 'file', action: 'file:save', isEnabled: true },
  { id: 'save-as', name: 'Save As', keys: ['Ctrl', 'Shift', 'S'], category: 'file', action: 'file:save-as', isEnabled: true },
  { id: 'new-flow', name: 'New Flow', keys: ['Ctrl', 'N'], category: 'file', action: 'file:new-flow', isEnabled: true },
  { id: 'open-flow', name: 'Open Flow', keys: ['Ctrl', 'O'], category: 'file', action: 'file:open-flow', isEnabled: true },
  
  { id: 'undo', name: 'Undo', keys: ['Ctrl', 'Z'], category: 'editor', action: 'editor:undo', isEnabled: true },
  { id: 'redo', name: 'Redo', keys: ['Ctrl', 'Shift', 'Z'], category: 'editor', action: 'editor:redo', isEnabled: true },
  { id: 'copy', name: 'Copy', keys: ['Ctrl', 'C'], category: 'editor', action: 'editor:copy', isEnabled: true },
  { id: 'paste', name: 'Paste', keys: ['Ctrl', 'V'], category: 'editor', action: 'editor:paste', isEnabled: true },
  { id: 'cut', name: 'Cut', keys: ['Ctrl', 'X'], category: 'editor', action: 'editor:cut', isEnabled: true },
  { id: 'delete', name: 'Delete', keys: ['Delete'], category: 'editor', action: 'editor:delete', isEnabled: true },
  { id: 'select-all', name: 'Select All', keys: ['Ctrl', 'A'], category: 'editor', action: 'editor:select-all', isEnabled: true },
  
  { id: 'zoom-in', name: 'Zoom In', keys: ['Ctrl', '+'], category: 'view', action: 'view:zoom-in', isEnabled: true },
  { id: 'zoom-out', name: 'Zoom Out', keys: ['Ctrl', '-'], category: 'view', action: 'view:zoom-out', isEnabled: true },
  { id: 'zoom-fit', name: 'Fit to View', keys: ['Ctrl', '0'], category: 'view', action: 'view:zoom-fit', isEnabled: true },
  { id: 'toggle-sidebar', name: 'Toggle Sidebar', keys: ['Ctrl', 'B'], category: 'view', action: 'view:toggle-sidebar', isEnabled: true },
  { id: 'toggle-minimap', name: 'Toggle Minimap', keys: ['Ctrl', 'M'], category: 'view', action: 'view:toggle-minimap', isEnabled: true },
  
  { id: 'run-flow', name: 'Run Flow', keys: ['F5'], category: 'flow', action: 'flow:run', isEnabled: true },
  { id: 'stop-flow', name: 'Stop Flow', keys: ['Shift', 'F5'], category: 'flow', action: 'flow:stop', isEnabled: true },
  { id: 'validate-flow', name: 'Validate Flow', keys: ['F6'], category: 'flow', action: 'flow:validate', isEnabled: true },
  { id: 'add-node', name: 'Add Node', keys: ['Ctrl', 'Shift', 'A'], category: 'flow', action: 'flow:add-node', isEnabled: true },
  
  { id: 'command-palette', name: 'Command Palette', keys: ['Ctrl', 'P'], category: 'general', action: 'general:command-palette', isEnabled: true },
  { id: 'search', name: 'Search', keys: ['Ctrl', 'F'], category: 'general', action: 'general:search', isEnabled: true },
  { id: 'settings', name: 'Settings', keys: ['Ctrl', ','], category: 'general', action: 'general:settings', isEnabled: true },
  { id: 'help', name: 'Help', keys: ['F1'], category: 'general', action: 'general:help', isEnabled: true },
  { id: 'escape', name: 'Cancel/Close', keys: ['Escape'], category: 'general', action: 'general:escape', isEnabled: true },
  
  { id: 'step-over', name: 'Step Over', keys: ['F10'], category: 'debug', action: 'debug:step-over', isEnabled: true },
  { id: 'step-into', name: 'Step Into', keys: ['F11'], category: 'debug', action: 'debug:step-into', isEnabled: true },
  { id: 'toggle-breakpoint', name: 'Toggle Breakpoint', keys: ['F9'], category: 'debug', action: 'debug:toggle-breakpoint', isEnabled: true },
];

const generateId = () => Math.random().toString(36).substring(2, 11);

const isMac = typeof navigator !== 'undefined' && /Mac/.test(navigator.platform);
const normalizeKey = (key: string): string => {
  if (isMac && key === 'Ctrl') return 'Cmd';
  return key;
};

export const useShortcutsStore = create<ShortcutsState>()(
  persist(
    (set, get) => ({
      shortcuts: DEFAULT_SHORTCUTS,
      handlers: new Map(),
      isEnabled: true,
      context: {
        isEditorFocused: false,
        isInputFocused: false,
        isModalOpen: false,
      },

      registerHandler: (action, handler) => {
        set((state) => {
          const newHandlers = new Map(state.handlers);
          newHandlers.set(action, handler);
          return { handlers: newHandlers };
        });
      },

      unregisterHandler: (action) => {
        set((state) => {
          const newHandlers = new Map(state.handlers);
          newHandlers.delete(action);
          return { handlers: newHandlers };
        });
      },

      updateShortcut: (id, keys) => {
        const conflict = get().hasConflict(keys, id);
        if (conflict) {
          throw new Error(`Shortcut conflicts with "${conflict.name}"`);
        }

        set((state) => ({
          shortcuts: state.shortcuts.map((s) =>
            s.id === id ? { ...s, keys } : s
          ),
        }));
      },

      resetShortcut: (id) => {
        const defaultShortcut = DEFAULT_SHORTCUTS.find((s) => s.id === id);
        if (defaultShortcut) {
          set((state) => ({
            shortcuts: state.shortcuts.map((s) =>
              s.id === id ? { ...s, keys: defaultShortcut.keys } : s
            ),
          }));
        }
      },

      resetAllShortcuts: () => {
        set((state) => ({
          shortcuts: state.shortcuts.map((s) => {
            const defaultShortcut = DEFAULT_SHORTCUTS.find((d) => d.id === s.id);
            return defaultShortcut ? { ...s, keys: defaultShortcut.keys } : s;
          }),
        }));
      },

      enableShortcut: (id) => {
        set((state) => ({
          shortcuts: state.shortcuts.map((s) =>
            s.id === id ? { ...s, isEnabled: true } : s
          ),
        }));
      },

      disableShortcut: (id) => {
        set((state) => ({
          shortcuts: state.shortcuts.map((s) =>
            s.id === id ? { ...s, isEnabled: false } : s
          ),
        }));
      },

      toggleShortcut: (id) => {
        set((state) => ({
          shortcuts: state.shortcuts.map((s) =>
            s.id === id ? { ...s, isEnabled: !s.isEnabled } : s
          ),
        }));
      },

      setEnabled: (isEnabled) => set({ isEnabled }),

      setContext: (context) =>
        set((state) => ({
          context: { ...state.context, ...context },
        })),

      getShortcut: (id) => get().shortcuts.find((s) => s.id === id),

      getShortcutByAction: (action) => get().shortcuts.find((s) => s.action === action),

      getShortcutsByCategory: (category) =>
        get().shortcuts.filter((s) => s.category === category),

      executeShortcut: (keys) => {
        const { shortcuts, handlers, isEnabled, context } = get();
        if (!isEnabled) return false;

        const normalizedKeys = keys.map(normalizeKey).sort();
        const shortcut = shortcuts.find((s) => {
          if (!s.isEnabled) return false;
          const shortcutKeys = s.keys.map(normalizeKey).sort();
          if (shortcutKeys.length !== normalizedKeys.length) return false;
          return shortcutKeys.every((k, i) => k === normalizedKeys[i]);
        });

        if (!shortcut) return false;

        const handler = handlers.get(shortcut.action);
        if (handler) {
          const result = handler(context);
          return result !== false;
        }

        return false;
      },

      formatKeys: (keys) => {
        return keys.map(normalizeKey).join(isMac ? '' : '+');
      },

      parseKeyEvent: (event) => {
        const keys: string[] = [];
        if (event.ctrlKey || event.metaKey) keys.push('Ctrl');
        if (event.shiftKey) keys.push('Shift');
        if (event.altKey) keys.push('Alt');
        
        const key = event.key;
        if (!['Control', 'Shift', 'Alt', 'Meta'].includes(key)) {
          if (key === ' ') {
            keys.push('Space');
          } else if (key.length === 1) {
            keys.push(key.toUpperCase());
          } else {
            keys.push(key);
          }
        }
        
        return keys;
      },

      hasConflict: (keys, excludeId) => {
        const normalizedKeys = keys.map(normalizeKey).sort();
        return get().shortcuts.find((s) => {
          if (s.id === excludeId) return false;
          const shortcutKeys = s.keys.map(normalizeKey).sort();
          if (shortcutKeys.length !== normalizedKeys.length) return false;
          return shortcutKeys.every((k, i) => k === normalizedKeys[i]);
        });
      },

      addCustomShortcut: (shortcut) => {
        const conflict = get().hasConflict(shortcut.keys);
        if (conflict) {
          throw new Error(`Shortcut conflicts with "${conflict.name}"`);
        }

        const id = generateId();
        set((state) => ({
          shortcuts: [...state.shortcuts, { ...shortcut, id, isCustom: true }],
        }));
        return id;
      },

      removeCustomShortcut: (id) => {
        set((state) => ({
          shortcuts: state.shortcuts.filter((s) => s.id !== id || !s.isCustom),
        }));
      },
    }),
    {
      name: 'leagent-shortcuts',
      partialize: (state) => ({
        shortcuts: state.shortcuts,
        isEnabled: state.isEnabled,
      }),
    }
  )
);

export function initializeShortcutListener() {
  if (typeof window === 'undefined') return;

  const handleKeyDown = (event: KeyboardEvent) => {
    const target = event.target as HTMLElement;
    const isInput = target.tagName === 'INPUT' || 
                    target.tagName === 'TEXTAREA' || 
                    target.isContentEditable;
    
    useShortcutsStore.getState().setContext({ isInputFocused: isInput });
    
    const keys = useShortcutsStore.getState().parseKeyEvent(event);
    if (keys.length > 0) {
      const handled = useShortcutsStore.getState().executeShortcut(keys);
      if (handled) {
        event.preventDefault();
        event.stopPropagation();
      }
    }
  };

  window.addEventListener('keydown', handleKeyDown);
  return () => window.removeEventListener('keydown', handleKeyDown);
}
