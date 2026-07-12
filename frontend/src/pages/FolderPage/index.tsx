import { useState, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  RefreshCw,
  FolderPlus,
  PanelLeft,
  Sparkles,
} from 'lucide-react';
import {
  Button,
  Card,
  Modal,
  ModalHeader,
  Sheet,
  SheetContent,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui';
import { PageShell } from '@/components/layout/PageShell';
import {
  useFolderTree,
  useFolderItems,
  useFolderDetail,
  useCreateFolder,
  useDeleteFolder,
  useUpdateFolder,
  useUploadFileToFolder,
  useRemoveFileFromFolder,
  type FolderTreeNode,
  type FolderFileItem,
} from '@/hooks/useFolders';
import {
  useCodingProjectTemplates,
  useScaffoldFolderProject,
} from '@/hooks/useFolderProjectRuntime';
import { CreateCodingProjectModal } from '@/pages/CodingProjects/CreateCodingProjectModal';
import { useFoldersStore } from '@/stores/foldersStore';
import { useChatDraftStore } from '@/stores/chatDraft';
import { useRealtimeFileSync } from '@/hooks/useRealtimeFileSync';
import FolderTreeView from './components/FolderTreeView';
import FolderBreadcrumb, { type BreadcrumbItem } from './components/FolderBreadcrumb';
import FileListView from './components/FileListView';
import FilePreviewPanel from './components/FilePreviewPanel';
import FolderContextMenu from './components/FolderContextMenu';
import ProjectModeBadge from './project/ProjectModeBadge';
import ProjectPanel from './project/ProjectPanel';
import FolderProjectRunPanel from './project/FolderProjectRunPanel';

/**
 * FolderPage — redesigned to match the app's design system.
 *
 * Old layout was an edge-to-edge 3-pane explorer with `-m-6` negative margins
 * and custom `rgb(var(--color-surface-base))` colors that didn't look like any
 * other page. The new layout is a standard two-column page:
 *
 *   ┌────── PageShell header ──────┐
 *   │  Folders  [New subfolder] [⟲] │
 *   ├───────────┬───────────────────┤
 *   │ Card:tree │ Card: breadcrumb  │
 *   │ (sticky)  │        + files    │
 *   └───────────┴───────────────────┘
 *
 * - Preview moves into a <Modal/> so the file grid stays full-width.
 * - On < lg, the tree collapses into a <Sheet/> triggered from the header.
 */
export default function FolderPage() {
  const { t } = useTranslation();
  const { selectedFolderId, selectFolder, fetchFolders, getFolderPath } =
    useFoldersStore();

  const { data: treeData, refetch: refetchTree } = useFolderTree();
  const {
    data: items,
    isLoading: itemsLoading,
    refetch: refetchItems,
  } = useFolderItems(selectedFolderId);
  const { data: folderDetail } = useFolderDetail(selectedFolderId);

  const createFolder = useCreateFolder();
  const deleteFolder = useDeleteFolder();
  const updateFolder = useUpdateFolder();
  const uploadFile = useUploadFileToFolder();
  const removeFile = useRemoveFileFromFolder();
  const scaffoldProject = useScaffoldFolderProject();
  const { data: templates = [] } = useCodingProjectTemplates();

  const [scaffoldOpen, setScaffoldOpen] = useState(false);
  const [scaffoldName, setScaffoldName] = useState('');
  const [scaffoldDesc, setScaffoldDesc] = useState('');
  const [scaffoldTemplate, setScaffoldTemplate] = useState('');

  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const setFolderContext = useChatDraftStore((s) => s.setFolderContext);

  const [previewFile, setPreviewFile] = useState<FolderFileItem | null>(null);
  const [mobileTreeOpen, setMobileTreeOpen] = useState(false);
  const [contextMenu, setContextMenu] = useState<{
    x: number;
    y: number;
    folderId: string;
  } | null>(null);
  useRealtimeFileSync(true);

  useEffect(() => {
    fetchFolders();
  }, [fetchFolders]);

  useEffect(() => {
    const folderFromUrl = searchParams.get('folder');
    if (folderFromUrl && folderFromUrl !== selectedFolderId) {
      selectFolder(folderFromUrl);
    }
  }, [searchParams, selectFolder, selectedFolderId]);

  const tree: FolderTreeNode[] = treeData ?? [];
  const fileList = items ?? [];

  const breadcrumb: BreadcrumbItem[] = selectedFolderId
    ? getFolderPath(selectedFolderId).map((f) => ({ id: f.id, name: f.name }))
    : [];

  const handleCreateFolder = useCallback(
    async (parentId: string | null) => {
      const name = window.prompt(t('folders.newFolderPrompt'));
      if (!name?.trim()) return;
      await createFolder.mutateAsync({ name: name.trim(), parent_id: parentId });
      refetchTree();
      fetchFolders();
    },
    [createFolder, refetchTree, fetchFolders, t]
  );

  const handleRenameFolder = useCallback(
    async (folderId: string) => {
      const name = window.prompt(t('folders.newFolderPrompt'));
      if (!name?.trim()) return;
      await updateFolder.mutateAsync({ id: folderId, name: name.trim() });
      refetchTree();
      fetchFolders();
    },
    [updateFolder, refetchTree, fetchFolders, t],
  );

  const handleDeleteFolder = useCallback(
    async (folderId: string) => {
      if (
        !window.confirm(
          t('folders.deleteConfirm')
        )
      )
        return;
      await deleteFolder.mutateAsync({ id: folderId, recursive: true });
      if (selectedFolderId === folderId) selectFolder(null);
      refetchTree();
      fetchFolders();
    },
    [deleteFolder, selectedFolderId, selectFolder, refetchTree, fetchFolders, t]
  );

  const handleUpload = useCallback(
    async (files: FileList) => {
      if (!selectedFolderId) {
        window.alert(t('folders.selectFolderFirst'));
        return;
      }
      for (const file of Array.from(files)) {
        await uploadFile.mutateAsync({ file, folderId: selectedFolderId });
      }
      refetchItems();
    },
    [selectedFolderId, uploadFile, refetchItems, t]
  );

  const handleRemoveFile = useCallback(
    async (fileId: string) => {
      if (!selectedFolderId) return;
      await removeFile.mutateAsync({ folderId: selectedFolderId, fileId });
      setPreviewFile(null);
      refetchItems();
    },
    [selectedFolderId, removeFile, refetchItems]
  );

  const handleRefresh = useCallback(() => {
    refetchTree();
    refetchItems();
    fetchFolders();
  }, [refetchTree, refetchItems, fetchFolders]);

  const handleSelectFolder = useCallback(
    (id: string | null) => {
      selectFolder(id);
      setMobileTreeOpen(false);
    },
    [selectFolder]
  );

  const treeView = (
    <FolderTreeView
      tree={tree}
      selectedId={selectedFolderId}
      onSelect={handleSelectFolder}
      onContextMenu={(e, folderId) => {
        e.preventDefault();
        setContextMenu({ x: e.clientX, y: e.clientY, folderId });
      }}
      onCreateFolder={handleCreateFolder}
    />
  );

  return (
    <PageShell
      title={t('folders.title')}
      description={t('folders.description')}
      contentClassName="flex min-h-0 flex-1 flex-col"
      actions={
        <>
          {/* Mobile-only trigger that opens the tree in a Sheet */}
          <Button
            variant="ghost"
            size="sm"
            className="lg:hidden"
            onClick={() => setMobileTreeOpen(true)}
            leftIcon={<PanelLeft className="w-4 h-4" />}
          >
            {t('folders.showTree')}
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => handleCreateFolder(selectedFolderId)}
            leftIcon={<FolderPlus className="w-4 h-4" />}
          >
            {selectedFolderId
              ? t('folders.newSubfolder')
              : t('folders.newFolder')}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={handleRefresh}
            aria-label={t('common.refresh')}
          >
            <RefreshCw className="w-4 h-4" />
          </Button>
        </>
      }
    >
      {/*
        Grid: fixed 280px sidebar on large screens, single column below.
        flex-1 + grid-rows fr fills the WorkPanel scrollport (matches CodingProjectsPage).
      */}
      <div className="grid min-h-0 flex-1 grid-cols-1 grid-rows-[minmax(0,1fr)] gap-6 lg:grid-cols-[280px_1fr]">
        {/* Sidebar — hidden on mobile (use Sheet instead) */}
        <Card
          padding="none"
          className="hidden min-h-0 overflow-hidden lg:flex lg:flex-col"
        >
          {treeView}
        </Card>

        {/* Main column */}
        <Card
          padding="none"
          className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden"
        >
          {/* Breadcrumb strip */}
          <div className="flex items-center gap-3 px-4 sm:px-5 h-12 border-b border-border">
            <FolderBreadcrumb items={breadcrumb} onNavigate={handleSelectFolder} />
          </div>

          {/*
            Body: when project mode is on, expose Files / Code / Git / Run
            tabs in the folder-detail strip (same row as name/stats).
            Otherwise render the detail strip + full-width file list.
          */}
          {selectedFolderId && folderDetail?.is_project ? (
            <Tabs defaultValue="code" className="flex min-h-0 flex-1 flex-col">
              <div className="flex flex-wrap items-center gap-3 px-4 sm:px-5 py-2 border-b border-border bg-surface-sunken/40 text-xs text-muted-foreground">
                <span className="flex items-center gap-1.5">
                  <span aria-hidden>{folderDetail.icon ?? '📁'}</span>
                  <strong className="font-medium text-foreground">
                    {folderDetail.name}
                  </strong>
                </span>
                {folderDetail.description && (
                  <span className="min-w-0 truncate">{folderDetail.description}</span>
                )}
                <TabsList className="shrink-0 p-0.5">
                  <TabsTrigger value="files" className="px-2.5 py-1 text-xs">
                    {t('folders.project.filesTab', { defaultValue: 'Files' })}
                  </TabsTrigger>
                  <TabsTrigger value="code" className="px-2.5 py-1 text-xs">
                    {t('folders.project.codeTab', { defaultValue: 'Code' })}
                  </TabsTrigger>
                  <TabsTrigger value="git" className="px-2.5 py-1 text-xs">
                    {t('folders.project.gitTab', { defaultValue: 'Git' })}
                  </TabsTrigger>
                  <TabsTrigger value="run" className="px-2.5 py-1 text-xs">
                    {t('folders.project.runTab', { defaultValue: 'Run' })}
                  </TabsTrigger>
                </TabsList>
                <div className="ml-auto flex flex-wrap items-center gap-3">
                  <span>
                    {folderDetail.file_count}{' '}
                    {folderDetail.file_count === 1 ? 'file' : 'files'}
                  </span>
                  <span>
                    {folderDetail.flow_count}{' '}
                    {folderDetail.flow_count === 1 ? 'flow' : 'flows'}
                  </span>
                  <ProjectModeBadge
                    folderId={selectedFolderId}
                    isProject
                    projectPath={folderDetail.project_path ?? null}
                  />
                  {folderDetail.file_count > 0 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-xs"
                      onClick={() => {
                        setFolderContext(selectedFolderId, folderDetail.name);
                        navigate('/');
                      }}
                      leftIcon={<Sparkles className="w-3 h-3" />}
                    >
                      {t('folders.analyzeInChat', { defaultValue: 'Analyze in chat' })}
                    </Button>
                  )}
                </div>
              </div>
              <TabsContent value="files" className="flex min-h-0 flex-1 flex-col">
                <FileListView
                  files={fileList}
                  isLoading={itemsLoading}
                  onPreview={setPreviewFile}
                  onRemove={handleRemoveFile}
                  onUpload={handleUpload}
                />
              </TabsContent>
              <TabsContent value="code" className="flex min-h-0 flex-1 flex-col">
                <ProjectPanel
                  folderId={selectedFolderId}
                  folderName={folderDetail.name}
                  projectPath={folderDetail.project_path ?? null}
                  mode="code"
                />
              </TabsContent>
              <TabsContent value="git" className="flex min-h-0 flex-1 flex-col">
                <ProjectPanel
                  folderId={selectedFolderId}
                  folderName={folderDetail.name}
                  projectPath={folderDetail.project_path ?? null}
                  mode="git"
                />
              </TabsContent>
              <TabsContent value="run" className="flex min-h-0 flex-1 flex-col">
                <FolderProjectRunPanel
                  folderId={selectedFolderId}
                  folderName={folderDetail.name}
                />
              </TabsContent>
            </Tabs>
          ) : (
            <>
              {folderDetail && (
                <div className="flex flex-wrap items-center gap-3 px-4 sm:px-5 py-2 border-b border-border bg-surface-sunken/40 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1.5">
                    <span aria-hidden>{folderDetail.icon ?? '📁'}</span>
                    <strong className="font-medium text-foreground">
                      {folderDetail.name}
                    </strong>
                  </span>
                  {folderDetail.description && (
                    <span className="min-w-0 truncate">{folderDetail.description}</span>
                  )}
                  <div className="ml-auto flex flex-wrap items-center gap-3">
                    <span>
                      {folderDetail.file_count}{' '}
                      {folderDetail.file_count === 1 ? 'file' : 'files'}
                    </span>
                    <span>
                      {folderDetail.flow_count}{' '}
                      {folderDetail.flow_count === 1 ? 'flow' : 'flows'}
                    </span>
                    {selectedFolderId && (
                      <ProjectModeBadge
                        folderId={selectedFolderId}
                        isProject={Boolean(folderDetail.is_project)}
                        projectPath={folderDetail.project_path ?? null}
                      />
                    )}
                    {selectedFolderId && folderDetail.file_count > 0 && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-xs"
                        onClick={() => {
                          setFolderContext(selectedFolderId, folderDetail.name);
                          navigate('/');
                        }}
                        leftIcon={<Sparkles className="w-3 h-3" />}
                      >
                        {t('folders.analyzeInChat', { defaultValue: 'Analyze in chat' })}
                      </Button>
                    )}
                  </div>
                </div>
              )}
              <FileListView
                files={fileList}
                isLoading={itemsLoading}
                onPreview={setPreviewFile}
                onRemove={handleRemoveFile}
                onUpload={handleUpload}
              />
            </>
          )}
        </Card>
      </div>

      {/* Mobile tree sheet */}
      <Sheet open={mobileTreeOpen} onOpenChange={setMobileTreeOpen} side="left">
        <SheetContent className="p-0">
          <div className="h-full flex flex-col">{treeView}</div>
        </SheetContent>
      </Sheet>

      {/* File preview dialog — replaces the old inline right-side panel */}
      <Modal
        isOpen={Boolean(previewFile)}
        onClose={() => setPreviewFile(null)}
        size="md"
      >
        <ModalHeader onClose={() => setPreviewFile(null)}>
          {t('folders.preview')}
        </ModalHeader>
        {previewFile && (
          <FilePreviewPanel
            file={previewFile}
            onClose={() => setPreviewFile(null)}
            onRemove={handleRemoveFile}
          />
        )}
      </Modal>

      {/* Right-click menu */}
      {contextMenu && (
        <FolderContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          folderId={contextMenu.folderId}
          onClose={() => setContextMenu(null)}
          onNewSubfolder={handleCreateFolder}
          onRename={() => contextMenu && handleRenameFolder(contextMenu.folderId)}
          onDelete={handleDeleteFolder}
        />
      )}

      {selectedFolderId && (
        <CreateCodingProjectModal
          open={scaffoldOpen}
          onClose={() => setScaffoldOpen(false)}
          templates={templates}
          name={scaffoldName}
          onNameChange={setScaffoldName}
          description={scaffoldDesc}
          onDescriptionChange={setScaffoldDesc}
          template={scaffoldTemplate}
          onTemplateChange={setScaffoldTemplate}
          isSubmitting={scaffoldProject.isPending}
          onSubmit={async () => {
            if (!selectedFolderId) return;
            await scaffoldProject.mutateAsync({
              folderId: selectedFolderId,
              name: scaffoldName.trim(),
              template: scaffoldTemplate,
              description: scaffoldDesc.trim() || undefined,
            });
            setScaffoldOpen(false);
            refetchTree();
            fetchFolders();
          }}
        />
      )}
    </PageShell>
  );
}
