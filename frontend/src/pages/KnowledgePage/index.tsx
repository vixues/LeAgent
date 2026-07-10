import { useState, useRef, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Upload,
  FileText,
  File,
  Image,
  Trash2,
  Download,
  Eye,
} from 'lucide-react';
import {
  Card,
  CardContent,
  Button,
  Badge,
} from '@/components/ui';
import { PageShell } from '@/components/layout/PageShell';
import { useKnowledgeStore } from '@/stores/knowledge';
import { useDocuments, useUploadDocument } from '@/hooks/useKnowledge';
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

interface KnowledgeDoc {
  id: string;
  name: string;
  type: string;
  size: number;
  url: string;
  preview?: string;
  chunks?: number;
  createdAt: string;
}

function mapSearchResultToDocument(r: DocumentSearchResult): KnowledgeDoc {
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
    url: '',
    preview: r.snippet ?? undefined,
    createdAt: new Date().toISOString(),
  };
}

export default function KnowledgePage() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const {
    search,
    setSearch,
    selectedDocument,
    setSelectedDocument,
    setPreviewOpen,
  } = useKnowledgeStore();

  const [debouncedQuery, setDebouncedQuery] = useState('');
  useRealtimeFileSync(true);
  const isSearchMode = debouncedQuery.trim().length > 0;

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

  const { data: documentsData, isLoading: listLoading } = useDocuments({ enabled: !isSearchMode });

  const { data: searchData, isLoading: searchLoading } = useQuery({
    queryKey: ['documents', 'search', debouncedQuery.trim()],
    queryFn: () =>
      apiClient.get<DocumentSearchResponse>('/documents/search', {
        query: debouncedQuery.trim(),
        limit: 100,
      }),
    enabled: isSearchMode,
  });

  const displayDocuments = useMemo(() => {
    if (!isSearchMode) {
      return (documentsData?.items ?? []).map((f): KnowledgeDoc => ({
        id: String(f.id),
        name: f.original_name,
        type: f.mime_type ?? f.file_type,
        size: f.size,
        url: `/api/v1/files/${f.id}`,
        createdAt: f.created_at,
      }));
    }
    return (searchData?.results ?? []).map(mapSearchResultToDocument);
  }, [isSearchMode, documentsData, searchData]);

  const listBusy = isSearchMode ? searchLoading : listLoading;

  const handleSearchDebounced = useCallback((value: string) => {
    setDebouncedQuery(value);
  }, []);

  const uploadDocument = useUploadDocument();

  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const handleFileSelect = async (files: FileList | null) => {
    if (!files || files.length === 0) return;

    setUploadProgress(0);
    try {
      for (const file of Array.from(files)) {
        await uploadDocument.mutateAsync({ file });
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
    if (type.startsWith('image/')) return Image;
    if (type.includes('pdf') || type.includes('document')) return FileText;
    return File;
  };

  const getFileTypeLabel = (type: string) => {
    if (type.startsWith('image/')) return t('knowledge.types.image');
    if (type.includes('pdf')) return 'PDF';
    if (type.includes('word') || type.includes('document')) return t('knowledge.types.document');
    if (type.includes('spreadsheet') || type.includes('excel')) return t('knowledge.types.spreadsheet');
    if (type.includes('text')) return t('knowledge.types.text');
    return t('knowledge.types.other');
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <PageShell
      title={t('knowledge.title')}
      description={t('knowledge.description')}
      actions={
        <>
          <SearchInput
            placeholder={t('knowledge.search')}
            value={search}
            onChange={(v) => setSearch(v)}
            onSearch={handleSearchDebounced}
            debounceMs={300}
            loading={isSearchMode && searchLoading}
            className="w-64"
          />
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(e) => handleFileSelect(e.target.files)}
            accept=".pdf,.doc,.docx,.txt,.md,.csv,.xlsx,.xls,.png,.jpg,.jpeg"
          />
          <Button onClick={() => fileInputRef.current?.click()} leftIcon={<Upload className="w-4 h-4" />}>
            {t('knowledge.upload')}
          </Button>
        </>
      }
    >
      <div className="grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <Card
              className={cn(
                'transition-colors',
                dragOver && 'ring-2 ring-primary-500 bg-primary-50 dark:bg-primary-900/20'
              )}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
            >
              <div className="p-4 border-b border-border">
                <div className="flex items-center justify-between">
                  <h2 className="text-2xl font-semibold text-foreground">
                    {t('knowledge.documents')}
                  </h2>
                  <span className="text-sm text-muted-foreground">
                    {displayDocuments.length} {t('knowledge.items')}
                  </span>
                </div>
              </div>

              {uploadProgress !== null && (
                <div className="px-4 py-3 border-b border-border">
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

              <CardContent padding="none">
                {listBusy ? (
                  <div className="flex items-center justify-center py-12">
                    <PageLoader message={t('common.loading')} />
                  </div>
                ) : displayDocuments.length > 0 ? (
                  <div className="divide-y divide-border">
                    {displayDocuments.map((doc) => {
                      const FileIcon = getFileIcon(doc.type);
                      const isSelected = selectedDocument?.id === doc.id;

                      return (
                        <div
                          key={doc.id}
                          className={cn(
                            'flex items-center gap-4 p-4 cursor-pointer transition-colors',
                            isSelected
                              ? 'bg-primary-50 dark:bg-primary-900/20'
                              : 'hover:bg-surface-sunken/80'
                          )}
                          onClick={() => {
                            setSelectedDocument(doc);
                            setPreviewOpen(true);
                          }}
                        >
                          <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-surface-sunken flex items-center justify-center">
                            <FileIcon className="w-5 h-5 text-muted-foreground" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="font-medium text-foreground truncate">
                              {doc.name}
                            </p>
                            <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                              {isSearchMode ? (
                                <span>{t('knowledge.searchMatch')}</span>
                              ) : (
                                <>
                                  <span>{formatFileSize(doc.size)}</span>
                                  <span>{formatRelativeTime(doc.createdAt)}</span>
                                </>
                              )}
                            </div>
                            {doc.preview && isSearchMode && (
                              <p className="mt-1 text-xs text-muted-foreground line-clamp-2">
                                {doc.preview}
                              </p>
                            )}
                          </div>
                          <Badge variant="default" size="sm">
                            {getFileTypeLabel(doc.type)}
                          </Badge>
                          <div className="flex items-center gap-1">
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
                                handleDelete(doc.id);
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
          </div>

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
                      <div className="min-w-0">
                        <p className="font-medium text-foreground truncate">
                          {selectedDocument.name}
                        </p>
                        <p className="text-sm text-muted-foreground">
                          {getFileTypeLabel(selectedDocument.type)}
                        </p>
                      </div>
                    </div>

                    <div className="flex-shrink-0 space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">{t('knowledge.size')}:</span>
                        <span className="text-foreground">
                          {formatFileSize(selectedDocument.size)}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">{t('knowledge.created')}:</span>
                        <span className="text-foreground">
                          {formatDate(selectedDocument.createdAt)}
                        </span>
                      </div>
                      {selectedDocument.chunks && (
                        <div className="flex justify-between">
                          <span className="text-muted-foreground">{t('knowledge.chunks')}:</span>
                          <span className="text-foreground">
                            {selectedDocument.chunks}
                          </span>
                        </div>
                      )}
                    </div>

                    {selectedDocument.preview && (
                      <div className="flex-shrink-0 p-3 rounded-lg bg-surface-sunken">
                        <p className="text-sm text-muted-foreground line-clamp-6">
                          {selectedDocument.preview}
                        </p>
                      </div>
                    )}

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
    </PageShell>
  );
}
