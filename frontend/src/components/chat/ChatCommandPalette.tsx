import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import Fuse from 'fuse.js';
import {
  Search,
  Plus,
  PanelLeft,
  PanelRight,
  Trash2,
  FileText,
  MessageSquareText,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/stores/chat';
import { useLayoutStore } from '@/stores/layout';
import { useArtifactStore } from '@/stores/artifact';

interface PaletteAction {
  id: string;
  label: string;
  description?: string;
  icon: React.ReactNode;
  onSelect: () => void;
  section: 'actions' | 'sessions';
}

interface ChatCommandPaletteProps {
  open: boolean;
  onClose: () => void;
}

export function ChatCommandPalette({ open, onClose }: ChatCommandPaletteProps) {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const sessions = useChatStore((s) => s.sessions);
  const createSession = useChatStore((s) => s.createSession);
  const selectSession = useChatStore((s) => s.selectSession);
  const clearMessages = useChatStore((s) => s.clearMessages);
  const currentSessionId = useChatStore((s) => s.currentSessionId);
  const sidebarCollapsed = useLayoutStore((s) => s.sidebarCollapsed);
  const setSidebarCollapsed = useLayoutStore((s) => s.setSidebarCollapsed);
  const setChatHistoryOpen = useLayoutStore((s) => s.setChatHistoryOpen);
  const toggleWorkspace = useLayoutStore((s) => s.toggleWorkspace);
  const openTabIds = useArtifactStore((s) => s.openTabIds);
  const setActiveTab = useArtifactStore((s) => s.setActiveTab);

  const actions = useMemo<PaletteAction[]>(() => {
    const items: PaletteAction[] = [
      {
        id: 'new-chat',
        label: t('chat.newChatTitle', { defaultValue: 'New Chat' }),
        description: 'Start a fresh conversation',
        icon: <Plus className="w-4 h-4" />,
        onSelect: () => { createSession(); onClose(); },
        section: 'actions',
      },
      {
        id: 'open-main-nav',
        label: t('chat.openMainNavPalette', { defaultValue: 'Open navigation & history' }),
        description: t('chat.openMainNavPaletteDesc', {
          defaultValue: 'Expand the sidebar and chat history',
        }),
        icon: <PanelLeft className="w-4 h-4" />,
        onSelect: () => {
          if (sidebarCollapsed) setSidebarCollapsed(false);
          setChatHistoryOpen(true);
          onClose();
        },
        section: 'actions',
      },
      {
        id: 'toggle-workspace',
        label: t('chat.workspace.toggleAria', { defaultValue: 'Toggle Workspace' }),
        description: 'Show or hide the workspace panel',
        icon: <PanelRight className="w-4 h-4" />,
        onSelect: () => { toggleWorkspace(); onClose(); },
        section: 'actions',
      },
      {
        id: 'clear-messages',
        label: t('chat.clearMessages', { defaultValue: 'Clear Messages' }),
        description: 'Clear the current conversation',
        icon: <Trash2 className="w-4 h-4" />,
        onSelect: () => {
          if (currentSessionId) clearMessages(currentSessionId);
          onClose();
        },
        section: 'actions',
      },
    ];

    if (openTabIds.length > 0) {
      const lastTabId = openTabIds[openTabIds.length - 1]!;
      items.push({
        id: 'last-artifact',
        label: 'Open Last Artifact',
        description: 'Jump to the last opened artifact',
        icon: <FileText className="w-4 h-4" />,
        onSelect: () => {
          setActiveTab(lastTabId);
          onClose();
        },
        section: 'actions',
      });
    }

    sessions.forEach((session) => {
      items.push({
        id: `session-${session.id}`,
        label: session.title,
        description: session.preview,
        icon: <MessageSquareText className="w-4 h-4" />,
        onSelect: () => { selectSession(session.id); onClose(); },
        section: 'sessions',
      });
    });

    return items;
  }, [
    t, sessions, createSession, selectSession, clearMessages,
    currentSessionId,
    sidebarCollapsed,
    setSidebarCollapsed,
    setChatHistoryOpen,
    toggleWorkspace,
    openTabIds, setActiveTab, onClose,
  ]);

  const fuse = useMemo(
    () =>
      new Fuse(actions, {
        keys: ['label', 'description'],
        threshold: 0.4,
      }),
    [actions],
  );

  const filtered = useMemo(() => {
    if (!query.trim()) return actions;
    return fuse.search(query).map((r) => r.item);
  }, [query, fuse, actions]);

  useEffect(() => {
    setActiveIndex(0);
    setQuery('');
  }, [open]);

  useEffect(() => {
    if (open) {
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIndex((i) => (i + 1) % Math.max(1, filtered.length));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIndex(
          (i) => (i - 1 + filtered.length) % Math.max(1, filtered.length),
        );
      } else if (e.key === 'Enter' && filtered[activeIndex]) {
        e.preventDefault();
        filtered[activeIndex].onSelect();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    },
    [filtered, activeIndex, onClose],
  );

  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const item = list.children[activeIndex] as HTMLElement | undefined;
    item?.scrollIntoView({ block: 'nearest' });
  }, [activeIndex]);

  // Focus trap: close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);

  if (!open) return null;

  const actionItems = filtered.filter((i) => i.section === 'actions');
  const sessionItems = filtered.filter((i) => i.section === 'sessions');

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh] chat-palette-overlay"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="w-full max-w-lg rounded-2xl border border-border-subtle bg-surface shadow-lg chat-palette-dialog overflow-hidden"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label={t('chat.commandPalette', {
          defaultValue: 'Command palette',
        })}
      >
        {/* Search input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border-subtle">
          <Search className="w-4 h-4 text-muted-foreground-tertiary flex-shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActiveIndex(0);
            }}
            onKeyDown={handleKeyDown}
            placeholder={t('chat.commandPalettePlaceholder', {
              defaultValue: 'Search commands and sessions...',
            })}
            className="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground-tertiary focus:outline-none"
          />
          <kbd className="hidden sm:inline-flex px-1.5 py-0.5 rounded text-[10px] font-mono text-muted-foreground-tertiary bg-surface-sunken border border-border-subtle">
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div
          ref={listRef}
          className="max-h-80 overflow-y-auto p-1"
          role="listbox"
        >
          {filtered.length === 0 && (
            <div className="flex items-center justify-center py-8 text-sm text-muted-foreground-tertiary">
              {t('chat.noResults', { defaultValue: 'No results found' })}
            </div>
          )}

          {actionItems.length > 0 && (
            <>
              <div className="px-3 pt-2 pb-1">
                <p className="text-[11px] font-semibold text-muted-foreground-tertiary uppercase tracking-wider">
                  {t('chat.actions', { defaultValue: 'Actions' })}
                </p>
              </div>
              {actionItems.map((item) => {
                const idx = filtered.indexOf(item);
                return (
                  <PaletteItem
                    key={item.id}
                    item={item}
                    active={idx === activeIndex}
                    onSelect={item.onSelect}
                    onHover={() => setActiveIndex(idx)}
                  />
                );
              })}
            </>
          )}

          {sessionItems.length > 0 && (
            <>
              <div className="px-3 pt-3 pb-1">
                <p className="text-[11px] font-semibold text-muted-foreground-tertiary uppercase tracking-wider">
                  {t('chat.sessions', { defaultValue: 'Sessions' })}
                </p>
              </div>
              {sessionItems.map((item) => {
                const idx = filtered.indexOf(item);
                return (
                  <PaletteItem
                    key={item.id}
                    item={item}
                    active={idx === activeIndex}
                    onSelect={item.onSelect}
                    onHover={() => setActiveIndex(idx)}
                  />
                );
              })}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-4 py-2 border-t border-border-subtle text-[11px] text-muted-foreground-tertiary">
          <span>
            <kbd className="px-1 py-0.5 rounded bg-surface-sunken border border-border-subtle font-mono mr-0.5">
              ↑↓
            </kbd>
            navigate
          </span>
          <span>
            <kbd className="px-1 py-0.5 rounded bg-surface-sunken border border-border-subtle font-mono mr-0.5">
              ⏎
            </kbd>
            select
          </span>
          <span>
            <kbd className="px-1 py-0.5 rounded bg-surface-sunken border border-border-subtle font-mono mr-0.5">
              ⌘K
            </kbd>
            toggle
          </span>
        </div>
      </div>
    </div>
  );
}

/* ── Palette item ── */
interface PaletteItemProps {
  item: PaletteAction;
  active: boolean;
  onSelect: () => void;
  onHover: () => void;
}

function PaletteItem({ item, active, onSelect, onHover }: PaletteItemProps) {
  return (
    <button
      type="button"
      role="option"
      aria-selected={active}
      onClick={onSelect}
      onMouseEnter={onHover}
      className={cn(
        'w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-colors',
        active
          ? 'bg-primary-50 dark:bg-primary-900/20 text-foreground'
          : 'text-muted-foreground hover:bg-surface-sunken',
      )}
    >
      <span
        className={cn(
          'flex-shrink-0',
          active
            ? 'text-primary-600 dark:text-primary-400'
            : 'text-muted-foreground-tertiary',
        )}
      >
        {item.icon}
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium truncate">{item.label}</div>
        {item.description && (
          <div className="text-xs text-muted-foreground-tertiary truncate">
            {item.description}
          </div>
        )}
      </div>
    </button>
  );
}
