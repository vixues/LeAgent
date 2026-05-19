import { create } from 'zustand';

import { knowledgeFileIdsFromComposerRefs } from '@/lib/knowledgeChatToken';

export type ComposerFileRefKind = 'knowledge' | 'workspace' | 'skill';

export interface ComposerFileRef {
  /** Stable key for React lists / removal. */
  clientId: string;
  kind: ComposerFileRefKind;
  /** Literal token sent to the API, e.g. ``@knowledge:…#uuid``. */
  token: string;
  /** Short display name (filename). */
  label: string;
}

function newClientId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `ref-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * Ephemeral composer state for surfaces outside <ChatInput/> (workspace,
 * snippets, etc.).
 *
 * - ``pushInsert`` queues plain text (e.g. snippets); ChatInput drains the
 *   whole queue on each bump of ``insertCounter`` so rapid clicks do not drop
 *   earlier inserts.
 * - ``pushFileRef`` stacks knowledge / session file / skill references shown as chips;
 *   tokens are prepended to the outgoing message on send.
 */
interface ChatDraftStore {
  pendingInsertQueue: string[];
  insertCounter: number;
  /** Main textarea value — shared so empty-state suggestions can merge draft + attachments. */
  composerBody: string;
  /** Files staged in the composer (paperclip / paste / drop). */
  composerFiles: File[];
  composerFileRefs: ComposerFileRef[];
  folderId: string | null;
  folderName: string | null;
  /**
   * Code-project folder this chat turn is bound to. When set, the
   * chat stream sends ``project_folder_id`` and the backend folds
   * the resolved on-disk path into ``tool_extra['project_roots']``
   * so the coding agent / project_* tools can run without any
   * extra prompts from the user.
   */
  projectFolderId: string | null;
  projectFolderName: string | null;
  projectFolderPath: string | null;

  setComposerBody: (body: string) => void;
  setComposerFiles: (files: File[] | ((prev: File[]) => File[])) => void;

  pushInsert: (text: string) => void;
  pushFileRef: (ref: Omit<ComposerFileRef, 'clientId'>) => void;
  removeFileRef: (clientId: string) => void;
  clearPendingInsertQueue: () => void;
  clearComposerFileRefs: () => void;
  /** Clears queued text inserts and file-reference chips (not folder context). */
  clearPendingInsert: () => void;
  setFolderContext: (id: string, name: string) => void;
  clearFolderContext: () => void;
  setProjectFolderContext: (id: string, name: string, path?: string | null) => void;
  clearProjectFolderContext: () => void;
}

export const useChatDraftStore = create<ChatDraftStore>((set) => ({
  pendingInsertQueue: [],
  insertCounter: 0,
  composerBody: '',
  composerFiles: [],
  composerFileRefs: [],
  folderId: null,
  folderName: null,
  projectFolderId: null,
  projectFolderName: null,
  projectFolderPath: null,

  setComposerBody: (composerBody) => set({ composerBody }),

  setComposerFiles: (updater) =>
    set((state) => ({
      composerFiles:
        typeof updater === 'function'
          ? (updater as (prev: File[]) => File[])(state.composerFiles)
          : updater,
    })),

  pushInsert: (text) =>
    set((state) => ({
      pendingInsertQueue: [...state.pendingInsertQueue, text],
      insertCounter: state.insertCounter + 1,
    })),

  pushFileRef: (ref) =>
    set((state) => ({
      composerFileRefs: [
        ...state.composerFileRefs,
        { ...ref, clientId: newClientId() },
      ],
    })),

  removeFileRef: (clientId) =>
    set((state) => ({
      composerFileRefs: state.composerFileRefs.filter((r) => r.clientId !== clientId),
    })),

  clearPendingInsertQueue: () => set({ pendingInsertQueue: [] }),

  clearComposerFileRefs: () => set({ composerFileRefs: [] }),

  clearPendingInsert: () =>
    set({
      pendingInsertQueue: [],
      composerFileRefs: [],
      composerBody: '',
      composerFiles: [],
    }),

  setFolderContext: (id, name) => set({ folderId: id, folderName: name }),
  clearFolderContext: () => set({ folderId: null, folderName: null }),
  setProjectFolderContext: (id, name, path = null) =>
    set({ projectFolderId: id, projectFolderName: name, projectFolderPath: path }),
  clearProjectFolderContext: () =>
    set({ projectFolderId: null, projectFolderName: null, projectFolderPath: null }),
}));

/** Same merge as ChatInput send: ref tokens + body, optionally with a trailing suggestion block. */
export function buildComposerSendParams(suggestionAppend?: string) {
  const s = useChatDraftStore.getState();
  const refTokens = s.composerFileRefs.map((r) => r.token).join(' ');
  const trimmed = s.composerBody.trim();
  let merged = [refTokens, trimmed].filter(Boolean).join(' ');
  const extra = suggestionAppend?.trim();
  if (extra) {
    merged = merged ? `${merged}\n\n${extra}` : extra;
  }
  const fileIds = knowledgeFileIdsFromComposerRefs(s.composerFileRefs);
  return {
    content: merged,
    attachments: s.composerFiles.length > 0 ? [...s.composerFiles] : undefined,
    folderId: s.folderId,
    fileIds: fileIds.length > 0 ? fileIds : undefined,
    projectFolderId: s.projectFolderId,
  };
}

/** After a successful send (normal or suggestion). */
export function resetComposerAfterSend() {
  useChatDraftStore.setState({
    composerBody: '',
    composerFiles: [],
    composerFileRefs: [],
    folderId: null,
    folderName: null,
    pendingInsertQueue: [],
    // ``projectFolderId`` is intentionally preserved across sends —
    // a code-project binding belongs to the conversation, not the
    // single message, so the next turn keeps the same project root
    // until the user explicitly clears it.
  });
}
