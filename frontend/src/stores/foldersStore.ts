import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { apiClient } from '@/api/client';

export interface Folder {
  id: string;
  name: string;
  parent_id: string | null;
  description?: string;
  color?: string;
  icon?: string;
  position?: number;
  file_count: number;
  flow_count: number;
}

export interface FolderTreeNode extends Folder {
  children: FolderTreeNode[];
  isExpanded?: boolean;
}

interface PaginatedFolders {
  items: Folder[];
  total: number;
  page: number;
  page_size: number;
}

interface FoldersState {
  folders: Folder[];
  expandedFolderIds: Set<string>;
  selectedFolderId: string | null;
  isLoading: boolean;
  error: string | null;

  fetchFolders: () => Promise<void>;
  createFolder: (data: { name: string; description?: string; icon?: string; color?: string; parent_id?: string | null }) => Promise<Folder>;
  updateFolder: (id: string, updates: Partial<{ name: string; description: string; icon: string; color: string; parent_id: string | null; position: number }>) => Promise<void>;
  deleteFolder: (id: string, recursive?: boolean) => Promise<void>;
  moveFolder: (id: string, newParentId: string | null) => Promise<void>;

  getFolderTree: () => FolderTreeNode[];
  getFolder: (id: string) => Folder | undefined;
  getFolderPath: (id: string) => Folder[];
  getFolderChildren: (parentId: string | null) => Folder[];

  expandFolder: (id: string) => void;
  collapseFolder: (id: string) => void;
  toggleFolder: (id: string) => void;
  expandAll: () => void;
  collapseAll: () => void;

  selectFolder: (id: string | null) => void;

  searchFolders: (query: string) => Folder[];
}

export const useFoldersStore = create<FoldersState>()(
  persist(
    (set, get) => ({
      folders: [],
      expandedFolderIds: new Set<string>(),
      selectedFolderId: null,
      isLoading: false,
      error: null,

      fetchFolders: async () => {
        set({ isLoading: true, error: null });
        try {
          const res = await apiClient.get<PaginatedFolders>('/folders', { page_size: 200 });
          set({ folders: res.items, isLoading: false });
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Failed to fetch folders';
          set({ error: message, isLoading: false });
        }
      },

      createFolder: async (folderData) => {
        set({ isLoading: true, error: null });
        try {
          const folder = await apiClient.post<Folder>('/folders', folderData);
          set((state) => ({
            folders: [...state.folders, folder],
            isLoading: false,
          }));
          return folder;
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Failed to create folder';
          set({ error: message, isLoading: false });
          throw err;
        }
      },

      updateFolder: async (id, updates) => {
        set({ isLoading: true, error: null });
        try {
          const folder = await apiClient.put<Folder>(`/folders/${id}`, updates);
          set((state) => ({
            folders: state.folders.map((f) => (f.id === id ? folder : f)),
            isLoading: false,
          }));
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Failed to update folder';
          set({ error: message, isLoading: false });
          throw err;
        }
      },

      deleteFolder: async (id, recursive = false) => {
        set({ isLoading: true, error: null });
        try {
          await apiClient.delete(`/folders/${id}?recursive=${recursive}`);
          set((state) => {
            const idsToDelete = new Set<string>();
            const collectIds = (folderId: string) => {
              idsToDelete.add(folderId);
              state.folders
                .filter((f) => f.parent_id === folderId)
                .forEach((f) => collectIds(f.id));
            };
            collectIds(id);

            return {
              folders: state.folders.filter((f) => !idsToDelete.has(f.id)),
              selectedFolderId:
                state.selectedFolderId && idsToDelete.has(state.selectedFolderId)
                  ? null
                  : state.selectedFolderId,
              isLoading: false,
            };
          });
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Failed to delete folder';
          set({ error: message, isLoading: false });
          throw err;
        }
      },

      moveFolder: async (id, newParentId) => {
        const isDescendant = (parentId: string, childId: string): boolean => {
          const child = get().folders.find((f) => f.id === childId);
          if (!child?.parent_id) return false;
          if (child.parent_id === parentId) return true;
          return isDescendant(parentId, child.parent_id);
        };

        if (newParentId && (newParentId === id || isDescendant(id, newParentId))) {
          throw new Error('Cannot move folder into its own descendant');
        }

        set({ isLoading: true, error: null });
        try {
          const folder = await apiClient.put<Folder>(`/folders/${id}`, { parent_id: newParentId });
          set((state) => ({
            folders: state.folders.map((f) => (f.id === id ? folder : f)),
            isLoading: false,
          }));
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Failed to move folder';
          set({ error: message, isLoading: false });
          throw err;
        }
      },

      getFolderTree: () => {
        const { folders, expandedFolderIds } = get();

        const buildTree = (parentId: string | null): FolderTreeNode[] => {
          return folders
            .filter((f) => f.parent_id === parentId)
            .map((folder) => ({
              ...folder,
              children: buildTree(folder.id),
              isExpanded: expandedFolderIds.has(folder.id),
            }))
            .sort((a, b) => (a.position ?? 0) - (b.position ?? 0) || a.name.localeCompare(b.name));
        };

        return buildTree(null);
      },

      getFolder: (id) => get().folders.find((f) => f.id === id),

      getFolderPath: (id) => {
        const path: Folder[] = [];
        let current = get().folders.find((f) => f.id === id);

        while (current) {
          path.unshift(current);
          current = current.parent_id
            ? get().folders.find((f) => f.id === current!.parent_id)
            : undefined;
        }

        return path;
      },

      getFolderChildren: (parentId) =>
        get().folders.filter((f) => f.parent_id === parentId),

      expandFolder: (id) =>
        set((state) => ({
          expandedFolderIds: new Set([...state.expandedFolderIds, id]),
        })),

      collapseFolder: (id) =>
        set((state) => {
          const newSet = new Set(state.expandedFolderIds);
          newSet.delete(id);
          return { expandedFolderIds: newSet };
        }),

      toggleFolder: (id) => {
        const { expandedFolderIds } = get();
        if (expandedFolderIds.has(id)) {
          get().collapseFolder(id);
        } else {
          get().expandFolder(id);
        }
      },

      expandAll: () =>
        set((state) => ({
          expandedFolderIds: new Set(state.folders.map((f) => f.id)),
        })),

      collapseAll: () => set({ expandedFolderIds: new Set() }),

      selectFolder: (id) => set({ selectedFolderId: id }),

      searchFolders: (query) => {
        const lowerQuery = query.toLowerCase();
        return get().folders.filter(
          (f) =>
            f.name.toLowerCase().includes(lowerQuery) ||
            f.description?.toLowerCase().includes(lowerQuery)
        );
      },
    }),
    {
      name: 'leagent-folders',
      partialize: (state) => ({
        expandedFolderIds: Array.from(state.expandedFolderIds),
        selectedFolderId: state.selectedFolderId,
      }),
      merge: (persisted, current) => ({
        ...current,
        ...(persisted as object),
        expandedFolderIds: new Set((persisted as { expandedFolderIds?: string[] })?.expandedFolderIds || []),
      }),
    }
  )
);
