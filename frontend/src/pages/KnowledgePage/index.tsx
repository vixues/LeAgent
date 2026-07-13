import { useState, useRef, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query';
import {
  Upload,
  FileText,
  File,
  Image,
  Trash2,
  Download,
  Eye,
  FolderPlus,
  PanelLeft,
} from 'lucide-react';
import {
  Card,
  CardContent,
  Button,
  Badge,
  Sheet,
  SheetContent,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Input,
} from '@/components/ui';
import { PageShell } from '@/components/layout/PageShell';
import {
  useKnowledgeStore,
  type KnowledgeDocument,
} from '@/stores/knowledge';
import { useDocuments, useUploadDocument } from '@/hooks/useKnowledge';
import {
  useFolderTree,
  useCreateFolder,
  useDeleteFolder,
  type FolderTreeNode,
} from '@/hooks/useFolders';
import {
  FolderTreeView,
  FolderBreadcrumb,
} from '@/components/folders';
import {
  commitKnowledgeSearchQuery,
  KNOWLEDGE_SEARCH_DEBOUNCE_MS,
  KNOWLEDGE_SEARCH_LIMIT,
  normalizeKnowledgeQuery,
  shouldAutoSearch,
} from '@/lib/knowledgeSearch';
import { formatDate, formatRelativeTime } from '@/lib/utils';
import { cn } from '@/lib/utils';
import { PageLoader } from '@/components/common/PageLoader';
import { EmptyState } from '@/components/common/EmptyState';
import { SearchInput } from '@/components/common/SearchInput';
import { apiClient } from '@/api/client';
import { useRealtimeFileSync } from '@/hooks/useRealtimeFileSync';
import { UniversalFilePreview } from '@/components/files/UniversalFilePreview';
import { downloadAuthenticatedFile } from '@/lib/downloadAuthenticatedFile';
import { useToast } from '@/components/ui/Toaster';

interface DocumentSearchResult {
  id: string;
  name: string;
  file_type: string;
  score: number;
  snippet?: string | null;
  chunk_id?: string | null;
  start_offset?: number | null;
  end_offset?: number | null;
}

interface DocumentSearchResponse {
  query: string;
  results: DocumentSearchResult[];
  total: number;
}

type IndexStatusKey = 'indexed' | 'processing' | 'failed' | 'pending';

function deriveIndexStatus(
  status?: string,
  isIndexed?: boolean,
): IndexStatusKey {
  const normalized = (status ?? '').toLowerCase();
  if (normalized === 'failed') return 'failed';
  if (normalized === 'processing' || normalized === 'uploaded') {
    return isIndexed ? 'indexed' : 'processing';
  }
  if (isIndexed) return 'indexed';
  if (normalized === 'processed' && !isIndexed) return 'pending';
  return isIndexed ? 'indexed' : 'pending';
}

function indexStatusBadgeVariant(
  key: IndexStatusKey,
): 'success' | 'warning' | 'error' | 'default' {
  switch (key) {
    case 'indexed':
      return 'success';
    case 'processing':
      return 'warning';
    case 'failed':
      return 'error';
    default:
      return 'default';
  }
}

function mapSearchResultToDocument(r: DocumentSearchResult): KnowledgeDocument {
  const ft = r.file_type;
  const typeStr =
    ft === 'image'
      ? 'image/png'
      : ft === 'document'
        ? 'application/pdf'
        : ft === 'data'
          ? 'application/vnd.ms-excel'
          : 'application/octet-stream';
  return {
    id: String(r.id),
    name: r.name,
    type: typeStr,
    size: 0,
    url: `/api/v1/files/${r.id}`,
    preview: r.snippet ?? undefined,
    summary: r.snippet ?? null,
    isIndexed: true,
    status: 'processed',
    createdAt: new Date().toISOString(),
  };
}

/** Drop coding-project folders from the knowledge tree. */
function filterProjectNodes(nodes: FolderTreeNode[]): FolderTreeNode[] {
  return nodes
    .filter((n) => !n.is_project)
    .map((n) => ({
      ...n,
      children: filterProjectNodes(n.children ?? []),
    }));
}

function findFolderPath(
  nodes: FolderTreeNode[],
  targetId: string,
): FolderTreeNode[] | null {
  for (const node of nodes) {
    if (node.is_project) continue;
    if (node.id === targetId) return [node];
    if (node.children?.length) {
      const childPath = findFolderPath(node.children, targetId);
      if (childPath) return [node, ...childPath];
    }
  }
  return null;
}

export default function KnowledgePage() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const {
    selectedDocument,
    setSelectedDocument,
    setPreviewOpen,
  } = useKnowledgeStore();

  const [currentFolderId, setCurrentFolderId] = useState<string | null>(null);
  const [mobileTreeOpen, setMobileTreeOpen] = useState(false);
  /** Local draft — updates every keystroke without triggering remote search. */
  const [draftQuery, setDraftQuery] = useState('');
  /** Committed remote query after debounce/gate (or Enter). */
  const [committedQuery, setCommittedQuery] = useState('');
  const [createFolderOpen, setCreateFolderOpen] = useState(false);
  const [createFolderParentId, setCreateFolderParentId] = useState<
    string | null
  >(null);
  const [newFolderName, setNewFolderName] = useState('');
  const [creatingFolder, setCreatingFolder] = useState(false);
  useRealtimeFileSync(true);

  const isSearchMode = committedQuery.length > 0;
  const draftNormalized = normalizeKnowledgeQuery(draftQuery);
  const showSearchMinHint =
    draftNormalized.length > 0 &&
    !shouldAutoSearch(draftNormalized) &&
    !isSearchMode;

  const handleDownloadDocument = useCallback(
    (docId: string, fileName: string) => {
      void downloadAuthenticatedFile(docId, fileName).catch(() => {
        toast({
          title: t('knowledge.downloadFailed'),
          variant: 'error',
        });
      });
    },
    [t, toast],
  );

  const { data: folderTreeRaw = [] } = useFolderTree();
  const knowledgeTree = useMemo(
    () => filterProjectNodes(folderTreeRaw),
    [folderTreeRaw],
  );

  const breadcrumbItems = useMemo(() => {
    if (!currentFolderId) return [];
    const path = findFolderPath(knowledgeTree, currentFolderId);
    return (path ?? []).map((n) => ({ id: n.id, name: n.name }));
  }, [knowledgeTree, currentFolderId]);

  const { data: documentsData, isLoading: listLoading } = useDocuments({
    enabled: !isSearchMode,
    folder_id: currentFolderId ?? undefined,
    unfiled: currentFolderId == null,
  });

  const {
    data: searchData,
    isLoading: searchLoading,
    isFetching: searchFetching,
  } = useQuery({
    queryKey: ['documents', 'search', committedQuery],
    queryFn: () =>
      apiClient.get<DocumentSearchResponse>('/documents/search', {
        query: committedQuery,
        limit: KNOWLEDGE_SEARCH_LIMIT,
      }),
    enabled: isSearchMode,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });

  const displayDocuments = useMemo(() => {
    if (!isSearchMode) {
      return (documentsData?.items ?? []).map(
        (f): KnowledgeDocument => ({
          id: String(f.id),
          name: f.original_name,
          type: f.mime_type ?? f.file_type,
          size: f.size,
          url: `/api/v1/files/${f.id}`,
          summary: f.summary ?? null,
          preview: f.summary ?? undefined,
          status: f.status,
          isIndexed: f.is_indexed,
          createdAt: f.created_at,
        }),
      );
    }
    return (searchData?.results ?? []).map(mapSearchResultToDocument);
  }, [isSearchMode, documentsData, searchData]);

  // First remote search: show loader. Refetches keep previous hits visible.
  const listBusy = isSearchMode
    ? searchLoading && !searchData
    : listLoading;

  const showEmpty = !listBusy && displayDocuments.length === 0;

  const commitSearch = useCallback((value: string, force = false) => {
    setCommittedQuery(commitKnowledgeSearchQuery(value, { force }));
  }, []);

  const handleSearchDebounced = useCallback(
    (value: string) => {
      commitSearch(value, false);
    },
    [commitSearch],
  );

  const handleSearchSubmit = useCallback(
    (value: string) => {
      setDraftQuery(value);
      commitSearch(value, true);
    },
    [commitSearch],
  );

  const uploadDocument = useUploadDocument();
  const createFolder = useCreateFolder();
  const deleteFolder = useDeleteFolder();

  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const navigateToFolder = useCallback(
    (id: string | null) => {
      setCurrentFolderId(id);
      setSelectedDocument(null);
      setPreviewOpen(false);
      setMobileTreeOpen(false);
    },
    [setSelectedDocument, setPreviewOpen],
  );

  const openCreateFolder = useCallback(
    (parentId: string | null = currentFolderId) => {
      setCreateFolderParentId(parentId);
      setNewFolderName('');
      setCreateFolderOpen(true);
    },
    [currentFolderId],
  );

  const closeCreateFolder = useCallback(() => {
    if (creatingFolder) return;
    setCreateFolderOpen(false);
    setNewFolderName('');
  }, [creatingFolder]);

  const submitCreateFolder = useCallback(async () => {
    const name = newFolderName.trim();
    if (!name) return;
    setCreatingFolder(true);
    try {
      await createFolder.mutateAsync({
        name,
        parent_id: createFolderParentId,
      });
      setCreateFolderOpen(false);
      setNewFolderName('');
    } catch {
      toast({
        title: t('knowledge.createFolderFailed'),
        variant: 'error',
      });
    } finally {
      setCreatingFolder(false);
    }
  }, [createFolder, createFolderParentId, newFolderName, t, toast]);

  const handleDeleteFolder = useCallback(
    async (folderId: string, e?: React.MouseEvent) => {
      e?.preventDefault();
      e?.stopPropagation();
      if (!window.confirm(t('knowledge.confirmDeleteFolder'))) return;
      try {
        await deleteFolder.mutateAsync({ id: folderId, recursive: true });
        if (currentFolderId === folderId) {
          navigateToFolder(null);
        }
      } catch {
        window.alert(t('knowledge.deleteUnavailable'));
      }
    },
    [deleteFolder, currentFolderId, navigateToFolder, t],
  );

  const handleFileSelect = async (files: FileList | null) => {
    if (!files || files.length === 0) return;

    setUploadProgress(0);
    try {
      for (const file of Array.from(files)) {
        await uploadDocument.mutateAsync({
          file,
          folder_id: currentFolderId ?? undefined,
        });
      }
    } finally {
      setUploadProgress(null);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    handleFileSelect(e.dataTransfer.files);
  };

  const handleDelete = async (id: string) => {
    if (window.confirm(t('knowledge.confirmDelete'))) {
      try {
        await apiClient.delete(`/files/${id}`);
        await queryClient.invalidateQueries({ queryKey: ['documents'] });
      } catch {
        window.alert(t('knowledge.deleteUnavailable'));
        return;
      }
      if (selectedDocument?.id === id) {
        setSelectedDocument(null);
        setPreviewOpen(false);
      }
    }
  };

  const getFileIcon = (type: string) => {
    if (type.startsWith('image/') || type === 'image') return Image;
    if (
      type.includes('pdf') ||
      type.includes('document') ||
      type.includes('word')
    ) {
      return FileText;
    }
    return File;
  };

  const getFileTypeLabel = (type: string) => {
    if (type.startsWith('image/') || type === 'image') {
      return t('knowledge.types.image');
    }
    if (type.includes('pdf')) return 'PDF';
    if (type.includes('word') || type === 'document') {
      return t('knowledge.types.document');
    }
    if (
      type.includes('spreadsheet') ||
      type.includes('excel') ||
      type.includes('csv') ||
      type === 'data'
    ) {
      return t('knowledge.types.spreadsheet');
    }
    if (type.includes('text') || type.includes('markdown')) {
      return t('knowledge.types.text');
    }
    return t('knowledge.types.other');
  };

  const formatFileSize = (bytes: number) => {
    if (bytes <= 0) return '—';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const rowBlurb = (doc: KnowledgeDocument): string => {
    if (isSearchMode && doc.preview) return doc.preview;
    const statusKey = deriveIndexStatus(doc.status, doc.isIndexed);
    if (statusKey === 'processing') return t('knowledge.indexing');
    if (doc.summary?.trim()) return doc.summary.trim();
    if (doc.preview?.trim()) return doc.preview.trim();
    return t('knowledge.noSummary');
  };

  const treeView = (
    <FolderTreeView
      tree={knowledgeTree}
      selectedId={currentFolderId}
      onSelect={navigateToFolder}
      onCreateFolder={(parentId) => openCreateFolder(parentId)}
      onContextMenu={(e, folderId) => {
        void handleDeleteFolder(folderId, e);
      }}
      title={t('knowledge.folders.treeTitle')}
      rootLabel={t('knowledge.folders.root')}
      emptyLabel={t('knowledge.folders.emptyTree')}
    />
  );

  return (
    <PageShell
      title={t('knowledge.title')}
      description={t('knowledge.description')}
      contentClassName="flex min-h-0 flex-1 flex-col"
      actions={
        <>
          <Button
            variant="ghost"
            size="sm"
            className="lg:hidden"
            onClick={() => setMobileTreeOpen(true)}
            leftIcon={<PanelLeft className="w-4 h-4" />}
            aria-label={t('knowledge.folders.showTree')}
          >
            {t('knowledge.folders.showTree')}
          </Button>
          <div className="relative">
            <SearchInput
              placeholder={t('knowledge.search')}
              value={draftQuery}
              onChange={setDraftQuery}
              onSearch={handleSearchDebounced}
              onSubmit={handleSearchSubmit}
              debounceMs={KNOWLEDGE_SEARCH_DEBOUNCE_MS}
              loading={isSearchMode && searchFetching}
              className="w-64"
            />
            {showSearchMinHint && (
              <p className="absolute left-0 top-full mt-1 text-[11px] text-muted-foreground whitespace-nowrap">
                {t('knowledge.searchMinHint')}
              </p>
            )}
          </div>
          <Button
            variant="outline"
            onClick={() => openCreateFolder(currentFolderId)}
            leftIcon={<FolderPlus className="w-4 h-4" />}
          >
            {t('knowledge.newFolder')}
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => handleFileSelect(e.target.files)}
            accept=".pdf,.doc,.docx,.txt,.md,.csv,.xlsx,.xls,.png,.jpg,.jpeg"
          />
          <Button
            onClick={() => fileInputRef.current?.click()}
            leftIcon={<Upload className="w-4 h-4" />}
          >
            {t('knowledge.upload')}
          </Button>
        </>
      }
    >
      <div className="grid min-h-0 flex-1 grid-cols-1 grid-rows-[minmax(0,1fr)] gap-6 lg:grid-cols-[240px_minmax(0,1.4fr)_minmax(0,1fr)]">
        <Card
          padding="none"
          className="hidden min-h-0 overflow-hidden lg:flex lg:flex-col"
        >
          {treeView}
        </Card>

        <Card
          className={cn(
            'flex min-h-0 min-w-0 flex-col overflow-hidden transition-colors',
            dragOver &&
              'ring-2 ring-primary-500 bg-primary-50 dark:bg-primary-900/20',
          )}
          padding="none"
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
        >
          <div className="p-4 border-b border-border space-y-3 flex-shrink-0">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-2xl font-semibold text-foreground">
                {t('knowledge.documents')}
              </h2>
              <span className="text-sm text-muted-foreground shrink-0">
                {`${displayDocuments.length} ${t('knowledge.items')}`}
              </span>
            </div>

            {isSearchMode ? (
              <p className="text-xs text-muted-foreground">
                {t('knowledge.searchAllHint')}
              </p>
            ) : (
              <FolderBreadcrumb
                items={breadcrumbItems}
                onNavigate={navigateToFolder}
                rootLabel={t('knowledge.folders.root')}
                ariaLabel={t('knowledge.folders.breadcrumbAria')}
              />
            )}
          </div>

          {uploadProgress !== null && (
            <div className="px-4 py-3 border-b border-border flex-shrink-0">
              <div className="flex items-center gap-3">
                <div className="flex-1 h-2 bg-border rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary-500 transition-[color,background-color,border-color,box-shadow,opacity,transform] duration-300"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
                <span className="text-sm text-muted-foreground">
                  {t('knowledge.uploading')}
                </span>
              </div>
            </div>
          )}

          <CardContent padding="none" className="min-h-0 flex-1 overflow-y-auto">
            {listBusy ? (
              <div className="flex items-center justify-center py-12">
                <PageLoader message={t('common.loading')} />
              </div>
            ) : !showEmpty ? (
              <div className="divide-y divide-border">
                {displayDocuments.map((doc) => {
                  const FileIcon = getFileIcon(doc.type);
                  const isSelected = selectedDocument?.id === doc.id;
                  const statusKey = deriveIndexStatus(
                    doc.status,
                    doc.isIndexed,
                  );
                  const blurb = rowBlurb(doc);

                  return (
                    <div
                      key={doc.id}
                      className={cn(
                        'flex items-start gap-4 p-4 cursor-pointer transition-colors',
                        isSelected
                          ? 'bg-primary-50 dark:bg-primary-900/20'
                          : 'hover:bg-surface-sunken/80',
                      )}
                      onClick={() => {
                        setSelectedDocument(doc);
                        setPreviewOpen(true);
                      }}
                    >
                      <div className="flex-shrink-0 w-10 h-10 mt-0.5 rounded-lg bg-surface-sunken flex items-center justify-center">
                        <FileIcon className="w-5 h-5 text-muted-foreground" />
                      </div>
                      <div className="flex-1 min-w-0 space-y-1.5">
                        <div className="flex items-center gap-2 min-w-0">
                          <p className="font-medium text-foreground truncate">
                            {doc.name}
                          </p>
                          <Badge
                            variant="outline"
                            size="sm"
                            className="shrink-0"
                          >
                            {getFileTypeLabel(doc.type)}
                          </Badge>
                        </div>
                        <p
                          className={cn(
                            'text-sm line-clamp-2',
                            doc.summary || doc.preview
                              ? 'text-muted-foreground'
                              : 'text-muted-foreground/70 italic',
                          )}
                        >
                          {blurb}
                        </p>
                        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                          <Badge
                            variant={indexStatusBadgeVariant(statusKey)}
                            size="sm"
                          >
                            {isSearchMode
                              ? t('knowledge.searchMatch')
                              : t(`knowledge.status.${statusKey}`)}
                          </Badge>
                          {!isSearchMode && (
                            <>
                              <span>{formatFileSize(doc.size)}</span>
                              <span aria-hidden>·</span>
                              <span>
                                {formatRelativeTime(doc.createdAt)}
                              </span>
                            </>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDownloadDocument(doc.id, doc.name);
                          }}
                        >
                          <Download className="w-4 h-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleDelete(doc.id);
                          }}
                          className="text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-900/20"
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <EmptyState
                type={isSearchMode ? 'search' : 'folder'}
                title={
                  isSearchMode
                    ? t('knowledge.searchEmpty')
                    : currentFolderId
                      ? t('knowledge.emptyFolder')
                      : t('knowledge.empty')
                }
                description={
                  isSearchMode
                    ? t('knowledge.searchEmptyHint')
                    : t('knowledge.dragOrClick')
                }
                action={
                  isSearchMode
                    ? undefined
                    : {
                        label: t('knowledge.selectFiles'),
                        onClick: () => fileInputRef.current?.click(),
                      }
                }
              />
            )}
          </CardContent>
        </Card>

        <div className="min-h-0 lg:min-h-[min(100%,calc(100dvh-8rem))]">
          <Card className="sticky top-8 flex max-h-[min(calc(100dvh-6rem),920px)] flex-col overflow-hidden min-h-0">
            <div className="p-4 border-b border-border flex-shrink-0">
              <h2 className="text-2xl font-semibold text-foreground">
                {t('knowledge.preview')}
              </h2>
            </div>
            <CardContent className="flex flex-col min-h-0 flex-1 overflow-hidden">
              {selectedDocument ? (
                <div className="flex flex-col min-h-0 flex-1 gap-4 overflow-hidden">
                  <div className="flex flex-shrink-0 items-center gap-3">
                    {(() => {
                      const FileIcon = getFileIcon(selectedDocument.type);
                      return (
                        <div className="w-12 h-12 rounded-lg bg-surface-sunken flex items-center justify-center">
                          <FileIcon className="w-6 h-6 text-muted-foreground" />
                        </div>
                      );
                    })()}
                    <div className="min-w-0 flex-1">
                      <p className="font-medium text-foreground truncate">
                        {selectedDocument.name}
                      </p>
                      <p className="text-sm text-muted-foreground">
                        {getFileTypeLabel(selectedDocument.type)}
                      </p>
                    </div>
                    <Badge
                      variant={indexStatusBadgeVariant(
                        deriveIndexStatus(
                          selectedDocument.status,
                          selectedDocument.isIndexed,
                        ),
                      )}
                      size="sm"
                    >
                      {t(
                        `knowledge.status.${deriveIndexStatus(
                          selectedDocument.status,
                          selectedDocument.isIndexed,
                        )}`,
                      )}
                    </Badge>
                  </div>

                  <div className="flex-shrink-0 space-y-2 text-sm">
                    <div className="flex justify-between gap-3">
                      <span className="text-muted-foreground">
                        {t('knowledge.size')}:
                      </span>
                      <span className="text-foreground">
                        {formatFileSize(selectedDocument.size)}
                      </span>
                    </div>
                    <div className="flex justify-between gap-3">
                      <span className="text-muted-foreground">
                        {t('knowledge.created')}:
                      </span>
                      <span className="text-foreground">
                        {formatDate(selectedDocument.createdAt)}
                      </span>
                    </div>
                    <div className="flex justify-between gap-3">
                      <span className="text-muted-foreground">
                        {t('knowledge.indexStatus')}:
                      </span>
                      <span className="text-foreground">
                        {t(
                          `knowledge.status.${deriveIndexStatus(
                            selectedDocument.status,
                            selectedDocument.isIndexed,
                          )}`,
                        )}
                      </span>
                    </div>
                    {selectedDocument.chunks != null && (
                      <div className="flex justify-between gap-3">
                        <span className="text-muted-foreground">
                          {t('knowledge.chunks')}:
                        </span>
                        <span className="text-foreground">
                          {selectedDocument.chunks}
                        </span>
                      </div>
                    )}
                  </div>

                  <div className="flex-shrink-0 p-3 rounded-lg bg-surface-sunken">
                    <p className="text-xs font-medium text-muted-foreground mb-1">
                      {t('knowledge.summary')}
                    </p>
                    <p
                      className={cn(
                        'text-sm line-clamp-6',
                        selectedDocument.summary || selectedDocument.preview
                          ? 'text-foreground'
                          : 'text-muted-foreground italic',
                      )}
                    >
                      {selectedDocument.summary?.trim() ||
                        selectedDocument.preview?.trim() ||
                        (deriveIndexStatus(
                          selectedDocument.status,
                          selectedDocument.isIndexed,
                        ) === 'processing'
                          ? t('knowledge.indexing')
                          : t('knowledge.noSummary'))}
                    </p>
                  </div>

                  <div className="flex flex-shrink-0 gap-2">
                    <Button
                      variant="outline"
                      className="flex-1"
                      onClick={() =>
                        handleDownloadDocument(
                          selectedDocument.id,
                          selectedDocument.name,
                        )
                      }
                      leftIcon={<Download className="w-4 h-4" />}
                    >
                      {t('knowledge.download')}
                    </Button>
                  </div>
                  <div className="min-h-0 flex-1 flex flex-col overflow-hidden border border-border rounded-lg bg-surface-sunken/30">
                    <UniversalFilePreview
                      fileId={selectedDocument.id}
                      fileName={selectedDocument.name}
                      mimeType={selectedDocument.type}
                      sizeBytes={selectedDocument.size}
                      showActions={false}
                      layout="fill"
                      className="min-h-0 flex-1"
                    />
                  </div>
                </div>
              ) : (
                <div className="py-8 text-center text-muted-foreground">
                  <Eye className="w-12 h-12 mx-auto mb-3 opacity-50" />
                  <p>{t('knowledge.selectToPreview')}</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      <Sheet open={mobileTreeOpen} onOpenChange={setMobileTreeOpen} side="left">
        <SheetContent className="p-0 w-[min(100vw-2rem,280px)]">
          {treeView}
        </SheetContent>
      </Sheet>

      <Modal
        isOpen={createFolderOpen}
        onClose={closeCreateFolder}
        size="sm"
      >
        <ModalHeader onClose={closeCreateFolder}>
          {t('knowledge.newFolder')}
        </ModalHeader>
        <ModalBody>
          <label className="block text-sm font-medium text-foreground mb-1.5">
            {t('knowledge.newFolderPrompt')}
          </label>
          <Input
            autoFocus
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            placeholder={t('knowledge.newFolderPlaceholder')}
            disabled={creatingFolder}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                void submitCreateFolder();
              }
            }}
          />
        </ModalBody>
        <ModalFooter>
          <Button
            variant="outline"
            onClick={closeCreateFolder}
            disabled={creatingFolder}
          >
            {t('common.cancel')}
          </Button>
          <Button
            onClick={() => void submitCreateFolder()}
            disabled={creatingFolder || !newFolderName.trim()}
            loading={creatingFolder}
          >
            {t('common.create')}
          </Button>
        </ModalFooter>
      </Modal>
    </PageShell>
  );
}
