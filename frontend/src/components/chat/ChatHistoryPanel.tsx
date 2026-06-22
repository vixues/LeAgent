import { useEffect, useState, useMemo } from 'react';
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
  Folder,
  FolderPlus,
  Lock,
  MoreHorizontal,
} from 'lucide-react';
import { useChatStore } from '@/stores/chat';
import { useChatProjectStore } from '@/stores/chatProjects';
import { useLayoutStore } from '@/stores/layout';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/DropdownMenu';
import { cn, formatRelativeTime } from '@/lib/utils';
import type { ChatProject, ChatSession } from '@/types/chat';

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
  const projects = useChatProjectStore((state) => state.projects);
  const currentProjectId = useChatProjectStore((state) => state.currentProjectId);
  const fetchProjects = useChatProjectStore((state) => state.fetchProjects);
  const createProject = useChatProjectStore((state) => state.createProject);
  const updateProject = useChatProjectStore((state) => state.updateProject);
  const deleteProject = useChatProjectStore((state) => state.deleteProject);
  const unlockProject = useChatProjectStore((state) => state.unlockProject);
  const selectProject = useChatProjectStore((state) => state.selectProject);
  const isProjectUnlocked = useChatProjectStore((state) => state.isProjectUnlocked);

  const [searchQuery, setSearchQuery] = useState('');
  const [projectsExpanded, setProjectsExpanded] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState('');
  const [unlockingProjectId, setUnlockingProjectId] = useState<string | null>(null);
  const [unlockPassword, setUnlockPassword] = useState('');
  const [unlockError, setUnlockError] = useState<string | null>(null);
  const [creatingProject, setCreatingProject] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectPassword, setNewProjectPassword] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);
  const [creatingBusy, setCreatingBusy] = useState(false);
  const [renamingProjectId, setRenamingProjectId] = useState<string | null>(null);
  const [renamingProjectName, setRenamingProjectName] = useState('');

  const isNav = variant === 'nav';
  const onChatRoute =
    location.pathname === '/home' || location.pathname === '/';

  const goToChatIfNeeded = () => {
    if (isNav && !onChatRoute) {
      navigate('/home');
    }
  };

  useEffect(() => {
    void fetchProjects();
  }, [fetchProjects]);

  const lockedProjectIds = useMemo(
    () => new Set(projects.filter((p) => p.hasPassword && !isProjectUnlocked(p.id)).map((p) => p.id)),
    [projects, isProjectUnlocked],
  );

  const filteredSessions = useMemo(() => {
    const scoped = sessions.filter((session) => {
      if (currentProjectId) {
        if (lockedProjectIds.has(currentProjectId)) return false;
        return session.projectId === currentProjectId;
      }
      return !session.projectId || !lockedProjectIds.has(session.projectId);
    });
    if (!searchQuery.trim()) return scoped;
    const q = searchQuery.toLowerCase();
    return scoped.filter(
      (s) =>
        s.title.toLowerCase().includes(q) ||
        s.preview?.toLowerCase().includes(q),
    );
  }, [sessions, searchQuery, currentProjectId, lockedProjectIds]);

  const handleSelect = (id: string) => {
    selectSession(id);
    goToChatIfNeeded();
  };
  const handleNewSession = () => {
    if (currentProjectId && !isProjectUnlocked(currentProjectId)) {
      setUnlockingProjectId(currentProjectId);
      return;
    }
    void createSession(undefined, currentProjectId);
    goToChatIfNeeded();
  };

  const handleSelectProject = (projectId: string | null) => {
    if (projectId && !isProjectUnlocked(projectId)) {
      setUnlockingProjectId(projectId);
      setUnlockPassword('');
      setUnlockError(null);
      return;
    }
    selectProject(projectId);
  };

  const handleCreateProject = () => {
    setCreateError(null);
    setNewProjectName('');
    setNewProjectPassword('');
    setProjectsExpanded(true);
    setCreatingProject(true);
  };

  const submitCreateProject = async () => {
    const name = newProjectName.trim();
    if (!name || creatingBusy) return;
    setCreatingBusy(true);
    setCreateError(null);
    try {
      const id = await createProject({
        name,
        password: newProjectPassword.trim() || null,
      });
      selectProject(id);
      setCreatingProject(false);
      setNewProjectName('');
      setNewProjectPassword('');
      goToChatIfNeeded();
    } catch (error) {
      setCreateError(
        error instanceof Error ? error.message : t('chat.projects.unlockFailed'),
      );
    } finally {
      setCreatingBusy(false);
    }
  };

  const cancelCreateProject = () => {
    setCreatingProject(false);
    setNewProjectName('');
    setNewProjectPassword('');
    setCreateError(null);
  };

  const handleRenameProjectStart = (project: ChatProject) => {
    setRenamingProjectId(project.id);
    setRenamingProjectName(project.name);
  };

  const handleRenameProjectSave = async () => {
    if (!renamingProjectId) return;
    const name = renamingProjectName.trim();
    const project = projects.find((p) => p.id === renamingProjectId);
    if (!name || !project || name === project.name) {
      setRenamingProjectId(null);
      setRenamingProjectName('');
      return;
    }
    await updateProject(renamingProjectId, { name });
    setRenamingProjectId(null);
    setRenamingProjectName('');
  };

  const handleRenameProjectCancel = () => {
    setRenamingProjectId(null);
    setRenamingProjectName('');
  };

  const handleDeleteProject = async (project: ChatProject) => {
    if (!window.confirm(t('chat.projects.deleteConfirm', { name: project.name }))) return;
    await deleteProject(project.id);
  };

  const handleUnlockProject = async () => {
    if (!unlockingProjectId) return;
    setUnlockError(null);
    try {
      await unlockProject(unlockingProjectId, unlockPassword);
      selectProject(unlockingProjectId);
      setUnlockingProjectId(null);
      setUnlockPassword('');
      goToChatIfNeeded();
    } catch (error) {
      setUnlockError(error instanceof Error ? error.message : t('chat.projects.unlockFailed'));
    }
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
          <button
            type="button"
            onClick={handleCreateProject}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-primary-600 dark:hover:text-primary-400 hover:bg-surface transition-colors"
            aria-label={t('chat.projects.create')}
            title={t('chat.projects.create')}
          >
            <FolderPlus className="w-4 h-4" />
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

      {/* Projects */}
      <div className={cn('flex-shrink-0', isNav ? 'px-2 pb-2' : 'px-3 pb-2')}>
        <div className="flex items-center justify-between mb-1.5">
          <button
            type="button"
            onClick={() => {
              setProjectsExpanded((v) => !v);
              handleSelectProject(null);
            }}
            aria-expanded={projectsExpanded}
            aria-label={t('chat.projects.toggleProjects')}
            title={t('chat.projects.toggleProjects')}
            className={cn(
              'flex items-center gap-1.5 min-w-0 text-xs font-semibold uppercase tracking-wider transition-colors',
              currentProjectId
                ? 'text-muted-foreground hover:text-foreground'
                : 'text-primary-600 dark:text-primary-400',
            )}
          >
            <FoldingFanIcon open={projectsExpanded} className="w-4 h-4 flex-shrink-0" />
            <span className="truncate">{t('chat.projects.allChats')}</span>
          </button>
        </div>

        {creatingProject && (
          <div className="mb-1.5 rounded-lg border border-border-subtle bg-surface p-2">
            <input
              type="text"
              value={newProjectName}
              onChange={(e) => setNewProjectName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void submitCreateProject();
                if (e.key === 'Escape') cancelCreateProject();
              }}
              placeholder={t('chat.projects.createNamePrompt')}
              className={cn(
                'w-full rounded-md border border-border-subtle bg-surface px-2 py-1 text-xs',
                'text-foreground placeholder:text-muted-foreground-tertiary',
                'focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-400',
              )}
              autoFocus
            />
            <input
              type="password"
              value={newProjectPassword}
              onChange={(e) => setNewProjectPassword(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void submitCreateProject();
                if (e.key === 'Escape') cancelCreateProject();
              }}
              placeholder={t('chat.projects.passwordPlaceholder')}
              className={cn(
                'mt-1.5 w-full rounded-md border border-border-subtle bg-surface px-2 py-1 text-xs',
                'text-foreground placeholder:text-muted-foreground-tertiary',
                'focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-400',
              )}
            />
            {createError && <p className="mt-1 text-[11px] text-red-600">{createError}</p>}
            <div className="mt-2 flex justify-end gap-1.5">
              <button
                type="button"
                onClick={cancelCreateProject}
                className="px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground"
              >
                {t('common.cancel', { defaultValue: 'Cancel' })}
              </button>
              <button
                type="button"
                onClick={() => void submitCreateProject()}
                disabled={!newProjectName.trim() || creatingBusy}
                className="rounded-md bg-primary-600 px-2 py-1 text-[11px] font-medium text-white hover:bg-primary-700 disabled:opacity-50"
              >
                {t('chat.projects.create')}
              </button>
            </div>
          </div>
        )}

        {projectsExpanded && projects.length > 0 && (
          <div className="flex flex-col gap-0.5 max-h-32 overflow-y-auto pr-0.5">
            {projects.map((project) => (
              <ProjectRowItem
                key={project.id}
                project={project}
                active={project.id === currentProjectId}
                locked={project.hasPassword && !isProjectUnlocked(project.id)}
                isRenaming={renamingProjectId === project.id}
                renamingName={renamingProjectName}
                onSelect={handleSelectProject}
                onRenameStart={handleRenameProjectStart}
                onRenameSave={() => void handleRenameProjectSave()}
                onRenameCancel={handleRenameProjectCancel}
                onRenameNameChange={setRenamingProjectName}
                onDelete={(p) => void handleDeleteProject(p)}
              />
            ))}
          </div>
        )}

        {unlockingProjectId && (
          <div className="mt-2 rounded-lg border border-border-subtle bg-surface p-2">
            <div className="mb-1 text-xs font-medium text-foreground">
              {t('chat.projects.unlockTitle')}
            </div>
            <input
              type="password"
              value={unlockPassword}
              onChange={(e) => setUnlockPassword(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void handleUnlockProject();
                if (e.key === 'Escape') setUnlockingProjectId(null);
              }}
              placeholder={t('chat.projects.passwordPlaceholder')}
              className={cn(
                'w-full rounded-md border border-border-subtle bg-surface px-2 py-1 text-xs',
                'text-foreground placeholder:text-muted-foreground-tertiary',
                'focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-400',
              )}
              autoFocus
            />
            {unlockError && <p className="mt-1 text-[11px] text-red-600">{unlockError}</p>}
            <div className="mt-2 flex justify-end gap-1.5">
              <button
                type="button"
                onClick={() => setUnlockingProjectId(null)}
                className="px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground"
              >
                {t('common.cancel', { defaultValue: 'Cancel' })}
              </button>
              <button
                type="button"
                onClick={() => void handleUnlockProject()}
                className="rounded-md bg-primary-600 px-2 py-1 text-[11px] font-medium text-white hover:bg-primary-700"
              >
                {t('chat.projects.unlock')}
              </button>
            </div>
          </div>
        )}
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

/* ── Project row ── */
interface ProjectRowItemProps {
  project: ChatProject;
  active: boolean;
  locked: boolean;
  isRenaming: boolean;
  renamingName: string;
  onSelect: (projectId: string) => void;
  onRenameStart: (project: ChatProject) => void;
  onRenameSave: () => void;
  onRenameCancel: () => void;
  onRenameNameChange: (value: string) => void;
  onDelete: (project: ChatProject) => void;
}

function ProjectRowItem({
  project,
  active,
  locked,
  isRenaming,
  renamingName,
  onSelect,
  onRenameStart,
  onRenameSave,
  onRenameCancel,
  onRenameNameChange,
  onDelete,
}: ProjectRowItemProps) {
  const { t } = useTranslation();

  if (isRenaming) {
    return (
      <div className="flex items-center gap-1 rounded-lg border border-border-subtle bg-surface px-2 py-1">
        <input
          type="text"
          value={renamingName}
          onChange={(e) => onRenameNameChange(e.target.value)}
          className="min-w-0 flex-1 bg-transparent px-1 py-0.5 text-xs focus:outline-none"
          autoFocus
          onKeyDown={(e) => {
            if (e.key === 'Enter') onRenameSave();
            if (e.key === 'Escape') onRenameCancel();
          }}
        />
        <button
          type="button"
          onClick={onRenameSave}
          className="rounded p-1 text-mint-600 hover:bg-mint-50 dark:hover:bg-mint-900/20"
          aria-label={t('common.save', { defaultValue: 'Save' })}
        >
          <Check className="w-3 h-3" />
        </button>
        <button
          type="button"
          onClick={onRenameCancel}
          className="rounded p-1 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20"
          aria-label={t('common.cancel', { defaultValue: 'Cancel' })}
        >
          <X className="w-3 h-3" />
        </button>
      </div>
    );
  }

  return (
    <div
      className={cn(
        'group flex min-w-0 items-center rounded-lg transition-colors',
        active
          ? 'bg-primary-50 dark:bg-primary-950/30 text-primary-700 dark:text-primary-300'
          : 'text-muted-foreground hover:bg-surface hover:text-foreground',
      )}
    >
      <button
        type="button"
        onClick={() => onSelect(project.id)}
        className="flex min-w-0 flex-1 items-center gap-2 px-2 py-1.5 text-left text-xs"
        aria-current={active ? 'page' : undefined}
      >
        {locked ? (
          <Lock className="h-3.5 w-3.5 flex-shrink-0" />
        ) : (
          <Folder className="h-3.5 w-3.5 flex-shrink-0" />
        )}
        <span className="min-w-0 flex-1 truncate">{project.name}</span>
        <span className="flex-shrink-0 text-[10px] tabular-nums text-muted-foreground-tertiary">
          {project.sessionCount}
        </span>
      </button>

      <DropdownMenu>
        <DropdownMenuTrigger
          className={cn(
            'mr-0.5 flex-shrink-0 rounded-md p-1',
            'text-muted-foreground-tertiary transition-all',
            'hover:bg-surface hover:text-foreground',
            'opacity-0 group-hover:opacity-100 group-focus-within:opacity-100',
            'data-[state=open]:bg-surface data-[state=open]:text-foreground data-[state=open]:opacity-100',
            active && 'opacity-70 hover:opacity-100',
          )}
          aria-label={t('chat.projects.settings')}
          onClick={(e) => e.stopPropagation()}
        >
          <MoreHorizontal className="h-3.5 w-3.5" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" side="bottom" className="w-40">
          <DropdownMenuLabel className="max-w-[9rem] truncate font-normal normal-case tracking-normal text-foreground">
            {project.name}
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            className="gap-2 text-xs"
            onClick={() => onRenameStart(project)}
          >
            <Edit2 className="h-3.5 w-3.5" />
            {t('chat.projects.rename')}
          </DropdownMenuItem>
          <DropdownMenuItem
            className="gap-2 text-xs text-red-600 hover:text-red-600 dark:text-red-400 dark:hover:text-red-400"
            onClick={() => onDelete(project)}
          >
            <Trash2 className="h-3.5 w-3.5" />
            {t('chat.projects.delete')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

/* ── Chinese folding fan icon (折扇) ──
 * The canopy (an annular sector with ribs) is scaled on the X axis around the
 * bottom rivet. Open → a full spread fan; folded → it collapses into a long
 * trapezoid sliver with the round rivet hole sitting at the bottom. The rivet
 * lives outside the scaled group so it stays a perfect circle in both states. */
function FoldingFanIcon({
  open,
  className,
}: {
  open: boolean;
  className?: string;
}) {
  const pivot = '12px 20px';
  const ease = 'cubic-bezier(0.34, 1.56, 0.64, 1)';
  // Spread angles (deg) for the ribs when the fan is open; all collapse to 0 when folded.
  const ribAngles = [-52, -26, 0, 26, 52];

  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {/* Folded body — a clean rounded rectangle (the closed fan) */}
      <rect
        x="9.6"
        y="5"
        width="4.8"
        height="15"
        rx="2"
        style={{
          transition: 'opacity 200ms ease',
          opacity: open ? 0 : 1,
        }}
      />

      {/* Open fan — sector arc + ribs spreading from the rivet */}
      <g
        style={{
          transition: 'opacity 220ms ease',
          opacity: open ? 1 : 0,
        }}
      >
        <path
          d="M1.76 12 A 13 13 0 0 1 22.24 12"
          style={{
            transformBox: 'view-box',
            transformOrigin: pivot,
            transform: open ? 'scaleX(1)' : 'scaleX(0.06)',
            transition: `transform 360ms ${ease}`,
          }}
        />
        {ribAngles.map((angle, i) => (
          <line
            key={i}
            x1="12"
            y1="20"
            x2="12"
            y2="7"
            style={{
              transformBox: 'view-box',
              transformOrigin: pivot,
              transform: `rotate(${open ? angle : 0}deg)`,
              transition: `transform 360ms ${ease}`,
            }}
          />
        ))}
      </g>

      {/* Rivet pin at the base */}
      <circle cx="12" cy="20" r="1.3" />
    </svg>
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
