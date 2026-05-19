import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  SquarePen,
  Trash2,
  Sparkles,
  Edit2,
  Check,
  X,
  PanelLeft,
  PanelLeftClose,
  PanelRight,
} from 'lucide-react';
import { useChatStore } from '@/stores/chat';
import { useLayoutStore } from '@/stores/layout';
import { cn } from '@/lib/utils';

interface ChatHeaderProps {
  onNewSession: () => void;
  onClearMessages: () => void;
  className?: string;
}

export function ChatHeader({
  onNewSession,
  onClearMessages,
  className,
}: ChatHeaderProps) {
  const { t } = useTranslation();
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const sessions = useChatStore((state) => state.sessions);
  const updateSessionTitle = useChatStore((state) => state.updateSessionTitle);
  const sidebarCollapsed = useLayoutStore((s) => s.sidebarCollapsed);
  const toggleSidebar = useLayoutStore((s) => s.toggleSidebar);
  const workspaceOpen = useLayoutStore((s) => s.workspaceOpen);
  const toggleWorkspace = useLayoutStore((s) => s.toggleWorkspace);

  const currentSession = currentSessionId
    ? sessions.find((s) => s.id === currentSessionId) ?? null
    : null;

  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState('');

  const startEdit = () => {
    setEditTitle(currentSession?.title || '');
    setIsEditing(true);
  };

  const saveEdit = () => {
    if (currentSessionId && editTitle.trim()) {
      updateSessionTitle(currentSessionId, editTitle.trim());
    }
    setIsEditing(false);
  };

  return (
    <div
      className={cn(
        'flex items-center gap-2 px-4 py-2.5',
        'border-b border-border-subtle',
        'bg-surface/80 backdrop-blur-sm',
        'flex-shrink-0',
        className
      )}
    >
      {/* Left: history toggle + new chat */}
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => toggleSidebar()}
          className={cn(
            'p-1.5 rounded-lg transition-colors',
            !sidebarCollapsed
              ? 'text-primary-600 dark:text-primary-400 bg-primary-50 dark:bg-primary-900/20'
              : 'text-muted-foreground hover:text-foreground hover:bg-surface-sunken'
          )}
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
          className="p-1.5 rounded-lg text-muted-foreground hover:text-primary-600 dark:hover:text-primary-400 hover:bg-primary-50 dark:hover:bg-primary-900/20 transition-colors"
          aria-label={t('chat.newSession')}
          title={t('chat.newChatTitle')}
        >
          <SquarePen className="w-4 h-4" />
        </button>
      </div>

      {/* Center: agent icon + session title */}
      <div className="flex items-center gap-2 flex-1 min-w-0 justify-center">
        <div className="w-5 h-5 rounded-md bg-gradient-to-br from-primary-600 to-cyan-500 flex items-center justify-center flex-shrink-0">
          <Sparkles className="w-3 h-3 text-white" />
        </div>

        {isEditing ? (
          <div className="flex items-center gap-1">
            <input
              type="text"
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') saveEdit();
                if (e.key === 'Escape') setIsEditing(false);
              }}
              className="text-sm font-medium bg-surface-sunken border border-primary-300 dark:border-primary-600 rounded-md px-2 py-0.5 focus:outline-none min-w-0 max-w-[200px]"
              autoFocus
            />
            <button
              type="button"
              onClick={saveEdit}
              className="p-1 rounded text-mint-600 dark:text-mint-400 hover:bg-mint-50 dark:hover:bg-mint-900/20"
            >
              <Check className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={() => setIsEditing(false)}
              className="p-1 rounded text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-1 group/title min-w-0">
            <span
              className="text-sm font-medium text-foreground truncate whitespace-nowrap min-w-0"
              title={currentSession?.title || t('chat.title')}
            >
              {currentSession?.title || t('chat.title')}
            </span>
            {currentSession && (
              <button
                type="button"
                onClick={startEdit}
                className="flex-shrink-0 p-0.5 rounded text-muted-foreground-tertiary hover:text-muted-foreground opacity-0 group-hover/title:opacity-100 transition-opacity"
                aria-label={t('chat.renameSessionAria')}
              >
                <Edit2 className="w-3 h-3" />
              </button>
            )}
          </div>
        )}
      </div>

      {/* Right: workspace toggle + clear messages */}
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={toggleWorkspace}
          className={cn(
            'p-1.5 rounded-lg transition-colors',
            workspaceOpen
              ? 'text-primary-600 dark:text-primary-400 bg-primary-50 dark:bg-primary-900/20'
              : 'text-muted-foreground hover:text-foreground hover:bg-surface-sunken'
          )}
          aria-label={t('chat.workspace.toggleAria', { defaultValue: 'Toggle workspace' })}
          title={t('chat.workspace.toggleAria', { defaultValue: 'Toggle workspace' })}
        >
          <PanelRight className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={onClearMessages}
          className="p-1.5 rounded-lg text-muted-foreground hover:text-red-500 dark:hover:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
          aria-label={t('chat.clearMessages')}
          title={t('chat.clearMessagesTitle')}
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
