import { useState, useRef, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  PanelLeft,
  PanelLeftClose,
  SquarePen,
  PanelRight,
  MoreHorizontal,
  Trash2,
  Edit2,
  Command,
  Maximize2,
  Minimize2,
} from 'lucide-react';
import { useChatStore } from '@/stores/chat';
import { useLayoutStore } from '@/stores/layout';
import { cn } from '@/lib/utils';
import { usePetDockPreview } from '@/hooks/usePetDockPreview';
import { usePetBehaviorMode } from '@/hooks/usePetBehaviorMode';

interface ChatFabBarProps {
  onNewSession: () => void;
  onClearMessages: () => void;
  onOpenCommandPalette: () => void;
  onToggleFocus?: () => void;
  focusMode?: boolean;
  className?: string;
}

export function ChatFabBar({
  onNewSession,
  onClearMessages,
  onOpenCommandPalette,
  onToggleFocus,
  focusMode = false,
  className,
}: ChatFabBarProps) {
  const { t } = useTranslation();
  const { data: petDock } = usePetDockPreview();
  const { visual: petVisual } = usePetBehaviorMode(petDock?.settings ?? null);
  const petChipTitle = useMemo(() => {
    switch (petVisual) {
      case 'working':
        return t('petSpace.dockStatusWorking', { defaultValue: 'Working' });
      case 'happy':
        return t('petSpace.dockStatusHappy', { defaultValue: 'Happy' });
      case 'sleep':
        return t('petSpace.dockStatusSleep', { defaultValue: 'Resting' });
      case 'focus':
        return t('petSpace.dockStatusFocus', { defaultValue: 'Focused' });
      case 'excited':
        return t('petSpace.dockStatusExcited', { defaultValue: 'Upbeat' });
      case 'walk':
      case 'wave':
      case 'jump':
      case 'shake':
      case 'lookAround':
      case 'dance':
        return t(`petSpace.manualMode.${petVisual}`, { defaultValue: 'Active' });
      default:
        return t('petSpace.dockStatusIdle', { defaultValue: 'Idle' });
    }
  }, [petVisual, t]);
  const sidebarCollapsed = useLayoutStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useLayoutStore((s) => s.toggleSidebar);
  const workspaceOpen = useLayoutStore((s) => s.workspaceOpen);
  const toggleWorkspace = useLayoutStore((s) => s.toggleWorkspace);

  const currentSessionId = useChatStore((s) => s.currentSessionId);
  const sessions = useChatStore((s) => s.sessions);
  const updateSessionTitle = useChatStore((s) => s.updateSessionTitle);

  const currentSession = currentSessionId
    ? sessions.find((s) => s.id === currentSessionId) ?? null
    : null;

  const [menuOpen, setMenuOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState('');
  const menuRef = useRef<HTMLDivElement>(null);
  const renameInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [menuOpen]);

  useEffect(() => {
    if (renaming) {
      requestAnimationFrame(() => renameInputRef.current?.focus());
    }
  }, [renaming]);

  const startRename = () => {
    setRenameValue(currentSession?.title || '');
    setRenaming(true);
    setMenuOpen(false);
  };

  const commitRename = () => {
    if (currentSessionId && renameValue.trim()) {
      updateSessionTitle(currentSessionId, renameValue.trim());
    }
    setRenaming(false);
  };

  const cancelRename = () => {
    setRenaming(false);
    setRenameValue('');
  };

  return (
    <div className={cn('chat-fab-row', className)}>
      {/* Left cluster */}
      <div className="chat-fab-cluster">
        <button
          type="button"
          onClick={() => toggleSidebar()}
          className="chat-fab"
          data-active={!sidebarCollapsed ? 'true' : undefined}
          aria-label={
            sidebarCollapsed
              ? t('chat.openMainNavAria', { defaultValue: 'Open navigation sidebar' })
              : t('nav.collapseRail', { defaultValue: 'Collapse sidebar' })
          }
          title={
            sidebarCollapsed
              ? t('chat.openMainNavTitle', { defaultValue: 'Open navigation sidebar' })
              : t('nav.collapseRail', { defaultValue: 'Collapse sidebar' })
          }
        >
          {sidebarCollapsed ? (
            <PanelLeft className="w-4 h-4" />
          ) : (
            <PanelLeftClose className="w-4 h-4" />
          )}
        </button>
        <button
          type="button"
          onClick={onNewSession}
          className="chat-fab"
          aria-label={t('chat.newSession', { defaultValue: 'New session' })}
          title={t('chat.newChatTitle', { defaultValue: 'New chat' })}
        >
          <SquarePen className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={onOpenCommandPalette}
          className="chat-fab"
          aria-label={t('chat.commandPalette', {
            defaultValue: 'Command palette',
          })}
          title="⌘K"
          aria-keyshortcuts="Meta+K"
        >
          <Command className="w-4 h-4" />
        </button>
      </div>

      {/* Inline rename floater — only visible while editing */}
      {renaming && (
        <div className="flex items-center gap-1 rounded-xl border border-border-subtle bg-surface px-2 py-1 shadow-sm">
          <input
            ref={renameInputRef}
            type="text"
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitRename();
              if (e.key === 'Escape') cancelRename();
            }}
            onBlur={commitRename}
            placeholder={t('chat.renamePlaceholder', {
              defaultValue: 'Rename session',
            })}
            className="text-xs font-medium bg-transparent focus:outline-none min-w-0 max-w-[220px] text-foreground"
          />
        </div>
      )}

      {/* Right cluster */}
      <div className="chat-fab-cluster">
        <Link
          to="/pet-space"
          className={cn('chat-fab chat-fab-pet-visual flex items-center justify-center min-w-[36px] px-2')}
          aria-label={t('petSpace.chatChipAria', {
            defaultValue: 'Pet Space — open desk pet settings',
          })}
          title={t('petSpace.chatChipTitle', { mode: petChipTitle })}
        >
          <span
            className="chat-fab-pet-dot h-2 w-2 rounded-full shrink-0 motion-reduce:transition-none"
            data-visual={petVisual}
            aria-hidden
          />
        </Link>
        {onToggleFocus && (
          <button
            type="button"
            onClick={onToggleFocus}
            className="chat-fab"
            data-active={focusMode ? 'true' : undefined}
            aria-label={t('chat.focusMode', {
              defaultValue: 'Toggle focus mode',
            })}
            title={t('chat.focusModeShortcut', {
              defaultValue: 'Focus mode (⌘\\)',
            })}
            aria-keyshortcuts="Meta+Backslash"
          >
            {focusMode ? (
              <Minimize2 className="w-4 h-4" />
            ) : (
              <Maximize2 className="w-4 h-4" />
            )}
          </button>
        )}
        <button
          type="button"
          onClick={toggleWorkspace}
          className="chat-fab"
          data-active={workspaceOpen ? 'true' : undefined}
          aria-label={t('chat.workspace.toggleAria', {
            defaultValue: 'Toggle workspace',
          })}
          title={t('chat.workspace.toggleAria', {
            defaultValue: 'Toggle workspace',
          })}
        >
          <PanelRight className="w-4 h-4" />
        </button>

        <div ref={menuRef} className="relative">
          <button
            type="button"
            onClick={() => setMenuOpen(!menuOpen)}
            className="chat-fab"
            aria-label={t('common.more', { defaultValue: 'More options' })}
            aria-expanded={menuOpen}
            aria-haspopup="menu"
          >
            <MoreHorizontal className="w-4 h-4" />
          </button>

          {menuOpen && (
            <div className="absolute right-0 top-full mt-1 w-48 rounded-xl border border-border-subtle bg-surface shadow-soft p-1 chat-palette-dialog z-40">
              {currentSession && (
                <button
                  type="button"
                  onClick={startRename}
                  className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-muted-foreground hover:text-foreground hover:bg-surface-sunken transition-colors text-left"
                >
                  <Edit2 className="w-3.5 h-3.5" />
                  {t('chat.rename', { defaultValue: 'Rename' })}
                </button>
              )}
              <button
                type="button"
                onClick={() => {
                  onClearMessages();
                  setMenuOpen(false);
                }}
                className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-muted-foreground hover:text-red-600 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors text-left"
              >
                <Trash2 className="w-3.5 h-3.5" />
                {t('chat.clearMessages', { defaultValue: 'Clear messages' })}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
