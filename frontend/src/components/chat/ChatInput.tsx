import {
  useState,
  useRef,
  useCallback,
  useEffect,
  useMemo,
  type KeyboardEvent,
  type ChangeEvent,
  type FormEvent,
} from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation } from 'react-router-dom';
import {
  Send,
  Paperclip,
  StopCircle,
  MapPin,
  Puzzle,
  FolderOpen,
  FolderGit2,
  X,
  Plus,
  Slash,
  AtSign,
  Video,
} from 'lucide-react';
import { isChatStreamBusyForSession, useChatStore } from '@/stores/chat';
import { getQueuedForSession, useSteerQueueStore } from '@/stores/steerQueue';
import { useChatDraftStore, buildComposerSendParams } from '@/stores/chatDraft';
import { generateId } from '@/lib/utils';
import type { Message } from '@/types/chat';
import { useLayoutStore } from '@/stores/layout';
import { useFoldersStore } from '@/stores/foldersStore';
import { useArtifactStore } from '@/stores/artifact';
import { formatAgentPathLabel } from '@/lib/agentPathDisplay';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/Button';
import { Modal, ModalBody, ModalFooter, ModalHeader } from '@/components/ui/Modal';
import {
  useAddAuthorizedPath,
  useRemoveAuthorizedPath,
  useSessionAuthorizedPaths,
} from '@/hooks/useChat';
import { useSkillsList } from '@/hooks/useSkills';
import { buildSkillChatToken } from '@/lib/skillChatToken';
import { matchComposerTriggerToken } from '@/lib/composerTriggerToken';
import { AttachmentStrip } from './composer/AttachmentStrip';
import { ComposerReferenceStrip } from './composer/ComposerReferenceStrip';
import { ModelSelector } from './composer/ModelSelector';
import {
  SlashCommandPalette,
  type SlashPaletteSelection,
} from './composer/SlashCommandPalette';
import { MentionPicker, type MentionItem } from './composer/MentionPicker';
import { CameraCaptureModal } from './CameraCaptureModal';
import { ContextUsagePopover } from './composer/ContextUsagePopover';
import { MAX_CHAT_UPLOAD_BYTES } from '@/constants/uploads';
import { normalizeLocalFolderPathForGrant } from '@/lib/localFolderPath';
import { LocalFolderBrowser } from './LocalFolderBrowser';

const MAX_FILE_BYTES = MAX_CHAT_UPLOAD_BYTES;

interface ChatInputProps {
  onSend: (
    content: string,
    files?: File[],
    folderId?: string | null,
    fileIds?: string[],
    projectFolderId?: string | null,
    modelMode?: string,
  ) => Promise<void>;
  onStop: () => void;
  className?: string;
}

type PickerKind = '/' | '@' | null;

function getPathDisplayName(path: string, label?: string | null): string {
  const trimmedLabel = label?.trim();
  if (trimmedLabel) return trimmedLabel;
  return formatAgentPathLabel(path);
}

export function ChatInput({
  onSend,
  onStop,
  className,
}: ChatInputProps) {
  const { t } = useTranslation();
  const location = useLocation();
  const setError = useChatStore((state) => state.setError);
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const currentSessionReady = useChatStore((state) => {
    const sid = state.currentSessionId;
    if (!sid) return false;
    return state.sessions.find((session) => session.id === sid)?.isPending !== true;
  });
  const streamBusyForThisSession = useChatStore((s) =>
    isChatStreamBusyForSession(s.currentSessionId, {
      activeStreamSessionId: s.activeStreamSessionId,
      isLoading: s.isLoading,
      isStreaming: s.isStreaming,
    }),
  );

  const content = useChatDraftStore((s) => s.composerBody);
  const files = useChatDraftStore((s) => s.composerFiles);
  const setComposerBody = useChatDraftStore((s) => s.setComposerBody);
  const setComposerFiles = useChatDraftStore((s) => s.setComposerFiles);
  const [isDragging, setIsDragging] = useState(false);
  const modelId = useChatDraftStore((s) => s.composerModelId);
  const [pickerKind, setPickerKind] = useState<PickerKind>(null);
  const [pickerQuery, setPickerQuery] = useState('');
  const [cameraOpen, setCameraOpen] = useState(false);
  const [authorizedModalOpen, setAuthorizedModalOpen] = useState(false);
  const [authorizedPath, setAuthorizedPath] = useState('');
  const [authorizedLabel, setAuthorizedLabel] = useState('');
  const dragCounter = useRef(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const prevSessionIdRef = useRef<string | null>(currentSessionId);

  const insertCounter = useChatDraftStore((s) => s.insertCounter);
  const composerFileRefs = useChatDraftStore((s) => s.composerFileRefs);
  const removeFileRef = useChatDraftStore((s) => s.removeFileRef);
  const pushFileRef = useChatDraftStore((s) => s.pushFileRef);

  const folderId = useChatDraftStore((s) => s.folderId);
  const folderName = useChatDraftStore((s) => s.folderName);
  const clearFolderContext = useChatDraftStore((s) => s.clearFolderContext);

  const projectFolderId = useChatDraftStore((s) => s.projectFolderId);
  const projectFolderName = useChatDraftStore((s) => s.projectFolderName);
  const projectFolderPath = useChatDraftStore((s) => s.projectFolderPath);
  const clearProjectFolderContext = useChatDraftStore((s) => s.clearProjectFolderContext);

  const selectedFolderId = useFoldersStore((s) => s.selectedFolderId);
  const getFolder = useFoldersStore((s) => s.getFolder);

  const toggleWorkspace = useLayoutStore((s) => s.toggleWorkspace);
  const authorizedSessionId = currentSessionReady ? currentSessionId : null;
  const { data: authorizedPathsResponse } =
    useSessionAuthorizedPaths(authorizedSessionId);
  const addAuthorizedPath = useAddAuthorizedPath();
  const removeAuthorizedPath = useRemoveAuthorizedPath();
  const authorizedPaths = authorizedPathsResponse?.paths ?? [];

  // File-reference chips and draft text/files are tied to the active thread.
  useEffect(() => {
    if (prevSessionIdRef.current === currentSessionId) return;
    prevSessionIdRef.current = currentSessionId;
    useChatDraftStore.getState().clearPendingInsert();
  }, [currentSessionId]);

  const adjustHeight = useCallback(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
    }
  }, []);

  /** Draft can clear while ``onSend`` is still awaiting the stream; sync textarea height on store reset. */
  useEffect(() => {
    if (content !== '') return;
    const id = requestAnimationFrame(() => {
      adjustHeight();
    });
    return () => cancelAnimationFrame(id);
  }, [content, adjustHeight]);

  // Queued text inserts (snippets, etc.) — drain the whole queue so rapid
  // clicks do not overwrite earlier pending inserts.
  useEffect(() => {
    const store = useChatDraftStore.getState();
    const queue = store.pendingInsertQueue;
    if (queue.length === 0) return;
    const batch = queue.join('\n\n');
    const prev = store.composerBody;
    const next = !prev
      ? batch
      : prev.endsWith('\n') || prev.endsWith(' ')
        ? `${prev}${batch}`
        : `${prev}\n\n${batch}`;
    store.setComposerBody(next);
    store.clearPendingInsertQueue();
    requestAnimationFrame(() => {
      textareaRef.current?.focus();
      adjustHeight();
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [insertCounter]);

  /* ─── Caret-aware picker detection ─────────────────────────── */
  const detectPicker = useCallback((value: string, caret: number) => {
    const before = value.slice(0, caret);
    const match = matchComposerTriggerToken(before);
    if (!match) return { kind: null as PickerKind, query: '' };
    return { kind: match.kind, query: match.query };
  }, []);

  const updatePickerFromEditor = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    const { kind, query } = detectPicker(el.value, el.selectionStart);
    setPickerKind(kind);
    setPickerQuery(query);
  }, [detectPicker]);

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    setComposerBody(e.target.value);
    adjustHeight();
    requestAnimationFrame(updatePickerFromEditor);
  };

  const handleKeyUp = () => {
    // Catches arrow-key navigation that moves the caret
    updatePickerFromEditor();
  };

  const closePicker = useCallback(() => {
    setPickerKind(null);
    setPickerQuery('');
  }, []);

  const insertAtCaret = useCallback(
    (replacement: string) => {
      const el = textareaRef.current;
      if (!el) return;
      const caret = el.selectionStart;
      const value = el.value;
      const before = value.slice(0, caret);
      const after = value.slice(caret);
      const match = matchComposerTriggerToken(before);
      const start = match ? caret - match.tokenLength : caret;
      const nextValue = value.slice(0, start) + replacement + after;
      setComposerBody(nextValue);
      requestAnimationFrame(() => {
        el.focus();
        const nextCaret = start + replacement.length;
        el.setSelectionRange(nextCaret, nextCaret);
        adjustHeight();
      });
    },
    [adjustHeight],
  );

  /* ─── Picker selection handlers ────────────────────────────── */
  const handleSlashSelect = useCallback(
    (sel: SlashPaletteSelection) => {
      closePicker();
      const el = textareaRef.current;
      const stripSlashToken = () => {
        if (!el) return;
        const value = el.value;
        const caret = el.selectionStart;
        const before = value.slice(0, caret);
        const match = matchComposerTriggerToken(before);
        if (match?.kind === '/') {
          const start = caret - match.tokenLength;
          const nextValue = value.slice(0, start) + value.slice(caret);
          setComposerBody(nextValue);
          requestAnimationFrame(() => {
            el.focus();
            el.setSelectionRange(start, start);
            adjustHeight();
          });
        }
      };

      if (sel.kind === 'skill') {
        stripSlashToken();
        pushFileRef({
          kind: 'skill',
          token: buildSkillChatToken(sel.display_name, sel.name),
          label: sel.display_name,
        });
        return;
      }

      stripSlashToken();
      const cmd = sel.cmd;
      if (cmd.id === 'new') useChatStore.getState().createSession();
      else if (cmd.id === 'clear') {
        const sid = useChatStore.getState().currentSessionId;
        if (sid && window.confirm(t('chat.confirmClear'))) {
          useChatStore.getState().clearMessages(sid);
        }
      } else if (cmd.id === 'workspace') toggleWorkspace();
      else if (cmd.id === 'attach') fileInputRef.current?.click();
    },
    [adjustHeight, closePicker, pushFileRef, t, toggleWorkspace],
  );

  const handleMentionSelect = useCallback(
    (item: MentionItem) => {
      if (item.type === 'skill' && item.skillName) {
        const el = textareaRef.current;
        if (el) {
          const caret = el.selectionStart;
          const value = el.value;
          const before = value.slice(0, caret);
          const match = matchComposerTriggerToken(before);
          if (match?.kind === '@') {
            const start = caret - match.tokenLength;
            const after = value.slice(caret);
            setComposerBody(value.slice(0, start) + after);
            requestAnimationFrame(() => {
              el.focus();
              el.setSelectionRange(start, start);
              adjustHeight();
            });
          }
        }
        pushFileRef({
          kind: 'skill',
          token: buildSkillChatToken(item.skillDisplayName ?? item.label, item.skillName),
          label: item.skillDisplayName ?? item.label,
        });
        closePicker();
        return;
      }
      if (item.type === 'knowledge' && item.knowledgeToken) {
        const el = textareaRef.current;
        if (el) {
          const caret = el.selectionStart;
          const value = el.value;
          const before = value.slice(0, caret);
          const match = matchComposerTriggerToken(before);
          if (match?.kind === '@') {
            const start = caret - match.tokenLength;
            const after = value.slice(caret);
            setComposerBody(value.slice(0, start) + after);
            requestAnimationFrame(() => {
              el.focus();
              el.setSelectionRange(start, start);
              adjustHeight();
            });
          }
        }
        pushFileRef({
          kind: 'knowledge',
          token: item.knowledgeToken,
          label: item.label,
        });
        closePicker();
        return;
      }
      insertAtCaret(item.insertText);
      closePicker();
      if (item.type === 'artifact') {
        // Open the artifact in the right panel
        const artId = item.id.replace(/^artifact-/, '');
        useArtifactStore.getState().openTab(artId);
      }
    },
    [adjustHeight, closePicker, insertAtCaret, pushFileRef],
  );

  /* ─── Send ────────────────────────────────────────────────── */
  const canSend =
    Boolean(content.trim()) ||
    files.length > 0 ||
    composerFileRefs.length > 0;

  const handleSend = async () => {
    if (!canSend) return;
    if (streamBusyForThisSession) return;

    useChatStore.setState({ lastStopWasUserInitiated: false });

    const {
      content: merged,
      attachments,
      folderId: fid,
      fileIds,
      projectFolderId: pfid,
      modelMode,
    } = buildComposerSendParams();

    const selectedPageFolderId =
      location.pathname.startsWith('/folders') ? selectedFolderId : null;
    await onSend(
      merged,
      attachments,
      fid ?? selectedPageFolderId,
      fileIds,
      pfid,
      modelMode,
    );
    closePicker();
  };

  /* ─── Steer / Queue (Codex-style mid-turn interaction) ────── */
  const steer = useSteerQueueStore((s) => s.steer);
  const queueMessage = useSteerQueueStore((s) => s.queueMessage);
  const removeQueued = useSteerQueueStore((s) => s.removeQueued);
  const popNextQueued = useSteerQueueStore((s) => s.popNextQueued);
  const queuedMessages = useSteerQueueStore((s) =>
    getQueuedForSession(s, currentSessionId),
  );

  const handleSteer = useCallback(async () => {
    const text = content.trim();
    if (!text || !currentSessionId) return;
    try {
      const result = await steer(currentSessionId, text);
      const userMessage: Message = {
        id: result.message_id || generateId(),
        role: 'user',
        content: text,
        createdAt: new Date().toISOString(),
      };
      useChatStore.getState().insertSteerMessage(currentSessionId, userMessage);
      setComposerBody('');
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : t('chat.steer.failed', { defaultValue: 'Could not steer the running turn.' }),
      );
    }
  }, [content, currentSessionId, setError, steer, t]);

  const handleQueue = useCallback(async () => {
    const text = content.trim();
    if (!text || !currentSessionId) return;
    try {
      await queueMessage(currentSessionId, text);
      setComposerBody('');
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : t('chat.steer.queueFailed', { defaultValue: 'Could not queue the message.' }),
      );
    }
  }, [content, currentSessionId, queueMessage, setError, t]);

  // Auto-dispatch the next queued message when the running turn finishes.
  const prevStreamBusyRef = useRef(streamBusyForThisSession);
  useEffect(() => {
    const wasBusy = prevStreamBusyRef.current;
    prevStreamBusyRef.current = streamBusyForThisSession;
    if (!wasBusy || streamBusyForThisSession || !currentSessionId) return;
    if (queuedMessages.length === 0) return;
    void (async () => {
      const popped = await popNextQueued(currentSessionId).catch(() => null);
      if (popped?.content) {
        await onSend(popped.content);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [streamBusyForThisSession, currentSessionId]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (pickerKind && (e.key === 'Enter' || e.key === 'ArrowUp' || e.key === 'ArrowDown' || e.key === 'Escape')) {
      // Let the picker intercept via its own document listener
      return;
    }
    if (e.key === 'Enter') {
      if (streamBusyForThisSession) {
        // Codex-style composer: while a turn is running, Enter steers the
        // current turn, Shift+Enter queues for the next one.
        if (!content.trim()) return;
        e.preventDefault();
        if (e.shiftKey) void handleQueue();
        else void handleSteer();
        return;
      }
      if (!e.shiftKey) {
        e.preventDefault();
        void handleSend();
      }
    }
  };

  /* ─── File intake (select / paste / drop) ─────────────────── */
  const addFiles = useCallback(
    (incoming: File[]) => {
      const accepted: File[] = [];
      for (const f of incoming) {
        if (f.size > MAX_FILE_BYTES) {
          setError(
            t('chat.errors.fileTooLarge', {
              defaultValue: `${f.name} exceeds 10MB.`,
            }),
          );
          continue;
        }
        accepted.push(f);
      }
      if (accepted.length > 0) {
        setComposerFiles((prev) => [...prev, ...accepted]);
      }
    },
    [setError, t],
  );

  const handleFileSelect = (e: ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(e.target.files || []);
    addFiles(selected);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    const pastedFiles: File[] = [];
    for (const item of e.clipboardData.items) {
      if (item.kind === 'file') {
        const f = item.getAsFile();
        if (f) pastedFiles.push(f);
      }
    }
    if (pastedFiles.length > 0) addFiles(pastedFiles);
  };

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current += 1;
    if (e.dataTransfer?.types?.includes('Files')) setIsDragging(true);
  };
  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current -= 1;
    if (dragCounter.current <= 0) {
      dragCounter.current = 0;
      setIsDragging(false);
    }
  };
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current = 0;
    setIsDragging(false);
    const dropped = Array.from(e.dataTransfer?.files ?? []);
    if (dropped.length > 0) addFiles(dropped);
  };

  const closeAuthorizedModal = useCallback(() => {
    setAuthorizedModalOpen(false);
    setAuthorizedPath('');
    setAuthorizedLabel('');
  }, []);

  const handleFolderBrowserSelect = useCallback(
    (path: string) => {
      setAuthorizedPath(path);
      const folderName = path.split('/').filter(Boolean).pop() ?? '';
      setAuthorizedLabel((prev) => prev || folderName);
    },
    [],
  );

  const handleAuthorizedSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!authorizedSessionId) {
      setError(
        t('chat.authorizedFolders.noSession', {
          defaultValue: 'Start a chat before granting a local folder.',
        }),
      );
      return;
    }

    const path = normalizeLocalFolderPathForGrant(authorizedPath);
    if (!path) {
      setError(
        t('chat.authorizedFolders.pathRequired', {
          defaultValue: 'Enter an absolute folder path.',
        }),
      );
      return;
    }

    try {
      await addAuthorizedPath.mutateAsync({
        sessionId: authorizedSessionId,
        body: {
          path,
          label: authorizedLabel.trim() || null,
        },
      });
      closeAuthorizedModal();
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : t('chat.authorizedFolders.grantFailed', {
              defaultValue: 'Could not grant folder access.',
            }),
      );
    }
  };

  const handleRemoveAuthorizedPath = async (path: string) => {
    if (!authorizedSessionId) return;
    try {
      await removeAuthorizedPath.mutateAsync({ sessionId: authorizedSessionId, path });
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : t('chat.authorizedFolders.removeFailed', {
              defaultValue: 'Could not remove folder access.',
            }),
      );
    }
  };

  const { data: skillsListActive } = useSkillsList({ active_only: true });
  const slashSkills = useMemo(
    () =>
      (skillsListActive?.skills ?? []).map((s) => ({
        name: s.name,
        display_name: s.display_name,
        description: s.description,
      })),
    [skillsListActive?.skills],
  );
  const activeSkillCount = slashSkills.length;
  const selectedPageFolder =
    location.pathname.startsWith('/folders') && selectedFolderId
      ? getFolder(selectedFolderId)
      : undefined;
  const effectiveFolderId = folderId ?? selectedPageFolder?.id ?? null;
  const effectiveFolderName = folderName ?? selectedPageFolder?.name ?? null;

  const contextLabel = useMemo(() => {
    const path = location.pathname;
    if (path.startsWith('/workflows'))
      return t('chat.contextLabels.workflow');
    if (path.startsWith('/folders')) return t('chat.contextLabels.folder');
    if (path.startsWith('/knowledge'))
      return t('chat.contextLabels.knowledge');
    if (path.startsWith('/tools')) return t('chat.contextLabels.tools');
    if (path.startsWith('/templates'))
      return t('chat.contextLabels.templates');
    if (path.startsWith('/dashboard'))
      return t('chat.contextLabels.dashboard');
    return null;
  }, [location.pathname, t]);

  const showContextChipRow =
    Boolean(contextLabel) || activeSkillCount > 0 || Boolean(authorizedSessionId);

  return (
    <div className={cn('relative w-full', className)}>
      {/* Context + skills + authorized folder chips */}
      {showContextChipRow && (
        <div className="pb-2 flex items-center flex-wrap gap-1.5">
          {contextLabel && (
            <>
              <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-300 text-xs font-medium">
                <MapPin className="w-3 h-3" />
                <span>{contextLabel}</span>
              </div>
              <span className="text-xs text-muted-foreground-tertiary">
                {t('chat.contextReady')}
              </span>
            </>
          )}
          {activeSkillCount > 0 && (
            <Link
              to="/skills"
              className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-surface-sunken text-muted-foreground hover:text-foreground text-xs font-medium transition-colors"
              title={t('chat.skillsBadgeTitle', {
                defaultValue: 'Click to manage skills',
              })}
            >
              <Puzzle className="w-3 h-3" />
              <span>
                {t('chat.skillsBadge', {
                  count: activeSkillCount,
                  defaultValue_one: '{{count}} skill available',
                  defaultValue_other: '{{count}} skills available',
                  defaultValue: `${activeSkillCount} skills available`,
                })}
              </span>
            </Link>
          )}
          {authorizedSessionId && (
            <div className="flex items-center flex-wrap gap-1">
              {authorizedPaths.length > 0 ? (
                authorizedPaths.map((entry) => (
                  <div
                    key={entry.path}
                    className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-surface-sunken text-muted-foreground text-xs font-medium"
                    title={entry.path}
                  >
                    <FolderOpen className="w-3 h-3" />
                    <span>{getPathDisplayName(entry.path, entry.label)}</span>
                    <button
                      type="button"
                      onClick={() => void handleRemoveAuthorizedPath(entry.path)}
                      className="ml-0.5 p-0.5 rounded-full hover:bg-border-subtle hover:text-foreground transition-colors"
                      aria-label={t('chat.authorizedFolders.removeAria', {
                        name: getPathDisplayName(entry.path, entry.label),
                        defaultValue: 'Remove local folder access for {{name}}',
                      })}
                      disabled={removeAuthorizedPath.isPending}
                    >
                      <X className="w-2.5 h-2.5" />
                    </button>
                  </div>
                ))
              ) : (
                <div
                  className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-surface-sunken text-muted-foreground text-xs font-medium"
                  title={t('chat.authorizedFolders.emptyTitle', {
                    defaultValue: 'Grant a local folder for agent file tools',
                  })}
                >
                  <FolderOpen className="w-3 h-3" />
                  <span>
                    {t('chat.authorizedFolders.emptyChip', {
                      defaultValue: 'Local folders',
                    })}
                  </span>
                </div>
              )}
              <button
                type="button"
                onClick={() => setAuthorizedModalOpen(true)}
                className="flex items-center justify-center w-5 h-5 rounded-full bg-surface-sunken text-muted-foreground hover:text-foreground hover:bg-border-subtle transition-colors"
                title={t('chat.authorizedFolders.addTitle', {
                  defaultValue: 'Grant local folder access',
                })}
                aria-label={t('chat.authorizedFolders.addAria', {
                  defaultValue: 'Grant local folder access',
                })}
              >
                <Plus className="w-3 h-3" />
              </button>
            </div>
          )}
        </div>
      )}

      {/* Folder context chip */}
      {effectiveFolderId && effectiveFolderName && (
        <div className="pb-2 flex items-center gap-1.5">
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-primary-50 dark:bg-primary-900/20 border border-primary-200 dark:border-primary-800 text-primary-700 dark:text-primary-300 text-xs font-medium">
            <FolderOpen className="w-3 h-3" />
            <span>{effectiveFolderName}</span>
            {folderId && (
              <button
                type="button"
                onClick={clearFolderContext}
                className="ml-0.5 p-0.5 rounded-full hover:bg-primary-200 dark:hover:bg-primary-800 transition-colors"
                aria-label={t('chat.removeFolderContext', {
                  defaultValue: 'Remove folder context',
                })}
              >
                <X className="w-2.5 h-2.5" />
              </button>
            )}
          </div>
          <span className="text-xs text-muted-foreground-tertiary">
            {t('chat.folderContextHint', {
              defaultValue: 'Folder will be analyzed with your message',
            })}
          </span>
        </div>
      )}

      {/* Active code-project chip */}
      {projectFolderId && projectFolderName && (
        <div className="pb-2 flex items-center gap-1.5">
          <div
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 text-xs font-medium"
            title={projectFolderPath ?? undefined}
          >
            <FolderGit2 className="w-3 h-3" />
            <span>{projectFolderName}</span>
            <button
              type="button"
              onClick={clearProjectFolderContext}
              className="ml-0.5 p-0.5 rounded-full hover:bg-emerald-200 dark:hover:bg-emerald-800 transition-colors"
              aria-label={t('chat.removeProjectContext', {
                defaultValue: 'Remove project context',
              })}
            >
              <X className="w-2.5 h-2.5" />
            </button>
          </div>
          <span className="text-xs text-muted-foreground-tertiary">
            {t('chat.projectContextHint', {
              defaultValue:
                'Coding agent and project tools will run inside this folder',
            })}
          </span>
        </div>
      )}

      {/* Slash / mention pickers — anchored above the composer card */}
      <SlashCommandPalette
        open={pickerKind === '/'}
        query={pickerQuery}
        skills={slashSkills}
        onSelect={handleSlashSelect}
        onClose={closePicker}
      />
      <MentionPicker
        open={pickerKind === '@'}
        query={pickerQuery}
        skills={slashSkills}
        onSelect={handleMentionSelect}
        onClose={closePicker}
      />

      {/* Queued messages (dispatched after the current turn) */}
      {queuedMessages.length > 0 && (
        <div className="pb-2 space-y-1">
          {queuedMessages.map((qm) => (
            <div
              key={qm.id}
              className="flex items-center gap-2 rounded-lg border border-border-subtle bg-surface-sunken px-3 py-1.5 text-xs text-muted-foreground"
            >
              <span className="shrink-0 rounded bg-border-subtle px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide">
                {t('chat.steer.queuedBadge', { defaultValue: 'Queued' })}
              </span>
              <span className="min-w-0 flex-1 truncate" title={qm.content}>
                {qm.content}
              </span>
              <button
                type="button"
                onClick={() => {
                  if (currentSessionId) void removeQueued(currentSessionId, qm.id);
                }}
                className="shrink-0 p-0.5 rounded-full hover:bg-border-subtle hover:text-foreground transition-colors"
                aria-label={t('chat.steer.removeQueued', {
                  defaultValue: 'Remove queued message',
                })}
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Composer card */}
      <div
        className={cn(
          'chat-composer-card',
          isDragging && 'chat-drop-active',
        )}
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >
        <ComposerReferenceStrip
          refs={composerFileRefs}
          onRemove={removeFileRef}
        />

        <AttachmentStrip
          files={files}
          onRemove={(idx) =>
            setComposerFiles((prev) => prev.filter((_, i) => i !== idx))
          }
        />

        <textarea
          ref={textareaRef}
          id="chat-composer-message"
          name="message"
          data-composer-input
          value={content}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          onKeyUp={handleKeyUp}
          onClick={updatePickerFromEditor}
          onPaste={handlePaste}
          placeholder={t('chat.inputPlaceholder')}
          rows={1}
          className={cn(
            'w-full resize-none bg-transparent px-4 py-3',
            'text-[15px] text-foreground leading-relaxed',
            'placeholder:text-muted-foreground-tertiary',
            'focus:outline-none',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            'max-h-52 overflow-y-auto no-scrollbar',
          )}
        />

        {/* Bottom toolbar — mt-auto fills min-height so Auto/Send sit on the card bottom */}
        <div className="mt-auto flex shrink-0 items-center justify-between px-3 pb-2 pt-1">
          <div className="flex items-center gap-0.5">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="p-1.5 rounded-lg text-muted-foreground-tertiary hover:text-foreground hover:bg-surface-sunken transition-colors disabled:opacity-50"
              aria-label={t('chat.uploadFile')}
              title={t('chat.uploadFile')}
            >
              <Paperclip className="w-4 h-4" />
            </button>

            <button
              type="button"
              onClick={() => setCameraOpen(true)}
              className="p-1.5 rounded-lg text-muted-foreground-tertiary hover:text-foreground hover:bg-surface-sunken transition-colors disabled:opacity-50"
              aria-label={t('chat.camera.openComposer', {
                defaultValue: 'Take photo',
              })}
              title={t('chat.camera.openComposer', {
                defaultValue: 'Take photo',
              })}
            >
              <Video className="w-4 h-4" />
            </button>

            <button
              type="button"
              onClick={() => {
                const el = textareaRef.current;
                if (!el) return;
                insertAtCaret('/');
                setPickerKind('/');
                setPickerQuery('');
              }}
              className="p-1.5 rounded-lg text-muted-foreground-tertiary hover:text-foreground hover:bg-surface-sunken transition-colors disabled:opacity-50"
              aria-label={t('chat.slashCommand', {
                defaultValue: 'Slash commands',
              })}
              title={t('chat.slashCommand', {
                defaultValue: 'Slash commands',
              })}
            >
              <Slash className="w-4 h-4" />
            </button>

            <button
              type="button"
              onClick={() => {
                insertAtCaret('@');
                setPickerKind('@');
                setPickerQuery('');
              }}
              className="p-1.5 rounded-lg text-muted-foreground-tertiary hover:text-foreground hover:bg-surface-sunken transition-colors disabled:opacity-50"
              aria-label={t('chat.mention', {
                defaultValue: 'Mention',
              })}
              title={t('chat.mention', { defaultValue: 'Mention' })}
            >
              <AtSign className="w-4 h-4" />
            </button>

            <div className="w-px h-4 bg-border-subtle mx-1" />

            <ModelSelector />
          </div>

          <div className="flex items-center gap-1">
            <ContextUsagePopover modelId={modelId} />
            {streamBusyForThisSession ? (
              <Button
                type="button"
                size="sm"
                variant="primary"
                leftIcon={<StopCircle className="w-3.5 h-3.5" />}
                onClick={onStop}
                aria-label={t('chat.stopGeneration')}
              >
                {t('chat.stop', { defaultValue: 'Stop' })}
              </Button>
            ) : (
              <Button
                type="button"
                size="sm"
                variant="primary"
                leftIcon={<Send className="w-3.5 h-3.5" />}
                onClick={handleSend}
                disabled={streamBusyForThisSession || !canSend}
                className="disabled:opacity-40"
                aria-label={t('chat.send')}
              >
                {t('chat.send', { defaultValue: 'Send' })}
              </Button>
            )}
          </div>
        </div>
      </div>

      <input
        ref={fileInputRef}
        id="chat-composer-file"
        name="attachments"
        type="file"
        multiple
        onChange={handleFileSelect}
        className="hidden"
        accept="image/*,video/mp4,video/webm,video/quicktime,.pdf,.doc,.docx,.xls,.xlsx,.txt,.csv,.md,.json,.yaml,.yml"
      />
      <p className="mt-2 text-center text-[11px] text-muted-foreground-tertiary">
        {streamBusyForThisSession
          ? t('chat.steer.hint', {
              defaultValue: 'Enter steers the running turn · Shift+Enter queues for the next turn',
            })
          : t('chat.inputFooterHint')}
      </p>

      <CameraCaptureModal open={cameraOpen} onOpenChange={setCameraOpen} />

      <Modal
        isOpen={authorizedModalOpen}
        onClose={closeAuthorizedModal}
        size="md"
      >
        <form onSubmit={handleAuthorizedSubmit}>
          <ModalHeader onClose={closeAuthorizedModal}>
            {t('chat.authorizedFolders.modalTitle', {
              defaultValue: 'Grant local folder access',
            })}
          </ModalHeader>
          <ModalBody className="space-y-4">
            <p className="text-sm text-muted-foreground">
              {t('chat.authorizedFolders.modalDescription', {
                defaultValue:
                  'Select a folder on this machine. The agent can use file tools inside it for this chat session.',
              })}
            </p>
            <LocalFolderBrowser onSelect={handleFolderBrowserSelect} />
            <div>
              <label
                htmlFor="chat-authorized-folder-path"
                className="block text-sm font-medium text-foreground mb-1"
              >
                {t('chat.authorizedFolders.pathLabel', {
                  defaultValue: 'Folder path',
                })}
              </label>
              <input
                id="chat-authorized-folder-path"
                name="authorizedFolderPath"
                value={authorizedPath}
                onChange={(event) => setAuthorizedPath(event.target.value)}
                onBlur={() =>
                  setAuthorizedPath((prev) =>
                    normalizeLocalFolderPathForGrant(prev),
                  )
                }
                placeholder={t('chat.authorizedFolders.pathPlaceholder', {
                  defaultValue: '/home/you/Documents',
                })}
                className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground-tertiary focus:outline-none focus:ring-2 focus:ring-primary-500/50"
              />
            </div>
            <div>
              <label
                htmlFor="chat-authorized-folder-label"
                className="block text-sm font-medium text-foreground mb-1"
              >
                {t('chat.authorizedFolders.labelLabel', {
                  defaultValue: 'Label (optional)',
                })}
              </label>
              <input
                id="chat-authorized-folder-label"
                name="authorizedFolderLabel"
                value={authorizedLabel}
                onChange={(event) => setAuthorizedLabel(event.target.value)}
                placeholder={t('chat.authorizedFolders.labelPlaceholder', {
                  defaultValue: 'Receipts',
                })}
                className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground-tertiary focus:outline-none focus:ring-2 focus:ring-primary-500/50"
              />
            </div>
          </ModalBody>
          <ModalFooter>
            <Button
              type="button"
              variant="secondary"
              onClick={closeAuthorizedModal}
            >
              {t('common.cancel', { defaultValue: 'Cancel' })}
            </Button>
            <Button type="submit" loading={addAuthorizedPath.isPending}>
              {t('chat.authorizedFolders.grantAction', {
                defaultValue: 'Grant',
              })}
            </Button>
          </ModalFooter>
        </form>
      </Modal>
    </div>
  );
}
