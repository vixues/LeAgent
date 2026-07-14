import { useCallback, useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  BookPlus,
  Code2,
  Download,
  FileArchive,
  FolderOpen,
  GitBranch,
  Search,
  Send,
  FileText,
} from 'lucide-react';
import { apiClient } from '@/api/client';
import { downloadAuthenticatedFile } from '@/lib/downloadAuthenticatedFile';
import { useDocuments, usePromoteToKnowledge } from '@/hooks/useKnowledge';
import { getOrCreateKnowledgeSessionId } from '@/lib/knowledgeSession';
import { useChatDraftStore } from '@/stores/chatDraft';
import { useChatStore } from '@/stores/chat';
import { useChatProjectStore } from '@/stores/chatProjects';
import { useArtifactStore } from '@/stores/artifact';
import { useRealtimeFileSync } from '@/hooks/useRealtimeFileSync';
import { cn, isUuid } from '@/lib/utils';
import { getFileExtensionIcon } from './artifactIcon';
import type { ArtifactType } from '@/types/artifact';
import { UniversalFilePreview } from '@/components/files/UniversalFilePreview';
import type { Attachment, Message } from '@/types/chat';
import { normalizeAttachmentList } from '@/types/chat';
import { collectSessionEditPaths } from '@/lib/sessionProjectEdits';
import { DocGenerationLivePreview } from './DocGenerationLivePreview';
import { canvasIframeSandbox, withCanvasPreviewJs } from '@/lib/canvasPreviewJs';
import type { FolderFileItem } from '@/hooks/useFolders';

const EMPTY_SESSION_MESSAGES: Message[] = [];

type KnowledgeItem = {
  id: string;
  original_name: string;
  mime_type?: string;
  size: number;
};

type SessionWorkspaceItem = {
  file_id: string;
  file_name: string;
  size: number;
  mime_type?: string;
  source: 'upload' | 'artifact' | 'canvas';
  is_ai: boolean;
  artifact_id?: string;
  /** Hosted canvas preview path (same-origin); only for ``source === 'canvas'``. */
  previewPath?: string;
  /** Hide from ZIP bundle (no storage file UUID). */
  excludeFromZip?: boolean;
  /** Workspace path alias this AI artifact was promoted from. */
  source_tool_path?: string;
  /** Monotonic version for the same source_tool_path (1-based). */
  version?: number;
  /** False when a newer content version superseded this row. */
  is_latest?: boolean;
};

type SelectedItem =
  | { source: 'workspace'; item: SessionWorkspaceItem }
  | { source: 'knowledge'; item: KnowledgeItem };

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function workspaceFileFingerprint(
  name: string,
  size: number,
  sha256?: string,
): string {
  const normalized = name.trim().toLowerCase();
  if (sha256) return `sha256:${sha256}`;
  return `name:${normalized}:${size}`;
}

function attachmentFingerprint(
  att: Attachment,
  raw?: Record<string, unknown>,
): string {
  const sha =
    raw && typeof raw.sha256 === 'string' && raw.sha256
      ? raw.sha256
      : undefined;
  return workspaceFileFingerprint(att.name, att.size ?? 0, sha);
}

function isAiOperated(item: unknown): boolean {
  if (!item || typeof item !== 'object') return false;
  const rec = item as Record<string, unknown>;
  return rec.created_by === 'ai' || rec.source === 'ai' || rec.owner_type === 'ai';
}

/* Map extensions → artifact type when a user double-clicks */
/** Workspace list rows only use UUID ``file_id`` for real stored blobs (excludes canvas pseudo-keys). */
const STORED_FILE_ID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function isStoredWorkspaceFileId(id: string): boolean {
  return STORED_FILE_ID_RE.test(id);
}

function typeFromExt(ext: string): ArtifactType {
  if (['md', 'mdx'].includes(ext)) return 'markdown';
  if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'avif'].includes(ext))
    return 'image';
  if (['html', 'htm'].includes(ext)) return 'html';
  if (['csv', 'tsv', 'xlsx', 'xls'].includes(ext)) return 'table';
  return 'code';
}

export function FilesTab() {
  const { t } = useTranslation();
  const currentSessionId = useChatStore((s) => s.currentSessionId);
  const chatSessionsReconciled = useChatStore((s) => s.chatSessionsReconciled);
  const currentSessionIsPending = useChatStore((s) => {
    const sid = s.currentSessionId;
    if (!sid) return false;
    return s.sessions.find((x) => x.id === sid)?.isPending === true;
  });
  const sessionProjectId = useChatStore((s) => {
    const sid = s.currentSessionId;
    if (!sid) return null;
    return s.sessions.find((x) => x.id === sid)?.projectId ?? null;
  });
  // Shared project files only when this session belongs to a chat project —
  // never fall back to sidebar currentProjectId (free chats stay session-local).
  const projectFolderId = useChatProjectStore((s) => {
    if (!sessionProjectId) return null;
    return s.projects.find((p) => p.id === sessionProjectId)?.folderId ?? null;
  });
  const messagesBySession = useChatStore((s) => s.messages);
  const sessionMessages = useMemo(
    () => (currentSessionId ? (messagesBySession[currentSessionId] ?? EMPTY_SESSION_MESSAGES) : EMPTY_SESSION_MESSAGES),
    [currentSessionId, messagesBySession],
  );
  const artifacts = useArtifactStore((s) => s.artifacts);
  const [query, setQuery] = useState('');
  const [selectedFile, setSelectedFile] = useState<SelectedItem | null>(null);
  const [zipIds, setZipIds] = useState<Set<string>>(() => new Set());
  const [zipBusy, setZipBusy] = useState(false);
  const [zipError, setZipError] = useState<string | null>(null);
  const [promoteError, setPromoteError] = useState<string | null>(null);
  const promoteMutation = usePromoteToKnowledge();
  useEffect(() => {
    // Reset session-scoped workspace navigation when chat session changes/deletes.
    setQuery('');
    setSelectedFile(null);
    setZipIds(new Set());
    setZipError(null);
    setPromoteError(null);
  }, [currentSessionId]);

  const toggleZipId = useCallback((id: string) => {
    setZipIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const downloadZipBundle = useCallback(async () => {
    if (zipIds.size === 0) return;
    setZipBusy(true);
    setZipError(null);
    const file_ids = Array.from(zipIds);
    const filename =
      currentSessionId && currentSessionId.length >= 8
        ? `workspace-${currentSessionId.slice(0, 8)}.zip`
        : 'workspace-files.zip';
    try {
      const blob = await apiClient.postBlob('/files/bundle/download', {
        file_ids,
        filename,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.rel = 'noopener';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setZipError(
        e instanceof Error ? e.message : t('chat.workspace.files.downloadZipError'),
      );
    } finally {
      setZipBusy(false);
    }
  }, [currentSessionId, t, zipIds]);

  useRealtimeFileSync(true);

  const sessionScopeKey = currentSessionId ?? 'no-session';

  const { data: knowledgeDocs, isLoading: knowledgeLoading } = useDocuments({
    page_size: 25,
    enabled: true,
    scopeKey: sessionScopeKey,
  });

  const knowledgeItems: KnowledgeItem[] = useMemo(
    () =>
      (knowledgeDocs?.items ?? []).map((doc) => ({
        id: String(doc.id),
        original_name: doc.original_name,
        mime_type: doc.mime_type ?? undefined,
        size: doc.size,
      })),
    [knowledgeDocs?.items],
  );

  const { data: sessionAttData } = useQuery({
    queryKey: ['chat', 'session-attachments', currentSessionId],
    queryFn: () =>
      apiClient.get<{ session_id: string; attachments: Record<string, unknown>[] }>(
        `/chat/sessions/${currentSessionId}/attachments`,
      ),
    enabled:
      isUuid(currentSessionId) &&
      chatSessionsReconciled &&
      !currentSessionIsPending,
    staleTime: 15_000,
  });

  const { data: projectFolderItems } = useQuery({
    queryKey: ['folders', 'items', projectFolderId, 'chat-project'],
    queryFn: () =>
      apiClient.get<FolderFileItem[]>('/folder-items', {
        folder_id: projectFolderId!,
      } as Record<string, string | number | boolean | undefined>),
    enabled: isUuid(projectFolderId),
    staleTime: 15_000,
  });

  const sharedProjectItems = useMemo(() => {
    const rows = projectFolderItems ?? [];
    const q = query.trim().toLowerCase();
    const mapped: SessionWorkspaceItem[] = rows.map((row) => ({
      file_id: row.file_id,
      file_name: row.file_name,
      size: row.size,
      mime_type: row.mime_type ?? undefined,
      source: 'upload' as const,
      is_ai: false,
    }));
    if (!q) return mapped;
    return mapped.filter((d) => d.file_name.toLowerCase().includes(q));
  }, [projectFolderItems, query]);

  const sessionAttachmentList = useMemo(
    () => normalizeAttachmentList(sessionAttData?.attachments ?? []),
    [sessionAttData],
  );

  const filteredKnowledge = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return knowledgeItems;
    return knowledgeItems.filter((d) => d.original_name.toLowerCase().includes(q));
  }, [knowledgeItems, query]);

  const workspaceItems = useMemo(() => {
    const out: SessionWorkspaceItem[] = [];
    const seenIds = new Set<string>();
    const seenFingerprints = new Set<string>();
    const latestBySourcePath = new Map<string, string>();
    const messageIdSet = new Set(sessionMessages.map((m) => m.id));

    const remember = (item: SessionWorkspaceItem, fingerprint: string) => {
      if (seenIds.has(item.file_id)) return false;
      // Superseded path versions: keep only the latest row in the default list.
      if (item.source_tool_path) {
        const priorId = latestBySourcePath.get(item.source_tool_path);
        if (priorId && priorId !== item.file_id && item.is_latest === false) {
          return false;
        }
        if (item.is_latest !== false) {
          latestBySourcePath.set(item.source_tool_path, item.file_id);
          // Drop an earlier draft for the same path if we already pushed it.
          const priorIdx = out.findIndex(
            (x) =>
              x.source_tool_path === item.source_tool_path &&
              x.file_id !== item.file_id,
          );
          if (priorIdx >= 0) {
            const removed = out.splice(priorIdx, 1)[0];
            if (removed) {
              seenIds.delete(removed.file_id);
            }
          }
        }
      }
      if (seenFingerprints.has(fingerprint) && item.is_latest === false) return false;
      seenIds.add(item.file_id);
      seenFingerprints.add(fingerprint);
      out.push(item);
      return true;
    };

    // Prefer API attachments first so version/extra metadata is available.
    const attRowsSorted = [...(sessionAttData?.attachments ?? [])].sort((a, b) => {
      const va = typeof a?.extra === 'object' && a.extra && typeof (a.extra as { version?: number }).version === 'number'
        ? (a.extra as { version: number }).version
        : 0;
      const vb = typeof b?.extra === 'object' && b.extra && typeof (b.extra as { version?: number }).version === 'number'
        ? (b.extra as { version: number }).version
        : 0;
      return vb - va;
    });

    for (const raw of attRowsSorted) {
      if (!raw || typeof raw !== 'object') continue;
      const id = typeof raw.id === 'string' ? raw.id : '';
      const name = typeof raw.filename === 'string'
        ? raw.filename
        : typeof raw.name === 'string'
          ? raw.name
          : '';
      if (!id || !name) continue;
      const extra =
        typeof raw.extra === 'object' && raw.extra !== null
          ? (raw.extra as Record<string, unknown>)
          : undefined;
      const fromTool = typeof extra?.source_tool_path === 'string';
      const version = typeof extra?.version === 'number' ? extra.version : undefined;
      const isLatest = extra?.is_latest === false ? false : true;
      const att = sessionAttachmentList.find((a) => a.id === id);
      remember(
        {
          file_id: id,
          file_name: name,
          size: typeof raw.size === 'number' ? raw.size : att?.size ?? 0,
          mime_type: typeof raw.content_type === 'string' ? raw.content_type : att?.type,
          source: 'upload',
          is_ai: fromTool,
          source_tool_path: fromTool ? String(extra?.source_tool_path) : undefined,
          version,
          is_latest: isLatest,
        },
        workspaceFileFingerprint(
          name,
          typeof raw.size === 'number' ? raw.size : 0,
          typeof raw.sha256 === 'string' ? raw.sha256 : undefined,
        ),
      );
    }

    for (const msg of sessionMessages) {
      for (const att of (msg.attachments ?? []) as Attachment[]) {
        if (!att.id || !att.name) continue;
        if (seenIds.has(att.id)) continue;
        const fingerprint = attachmentFingerprint(att);
        if (seenFingerprints.has(fingerprint)) continue;
        remember(
          {
            file_id: att.id,
            file_name: att.name,
            size: att.size ?? 0,
            mime_type: att.type,
            source: 'upload',
            is_ai: msg.role === 'assistant',
            is_latest: true,
          },
          fingerprint,
        );
      }
    }

    for (const artifact of Object.values(artifacts)) {
      const fileId = artifact.metadata?.fileId;
      if (typeof fileId === 'string' && fileId.length > 0) {
        const inSession =
          artifact.sessionId === currentSessionId ||
          (artifact.messageId ? messageIdSet.has(artifact.messageId) : false);
        if (!inSession) continue;
        const fingerprint = workspaceFileFingerprint(
          artifact.title,
          typeof artifact.metadata?.size === 'number' ? artifact.metadata.size : 0,
        );
        if (seenIds.has(fileId) || seenFingerprints.has(fingerprint)) continue;
        seenIds.add(fileId);
        seenFingerprints.add(fingerprint);
        out.push({
          file_id: fileId,
          file_name: artifact.title,
          size:
            typeof artifact.metadata?.size === 'number'
              ? artifact.metadata.size
              : 0,
          mime_type:
            typeof artifact.metadata?.mimeType === 'string'
              ? artifact.metadata.mimeType
              : undefined,
          source: 'artifact',
          is_ai: true,
          artifact_id: artifact.id,
        });
        continue;
      }

      const previewRaw = artifact.metadata?.previewPath ?? artifact.metadata?.preview_path;
      const previewPath = typeof previewRaw === 'string' ? previewRaw : '';
      if (!previewPath || artifact.type !== 'html') continue;
      const inSession =
        artifact.sessionId === currentSessionId ||
        (artifact.messageId ? messageIdSet.has(artifact.messageId) : false);
      if (!inSession) continue;
      const key = `canvas:${artifact.id}`;
      if (seenIds.has(key)) continue;
      seenIds.add(key);
      out.push({
        file_id: key,
        file_name: artifact.title || 'Canvas',
        size: 0,
        mime_type:
          typeof artifact.metadata?.contentType === 'string'
            ? artifact.metadata.contentType
            : 'text/html',
        source: 'canvas',
        is_ai: true,
        artifact_id: artifact.id,
        previewPath,
        excludeFromZip: true,
      });
    }

    return out;
  }, [
    artifacts,
    currentSessionId,
    sessionAttachmentList,
    sessionAttData,
    sessionMessages,
  ]);

  const filteredWorkspace = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return workspaceItems;
    return workspaceItems.filter((f) => f.file_name.toLowerCase().includes(q));
  }, [workspaceItems, query]);

  const workspacePromotableIds = useMemo(() => {
    const acc = new Set<string>();
    for (const row of workspaceItems) {
      if (!isStoredWorkspaceFileId(row.file_id)) continue;
      if (row.excludeFromZip) continue;
      acc.add(row.file_id);
    }
    return acc;
  }, [workspaceItems]);

  const promoteTargets = useMemo(
    () => Array.from(zipIds).filter((id) => workspacePromotableIds.has(id)),
    [zipIds, workspacePromotableIds],
  );

  const promoteToKnowledge = useCallback(async () => {
    if (promoteTargets.length === 0) return;
    setPromoteError(null);
    try {
      const session_id = await getOrCreateKnowledgeSessionId();
      await promoteMutation.mutateAsync({
        file_ids: promoteTargets,
        session_id,
      });
    } catch (e) {
      setPromoteError(
        e instanceof Error ? e.message : t('chat.workspace.files.addToKnowledgeError'),
      );
    }
  }, [promoteMutation, promoteTargets, t]);

  const sessionEditPaths = useMemo(
    () => collectSessionEditPaths(sessionMessages),
    [sessionMessages],
  );

  /** Do not gate the whole panel on `/documents` loading — session files must stay visible. */
  const showGlobalEmpty = useMemo(() => {
    const workspaceListEmpty =
      filteredWorkspace.length === 0 &&
      sessionEditPaths.length === 0 &&
      sharedProjectItems.length === 0;
    if (!workspaceListEmpty) return false;
    if (filteredKnowledge.length > 0) return false;
    const q = query.trim();
    if (q.length > 0) return true;
    return !knowledgeLoading;
  }, [
    filteredWorkspace.length,
    sessionEditPaths.length,
    sharedProjectItems.length,
    filteredKnowledge.length,
    query,
    knowledgeLoading,
  ]);

  const pushFileRef = useChatDraftStore((s) => s.pushFileRef);

  const openAsArtifact = (item: SessionWorkspaceItem) => {
    if (item.artifact_id) {
      useArtifactStore.getState().openTab(item.artifact_id);
      return;
    }
    const ext = item.file_name.split('.').pop()?.toLowerCase() ?? '';
    const artifactId = `file-${item.file_id}`;
    const existing = useArtifactStore.getState().artifacts[artifactId];
    if (!existing) {
      useArtifactStore.getState().addArtifact({
        id: artifactId,
        type: typeFromExt(ext),
        title: item.file_name,
        content: '',
        language: ext,
        createdAt: new Date().toISOString(),
        metadata: {
          fileId: item.file_id,
          size: item.size,
          mimeType: item.mime_type,
        },
        sessionId: currentSessionId ?? undefined,
      });
    }
    useArtifactStore.getState().openTab(artifactId);
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Search */}
      <div className="px-3 pt-3 pb-2 flex-shrink-0">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground-tertiary" />
          <input
            id="workspace-files-search"
            name="workspaceFilesSearch"
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('chat.workspace.files.searchPlaceholder', {
              defaultValue: 'Search folders and files',
            })}
            className="w-full pl-8 pr-2 py-1.5 text-xs rounded-lg bg-surface-sunken border border-transparent focus:border-primary-400 focus:outline-none text-foreground placeholder:text-muted-foreground-tertiary"
          />
        </div>
      </div>

      {/* Split: tree (left) + preview (right) */}
      <div className="grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-2 flex-1 min-h-0 px-3 pb-3">
        {/* Tree panel */}
        <div className="flex flex-col min-h-0 rounded-xl bg-surface-sunken/40 border border-border-subtle/50 overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-1.5 border-b border-border-subtle/60 bg-surface/20">
            <div className="text-[10px] font-semibold text-muted-foreground-tertiary uppercase tracking-wider shrink-0">
              {t('chat.workspace.title', { defaultValue: 'Workspace' })}
            </div>
            <div className="flex flex-wrap items-center justify-end gap-2 min-w-0">
              <button
                type="button"
                disabled={zipIds.size === 0 || zipBusy}
                onClick={() => void downloadZipBundle()}
                className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-medium bg-primary-600 text-white hover:bg-primary-700 disabled:pointer-events-none disabled:opacity-40"
              >
                <FileArchive className="h-3 w-3 shrink-0" aria-hidden />
                {zipBusy
                  ? t('chat.workspace.files.downloadZipPreparing')
                  : t('chat.workspace.files.downloadZip', { count: zipIds.size })}
              </button>
              <button
                type="button"
                disabled={
                  promoteTargets.length === 0 || promoteMutation.isPending || zipBusy
                }
                onClick={() => void promoteToKnowledge()}
                title={t('chat.workspace.files.addToKnowledgeHint')}
                className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-medium border border-border-subtle bg-surface hover:bg-surface-sunken disabled:pointer-events-none disabled:opacity-40"
              >
                <BookPlus className="h-3 w-3 shrink-0" aria-hidden />
                {promoteMutation.isPending
                  ? t('chat.workspace.files.addToKnowledgeBusy')
                  : t('chat.workspace.files.addToKnowledge', {
                      count: promoteTargets.length,
                    })}
              </button>
              {zipIds.size > 0 && !zipBusy ? (
                <button
                  type="button"
                  className="text-[10px] text-muted-foreground hover:text-foreground"
                  onClick={() => {
                    setZipIds(new Set());
                    setZipError(null);
                  }}
                >
                  {t('chat.workspace.files.downloadZipClear')}
                </button>
              ) : null}
              {zipError ? (
                <span className="min-w-0 max-w-[140px] sm:max-w-[200px] truncate text-[10px] text-red-500">
                  {zipError}
                </span>
              ) : null}
              {promoteError ? (
                <span className="min-w-0 max-w-[140px] sm:max-w-[200px] truncate text-[10px] text-red-500">
                  {promoteError}
                </span>
              ) : null}
            </div>
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto chat-sessions-scroll p-1">
            {showGlobalEmpty ? (
              <EmptyHint
                text={
                  query
                    ? t('chat.workspace.files.emptySearch', {
                        defaultValue: 'No matching entries.',
                      })
                    : t('chat.workspace.files.emptyNoFolder', {
                        defaultValue: 'No files in this session yet.',
                      })
                }
              />
            ) : (
              <ul className="flex flex-col gap-0.5">
                {sharedProjectItems.length > 0 ? (
                  <>
                    <li>
                      <p className="px-2 text-[10px] uppercase tracking-wide text-muted-foreground-tertiary">
                        {t('chat.workspace.files.sharedProjectFiles')}
                      </p>
                    </li>
                    {sharedProjectItems.map((item) => {
                      const isActive =
                        selectedFile?.source === 'workspace' &&
                        selectedFile.item.file_id === item.file_id;
                      return (
                        <li key={`project-${item.file_id}`} className="flex items-stretch gap-0.5">
                          <ZipCircleCheckbox
                            id={`project-zip-${item.file_id}`}
                            checked={zipIds.has(item.file_id)}
                            disabled={item.excludeFromZip}
                            onChange={() => toggleZipId(item.file_id)}
                            ariaLabel={t('chat.workspace.files.zipToggleAria', {
                              defaultValue: 'Include in ZIP download',
                            })}
                          />
                          <button
                            type="button"
                            onClick={() =>
                              setSelectedFile({ source: 'workspace', item })
                            }
                            onDoubleClick={() => openAsArtifact(item)}
                            className={cn(
                              'min-w-0 flex-1 flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs text-left transition-colors',
                              isActive
                                ? 'bg-surface text-foreground shadow-sm'
                                : 'text-muted-foreground hover:bg-surface-sunken hover:text-foreground',
                            )}
                            title={item.file_name}
                          >
                            <span className="flex-shrink-0">
                              {getFileExtensionIcon(item.file_name)}
                            </span>
                            <span className="flex-1 min-w-0 truncate">
                              {item.file_name}
                            </span>
                            <span className="text-[10px] text-muted-foreground-tertiary tabular-nums shrink-0">
                              {formatSize(item.size)}
                            </span>
                          </button>
                        </li>
                      );
                    })}
                  </>
                ) : null}
                <li>
                  <p className="px-2 text-[10px] uppercase tracking-wide text-muted-foreground-tertiary">
                    {t('chat.workspace.files.sessionWorkspace', {
                      defaultValue: 'Session Workspace',
                    })}
                  </p>
                </li>
                {sessionEditPaths.length > 0 ? (
                  <li className="mb-1 rounded-lg border border-border-subtle/60 bg-surface/30 px-2 py-1.5">
                    <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground-tertiary">
                      <GitBranch className="w-3 h-3" aria-hidden />
                      {t('chat.workspace.folders.sessionChanges', {
                        defaultValue: 'Session edits',
                      })}
                    </div>
                    <ul className="mt-1 space-y-0.5 max-h-28 overflow-y-auto">
                      {sessionEditPaths.map((row) => (
                        <li
                          key={row.path}
                          className="flex items-baseline gap-1.5 text-[11px] font-mono text-foreground/90 min-w-0"
                          title={row.path}
                        >
                          <span className="truncate flex-1">{row.path}</span>
                          <span className="flex-shrink-0 text-[9px] text-muted-foreground-tertiary">
                            {row.tool}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </li>
                ) : null}
                {filteredWorkspace.map((item) => {
                  const isActive =
                    selectedFile?.source === 'workspace' &&
                    selectedFile.item.file_id === item.file_id;
                  return (
                    <li key={item.file_id} className="flex items-stretch gap-0.5">
                      <ZipCircleCheckbox
                        id={`workspace-zip-${item.file_id}`}
                        checked={zipIds.has(item.file_id)}
                        disabled={item.excludeFromZip}
                        onChange={() => toggleZipId(item.file_id)}
                        ariaLabel={t('chat.workspace.files.zipToggleAria', {
                          defaultValue: 'Include in ZIP download',
                        })}
                      />
                      <button
                        type="button"
                        onClick={() =>
                          setSelectedFile({ source: 'workspace', item })
                        }
                        onDoubleClick={() => openAsArtifact(item)}
                        className={cn(
                          'min-w-0 flex-1 flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs text-left transition-colors',
                          isActive
                            ? 'bg-surface text-foreground shadow-sm'
                            : 'text-muted-foreground hover:bg-surface-sunken hover:text-foreground',
                        )}
                        title={item.file_name}
                      >
                        <span className="flex-shrink-0">
                          {getFileExtensionIcon(item.file_name)}
                        </span>
                        <span className="flex-1 min-w-0 truncate">
                          {item.file_name}
                        </span>
                        {item.is_ai && item.version && item.version > 1 ? (
                          <span className="text-[10px] rounded bg-emerald-100 dark:bg-emerald-900/30 text-emerald-800 dark:text-emerald-200 px-1 py-0.5 shrink-0">
                            {t('chat.workspace.files.latestVersion', {
                              defaultValue: 'latest',
                            })}
                          </span>
                        ) : null}
                        {isAiOperated(item) && (
                          <span className="text-[10px] rounded bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 px-1 py-0.5">
                            AI
                          </span>
                        )}
                        <span className="text-[10px] text-muted-foreground-tertiary tabular-nums shrink-0">
                          {formatSize(item.size)}
                        </span>
                      </button>
                    </li>
                  );
                })}
                {(knowledgeLoading || filteredKnowledge.length > 0) && (
                  <li className="pt-2">
                    <p className="px-2 text-[10px] uppercase tracking-wide text-muted-foreground-tertiary">
                      {t('chat.workspace.files.systemKnowledgeBase', {
                        defaultValue: 'System Knowledge Base',
                      })}
                    </p>
                  </li>
                )}
                {knowledgeLoading && filteredKnowledge.length === 0
                  ? Array.from({ length: 3 }).map((_, idx) => (
                      <li key={`kb-loading-${idx}`} className="px-2 py-0.5">
                        <div className="h-7 rounded-md bg-surface/70 border border-border-subtle/60 animate-pulse" />
                      </li>
                    ))
                  : filteredKnowledge.map((doc) => {
                      const isActive =
                        selectedFile?.source === 'knowledge' &&
                        selectedFile.item.id === doc.id;
                      return (
                        <li key={doc.id} className="flex items-stretch gap-0.5">
                          <ZipCircleCheckbox
                            id={`workspace-zip-kb-${doc.id}`}
                            checked={zipIds.has(doc.id)}
                            onChange={() => toggleZipId(doc.id)}
                            ariaLabel={t('chat.workspace.files.zipToggleAria', {
                              defaultValue: 'Include in ZIP download',
                            })}
                          />
                          <button
                            type="button"
                            onClick={() =>
                              setSelectedFile({ source: 'knowledge', item: doc })
                            }
                            className={cn(
                              'min-w-0 flex-1 flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs text-left transition-colors',
                              isActive
                                ? 'bg-surface text-foreground shadow-sm'
                                : 'text-muted-foreground hover:bg-surface-sunken hover:text-foreground',
                            )}
                            title={doc.original_name}
                          >
                            <FileText className="w-4 h-4 flex-shrink-0 text-sky-500" />
                            <span className="flex-1 min-w-0 truncate">
                              {doc.original_name}
                            </span>
                            {isAiOperated(doc) && (
                              <span className="text-[10px] rounded bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 px-1 py-0.5">
                                AI
                              </span>
                            )}
                            <span className="text-[10px] text-muted-foreground-tertiary tabular-nums shrink-0">
                              {formatSize(doc.size)}
                            </span>
                          </button>
                        </li>
                      );
                    })}
              </ul>
            )}
          </div>
        </div>

        {/* Preview panel */}
        <div className="hidden md:flex h-full min-h-0 flex-col rounded-xl bg-surface-sunken/40 border border-border-subtle/50 overflow-hidden">
          <div className="flex-shrink-0 p-2">
            <DocGenerationLivePreview />
          </div>
          {selectedFile ? (
            <FilePreview
              file={selectedFile}
              onInsert={() => {
                if (selectedFile.source === 'workspace') {
                  if (selectedFile.item.source === 'canvas') return;
                  pushFileRef({
                    kind: 'workspace',
                    token: `@file:${selectedFile.item.file_name}#${selectedFile.item.file_id}`,
                    label: selectedFile.item.file_name,
                  });
                } else {
                  pushFileRef({
                    kind: 'knowledge',
                    token: `@knowledge:${selectedFile.item.original_name}#${selectedFile.item.id}`,
                    label: selectedFile.item.original_name,
                  });
                }
              }}
              onOpen={() => {
                if (selectedFile.source === 'workspace') {
                  openAsArtifact(selectedFile.item);
                }
              }}
            />
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-center px-6">
              <FolderOpen className="w-8 h-8 text-muted-foreground-tertiary mb-2" />
              <p className="text-xs text-muted-foreground">
                {t('chat.workspace.files.selectHint', {
                  defaultValue:
                    'Click a file to preview in this session.',
                })}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function CanvasFilePreview({
  fileName,
  previewPath,
  onOpen,
}: {
  fileName: string;
  previewPath: string;
  onOpen: () => void;
}) {
  const { t } = useTranslation();
  const [jsEnabled, setJsEnabled] = useState(false);
  const [iframeKey, setIframeKey] = useState(0);
  const iframeSrcBase =
    previewPath.startsWith('http://') || previewPath.startsWith('https://')
      ? previewPath
      : `${typeof window !== 'undefined' ? window.location.origin : ''}${previewPath.startsWith('/') ? previewPath : `/${previewPath}`}`;
  const iframeSrc = previewPath ? withCanvasPreviewJs(iframeSrcBase, jsEnabled) : '';
  const isApiPreview = iframeSrc.includes('/canvas/preview');

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex items-start gap-2 px-3 py-2 border-b border-border-subtle/60">
        <div className="w-8 h-8 rounded-lg bg-surface flex items-center justify-center flex-shrink-0">
          {getFileExtensionIcon(fileName)}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold text-foreground truncate">{fileName}</p>
          <p className="text-[11px] text-muted-foreground-tertiary tabular-nums">
            {t('chat.workspace.files.canvasPreview', { defaultValue: 'Canvas preview' })}
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            setJsEnabled((v) => !v);
            setIframeKey((k) => k + 1);
          }}
          className={cn(
            'shrink-0 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide transition-colors',
            jsEnabled
              ? 'bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-200'
              : 'text-muted-foreground hover:text-foreground hover:bg-surface-sunken',
          )}
          title={jsEnabled ? t('chat.canvas.jsOn') : t('chat.canvas.jsOff')}
        >
          <span className="inline-flex items-center gap-0.5">
            <Code2 className="w-3 h-3" aria-hidden />
            {jsEnabled ? t('chat.canvas.jsOnShort') : t('chat.canvas.jsOffShort')}
          </span>
        </button>
      </div>
      <div className="flex flex-1 min-h-0 flex-col overflow-hidden bg-background">
        {previewPath ? (
          <iframe
            key={`${iframeKey}-${jsEnabled ? 'js' : 'nojs'}`}
            title={fileName}
            src={iframeSrc}
            className="h-full w-full min-h-[200px] border-0"
            sandbox={canvasIframeSandbox(jsEnabled, isApiPreview) || undefined}
          />
        ) : (
          <p className="p-3 text-xs text-muted-foreground">
            {t('chat.workspace.files.canvasNoPreview', {
              defaultValue: 'No preview path for this canvas.',
            })}
          </p>
        )}
      </div>
      <div className="flex gap-2 p-2 border-t border-border-subtle/60">
        <button
          type="button"
          onClick={onOpen}
          className="flex-1 text-[11px] font-medium px-2 py-1.5 rounded-lg bg-primary-600 hover:bg-primary-700 text-white transition-colors"
        >
          {t('chat.workspace.files.openAction', { defaultValue: 'Open as tab' })}
        </button>
        <button
          type="button"
          disabled
          className="flex-1 text-[11px] font-medium px-2 py-1.5 rounded-lg bg-surface text-muted-foreground-tertiary opacity-50 cursor-not-allowed"
        >
          {t('chat.workspace.files.insertAction', { defaultValue: 'Reference' })}
        </button>
      </div>
    </div>
  );
}

function FilePreview({
  file,
  onInsert,
  onOpen,
}: {
  file: SelectedItem;
  onInsert: () => void;
  onOpen: () => void;
}) {
  const { t } = useTranslation();

  if (file.source === 'workspace' && file.item.source === 'canvas') {
    return (
      <CanvasFilePreview
        fileName={file.item.file_name}
        previewPath={file.item.previewPath ?? ''}
        onOpen={onOpen}
      />
    );
  }

  const fileName =
    file.source === 'workspace'
      ? file.item.file_name
      : file.item.original_name;
  const fileSize = file.item.size;
  const fileId = file.source === 'workspace' ? file.item.file_id : file.item.id;
  const mime = file.item.mime_type;

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex items-start gap-2 px-3 py-2 border-b border-border-subtle/60">
        <div className="w-8 h-8 rounded-lg bg-surface flex items-center justify-center flex-shrink-0">
          {getFileExtensionIcon(fileName)}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold text-foreground truncate">
            {fileName}
          </p>
          <p className="text-[11px] text-muted-foreground-tertiary tabular-nums">
            {formatSize(fileSize)} · {mime || file.source}
          </p>
        </div>
      </div>
      <div className="flex flex-1 min-h-0 flex-col overflow-hidden px-3 py-3 text-[11px] text-muted-foreground leading-relaxed">
        <UniversalFilePreview
          fileId={fileId}
          fileName={fileName}
          mimeType={mime}
          sizeBytes={fileSize}
          showActions={false}
          layout="fill"
          className="min-h-0 flex-1"
        />
      </div>
      <div className="flex gap-2 p-2 border-t border-border-subtle/60">
        {file.source === 'workspace' && (
          <button
            type="button"
            onClick={onOpen}
            className="flex-1 text-[11px] font-medium px-2 py-1.5 rounded-lg bg-primary-600 hover:bg-primary-700 text-white transition-colors"
          >
            {t('chat.workspace.files.openAction', {
              defaultValue: 'Open as tab',
            })}
          </button>
        )}
        <button
          type="button"
          onClick={() => {
            void downloadAuthenticatedFile(fileId, fileName);
          }}
          className="flex-1 text-[11px] font-medium px-2 py-1.5 rounded-lg bg-surface text-muted-foreground hover:text-foreground hover:bg-surface-sunken transition-colors flex items-center justify-center gap-1"
        >
          <Download className="w-3 h-3" />
          {t('knowledge.download', { defaultValue: 'Download' })}
        </button>
        <button
          type="button"
          onClick={onInsert}
          className="flex-1 text-[11px] font-medium px-2 py-1.5 rounded-lg bg-surface text-muted-foreground hover:text-foreground hover:bg-surface-sunken transition-colors flex items-center justify-center gap-1"
        >
          <Send className="w-3 h-3" />
          {t('chat.workspace.files.insertAction', {
            defaultValue: 'Reference',
          })}
        </button>
      </div>
    </div>
  );
}

function ZipCircleCheckbox({
  id,
  checked,
  disabled,
  onChange,
  ariaLabel,
}: {
  id: string;
  checked: boolean;
  disabled?: boolean;
  onChange: () => void;
  ariaLabel: string;
}) {
  return (
    <label
      htmlFor={id}
      className={cn(
        'relative flex items-center pl-1 shrink-0',
        disabled ? 'cursor-not-allowed' : 'cursor-pointer',
      )}
    >
      <input
        id={id}
        name={id}
        type="checkbox"
        className="peer sr-only"
        checked={checked}
        disabled={disabled}
        onChange={onChange}
        aria-label={ariaLabel}
      />
      <span
        aria-hidden
        className={cn(
          'h-3 w-3 shrink-0 rounded-full border border-solid transition-[background-color,border-color] duration-150',
          'border-red-400/95 bg-transparent dark:border-red-500/88',
          'peer-checked:border-red-600 peer-checked:bg-red-600 dark:peer-checked:border-red-500 dark:peer-checked:bg-red-500',
          'peer-focus-visible:outline-none peer-focus-visible:ring-2 peer-focus-visible:ring-red-400/45 peer-focus-visible:ring-offset-1 peer-focus-visible:ring-offset-background',
          'peer-disabled:opacity-30',
        )}
      />
    </label>
  );
}

function EmptyHint({ text }: { text: string }) {
  return (
    <div className="text-center py-8 px-4">
      <p className="text-xs text-muted-foreground">{text}</p>
    </div>
  );
}
