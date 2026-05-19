import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { cn } from '@/lib/utils';

export interface Session {
  id: string;
  name: string;
  createdAt: Date;
  lastMessageAt: Date;
  messageCount: number;
  status: 'active' | 'completed' | 'error';
}

interface SessionViewProps {
  sessions: Session[];
  currentSessionId?: string;
  onSelectSession: (sessionId: string) => void;
  onCreateSession: () => void;
  onDeleteSession: (sessionId: string) => void;
}

export const SessionView = ({
  sessions,
  currentSessionId,
  onSelectSession,
  onCreateSession,
  onDeleteSession,
}: SessionViewProps) => {
  const { t } = useTranslation();
  const [searchQuery, setSearchQuery] = useState('');
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  const filteredSessions = sessions.filter((session) =>
    session.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const formatTime = (date: Date) => {
    const now = new Date();
    const diff = now.getTime() - new Date(date).getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (minutes < 1) return t('time.justNow');
    if (minutes < 60) return t('time.minutesAgo', { count: minutes });
    if (hours < 24) return t('time.hoursAgo', { count: hours });
    return t('time.daysAgo', { count: days });
  };

  const getStatusBadge = (status: Session['status']) => {
    const styles = {
      active: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400',
      completed: 'bg-surface-sunken text-muted-foreground',
      error: 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400',
    };

    const labels = {
      active: t('modals.io.session.active'),
      completed: t('modals.io.session.completed'),
      error: t('modals.io.session.error'),
    };

    return (
      <span className={cn('px-2 py-0.5 text-xs rounded-full', styles[status])}>
        {labels[status]}
      </span>
    );
  };

  const handleDelete = (sessionId: string) => {
    if (deleteConfirm === sessionId) {
      onDeleteSession(sessionId);
      setDeleteConfirm(null);
    } else {
      setDeleteConfirm(sessionId);
      setTimeout(() => setDeleteConfirm(null), 3000);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b border-border space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-medium text-foreground">
            {t('modals.io.sessions')}
          </h3>
          <Button size="sm" onClick={onCreateSession}>
            {t('chat.newSession')}
          </Button>
        </div>
        <Input
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder={t('chat.searchSessions')}
          leftIcon={
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
          }
        />
      </div>

      <div className="flex-1 overflow-auto">
        {filteredSessions.length === 0 ? (
          <div className="flex items-center justify-center h-full text-muted-foreground p-4">
            {searchQuery ? t('chat.noSearchResults') : t('chat.noSessions')}
          </div>
        ) : (
          <div className="divide-y divide-border">
            {filteredSessions.map((session) => (
              <div
                key={session.id}
                onClick={() => onSelectSession(session.id)}
                className={cn(
                  'p-4 cursor-pointer transition-colors',
                  'hover:bg-surface-sunken',
                  currentSessionId === session.id && 'bg-primary-50 dark:bg-primary-900/20 border-l-2 border-primary-500'
                )}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h4 className="font-medium text-foreground truncate">
                        {session.name}
                      </h4>
                      {getStatusBadge(session.status)}
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                      <span>
                        {t('chat.messageCount', { count: session.messageCount })}
                      </span>
                      <span>•</span>
                      <span>{formatTime(session.lastMessageAt)}</span>
                    </div>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDelete(session.id);
                    }}
                    className={cn(
                      'p-1.5 rounded transition-colors',
                      deleteConfirm === session.id
                        ? 'bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400'
                        : 'text-muted-foreground-tertiary hover:text-foreground hover:bg-surface-sunken'
                    )}
                    title={deleteConfirm === session.id ? t('modals.io.confirmDelete') : t('chat.deleteSession')}
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                      />
                    </svg>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="p-4 border-t border-border text-sm text-muted-foreground">
        {t('chat.sessionCount', { count: sessions.length })}
      </div>
    </div>
  );
};

export default SessionView;
