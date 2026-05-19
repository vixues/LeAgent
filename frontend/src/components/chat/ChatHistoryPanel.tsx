import { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Plus,
  Search,
  Trash2,
  Edit2,
  Check,
  X,
  Clock,
  ChevronsLeft,
} from 'lucide-react';
import { useChatStore } from '@/stores/chat';
import { useLayoutStore } from '@/stores/layout';
import { cn, formatRelativeTime } from '@/lib/utils';
import type { ChatSession } from '@/types/chat';

interface ChatHistoryPanelProps {
  /** `rail`: chat-area resizable rail (56px vs expanded). `nav`: embedded under NavRail — always list UI. */
  variant?: 'rail' | 'nav';
  collapsed?: boolean;
}

export function ChatHistoryPanel({
  variant = 'rail',
  collapsed = false,
}: ChatHistoryPanelProps) {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const toggleChatHistory = useLayoutStore((s) => s.toggleChatHistory);

  const sessions = useChatStore((state) => state.sessions);
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const selectSession = useChatStore((state) => state.selectSession);
  const deleteSession = useChatStore((state) => state.deleteSession);
  const createSession = useChatStore((state) => state.createSession);
  const updateSessionTitle = useChatStore((state) => state.updateSessionTitle);

  const [searchQuery, setSearchQuery] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState('');

  const isNav = variant === 'nav';
  const onChatRoute =
    location.pathname === '/home' || location.pathname === '/';

  const goToChatIfNeeded = () => {
    if (isNav && !onChatRoute) {
      navigate('/home');
    }
  };

  const filteredSessions = useMemo(() => {
    if (!searchQuery.trim()) return sessions;
    const q = searchQuery.toLowerCase();
    return sessions.filter(
      (s) =>
        s.title.toLowerCase().includes(q) ||
        s.preview?.toLowerCase().includes(q),
    );
  }, [sessions, searchQuery]);

  const handleSelect = (id: string) => {
    selectSession(id);
    goToChatIfNeeded();
  };
  const handleNewSession = () => {
    void createSession();
    goToChatIfNeeded();
  };

  const handleStartEdit = (session: ChatSession, e: React.MouseEvent) => {
    e.stopPropagation();
    setEditingId(session.id);
    setEditingTitle(session.title);
  };

  const handleSaveEdit = () => {
    if (editingId && editingTitle.trim()) {
      updateSessionTitle(editingId, editingTitle.trim());
    }
    setEditingId(null);
    setEditingTitle('');
  };

  const handleDelete = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    deleteSession(id);
  };

  // Collapsed 56px icon rail (chat layout only)
  if (variant === 'rail' && collapsed) {
    return (
      <div
        className={cn(
          'flex flex-col h-full min-h-0',
          'bg-surface-sunken/60',
          'transition-[width] duration-[var(--chat-duration-slow)] ease-[var(--chat-ease)]',
        )}
      >
        <div className="flex flex-col items-center gap-1.5 pt-2.5 pb-2 flex-shrink-0">
          <button
            type="button"
            onClick={handleNewSession}
            className="chat-fab !w-8 !h-8"
            aria-label={t('chat.newChatAria', { defaultValue: 'New chat' })}
            title={t('chat.newChatTitle', { defaultValue: 'New chat' })}
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="chat-sessions-scroll flex-1 min-h-0 py-1 flex flex-col items-center gap-0.5">
          {sessions.slice(0, 24).map((session) => {
            const isActive = session.id === currentSessionId;
            const initial = session.title.charAt(0).toUpperCase();
            return (
              <button
                key={session.id}
                type="button"
                onClick={() => handleSelect(session.id)}
                className={cn(
                  'w-8 h-8 rounded-lg flex items-center justify-center text-xs font-medium transition-colors',
                  isActive
                    ? 'bg-surface text-foreground shadow-sm'
                    : 'text-muted-foreground-tertiary hover:bg-surface/60 hover:text-muted-foreground',
                )}
                title={session.title}
                aria-label={session.title}
                aria-current={isActive ? 'page' : undefined}
              >
                {initial}
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        'flex flex-col min-h-0',
        isNav ? 'max-h-full h-full' : 'h-full',
        isNav ? 'bg-transparent' : 'bg-surface-sunken/60',
        !isNav &&
          'transition-[width] duration-[var(--chat-duration-slow)] ease-[var(--chat-ease)]',
      )}
    >
      {/* Header */}
      <div
        className={cn(
          'flex items-center justify-between flex-shrink-0',
          isNav ? 'px-2 py-2' : 'px-3 py-3',
        )}
      >
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          {t('chat.history')}
        </h3>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={handleNewSession}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-primary-600 dark:hover:text-primary-400 hover:bg-surface transition-colors"
            aria-label={t('chat.newChatAria')}
            title={t('chat.newChatTitle')}
          >
            <Plus className="w-4 h-4" />
          </button>
          {!isNav && (
            <button
              type="button"
              onClick={toggleChatHistory}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-surface transition-colors"
              aria-label={t('nav.collapseRail', {
                defaultValue: 'Collapse sidebar',
              })}
              title={t('nav.collapseRail', { defaultValue: 'Collapse sidebar' })}
            >
              <ChevronsLeft className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Search */}
      <div className={cn('flex-shrink-0', isNav ? 'px-2 pb-1.5' : 'px-3 pb-2')}>
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground-tertiary" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t('chat.searchSessions')}
            className={cn(
              'w-full pl-8 pr-3 py-1.5 text-xs rounded-lg',
              'bg-surface',
              'border border-border-subtle',
              'text-foreground placeholder:text-muted-foreground-tertiary',
              'focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-400',
            )}
          />
        </div>
      </div>

      {/* Session list */}
      <div
        className={cn(
          'chat-sessions-scroll flex-1 min-h-0 overflow-y-auto',
          isNav ? 'px-1.5 pb-1.5' : 'px-2 pb-2',
        )}
      >
        {filteredSessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-center px-4">
            <Clock className="w-5 h-5 text-muted-foreground-tertiary mb-2" />
            <p className="text-xs text-muted-foreground-tertiary">
              {searchQuery
                ? t('chat.noMatchingSessions')
                : t('chat.noSessionRecords')}
            </p>
          </div>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {filteredSessions.map((session) => (
              <SessionItem
                key={session.id}
                session={session}
                isActive={session.id === currentSessionId}
                isEditing={editingId === session.id}
                editingTitle={editingTitle}
                onSelect={handleSelect}
                onStartEdit={handleStartEdit}
                onSaveEdit={handleSaveEdit}
                onCancelEdit={() => {
                  setEditingId(null);
                  setEditingTitle('');
                }}
                onEditTitleChange={setEditingTitle}
                onDelete={handleDelete}
              />
            ))}
          </ul>
        )}
      </div>

      {/* Footer */}
      <div className={cn('flex-shrink-0', isNav ? 'px-2 py-1.5' : 'px-3 py-2')}>
        <p className="text-[11px] text-muted-foreground-tertiary text-center tabular-nums">
          {t('chat.sessionCountInline', { count: sessions.length })}
        </p>
      </div>
    </div>
  );
}

/* ── Session item ── */
interface SessionItemProps {
  session: ChatSession;
  isActive: boolean;
  isEditing: boolean;
  editingTitle: string;
  onSelect: (id: string) => void;
  onStartEdit: (session: ChatSession, e: React.MouseEvent) => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onEditTitleChange: (value: string) => void;
  onDelete: (id: string, e: React.MouseEvent) => void;
}

function SessionItem({
  session,
  isActive,
  isEditing,
  editingTitle,
  onSelect,
  onStartEdit,
  onSaveEdit,
  onCancelEdit,
  onEditTitleChange,
  onDelete,
}: SessionItemProps) {
  const { t } = useTranslation();

  if (isEditing) {
    return (
      <li>
        <div className="flex items-center gap-1 px-2 py-1.5 rounded-lg bg-surface border border-border-subtle">
          <input
            type="text"
            value={editingTitle}
            onChange={(e) => onEditTitleChange(e.target.value)}
            className="flex-1 bg-transparent border-0 px-1 py-0.5 text-xs focus:outline-none"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === 'Enter') onSaveEdit();
              if (e.key === 'Escape') onCancelEdit();
            }}
          />
          <button
            type="button"
            onClick={onSaveEdit}
            className="p-1 rounded hover:bg-mint-50 dark:hover:bg-mint-900/20 text-mint-600 dark:text-mint-400"
            aria-label={t('common.save', { defaultValue: 'Save' })}
          >
            <Check className="w-3 h-3" />
          </button>
          <button
            type="button"
            onClick={onCancelEdit}
            className="p-1 rounded hover:bg-red-50 dark:hover:bg-red-900/20 text-red-500"
            aria-label={t('common.cancel', { defaultValue: 'Cancel' })}
          >
            <X className="w-3 h-3" />
          </button>
        </div>
      </li>
    );
  }

  return (
    <li className="group relative">
      <button
        type="button"
        className={cn(
          'chat-session-row',
          isActive && 'text-primary-700 dark:text-primary-300',
        )}
        data-active={isActive ? 'true' : 'false'}
        aria-current={isActive ? 'page' : undefined}
        onClick={() => onSelect(session.id)}
        title={session.title}
      >
        <span className="chat-session-row-title">{session.title}</span>
        <span className="chat-session-row-time">
          {formatRelativeTime(session.updatedAt)}
        </span>
      </button>

      <div
        className={cn(
          'absolute right-1 top-1/2 -translate-y-1/2 flex gap-0.5',
          'opacity-0 group-hover:opacity-100 group-focus-within:opacity-100',
          'transition-opacity',
          // opacity-0 still receives hits; let clicks reach the row button until actions show
          'pointer-events-none group-hover:pointer-events-auto group-focus-within:pointer-events-auto',
        )}
      >
        <button
          type="button"
          onClick={(e) => onStartEdit(session, e)}
          className="p-1 rounded-md bg-surface/90 backdrop-blur hover:bg-surface text-muted-foreground hover:text-foreground transition-colors"
          aria-label={t('chat.renameAria')}
        >
          <Edit2 className="w-3 h-3" />
        </button>
        <button
          type="button"
          onClick={(e) => onDelete(session.id, e)}
          className="p-1 rounded-md bg-surface/90 backdrop-blur hover:bg-red-50 dark:hover:bg-red-900/20 text-muted-foreground hover:text-red-500 dark:hover:text-red-400 transition-colors"
          aria-label={t('chat.deleteAria')}
        >
          <Trash2 className="w-3 h-3" />
        </button>
      </div>
    </li>
  );
}
