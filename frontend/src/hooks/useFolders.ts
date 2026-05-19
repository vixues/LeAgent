import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/api/client';
import { emitRealtimeFileEvent } from './useRealtimeFileSync';

export interface FolderData {
  id: string;
  name: string;
  description?: string;
  icon?: string;
  color?: string;
  parent_id: string | null;
  position?: number;
  user_id?: string;
  file_count: number;
  flow_count: number;
  /** Code-project mode flag set via PATCH /folders/:id/project. */
  is_project?: boolean;
  /** Absolute on-disk path the coding agent / project_* tools operate on. */
  project_path?: string | null;
  /** Last time the backend re-validated `project_path`. */
  project_path_checked_at?: string | null;
}

export interface FolderFileItem {
  file_id: string;
  folder_id: string;
  file_name: string;
  file_type: string;
  size: number;
  mime_type?: string | null;
}

export interface FolderTreeNode {
  id: string;
  name: string;
  description?: string;
  icon?: string;
  color?: string;
  parent_id: string | null;
  position?: number;
  file_count: number;
  flow_count: number;
  is_project?: boolean;
  project_path?: string | null;
  children: FolderTreeNode[];
}

export interface CreateFolderInput {
  name: string;
  description?: string;
  icon?: string;
  color?: string;
  parent_id?: string | null;
}

interface PaginatedFolders {
  items: FolderData[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
  has_prev: boolean;
}

export function useFolderList(parentId?: string | null, scopeKey?: string | null) {
  return useQuery({
    queryKey: ['folders', 'list', parentId, scopeKey ?? 'global'],
    queryFn: async () => {
      const res = await apiClient.get<PaginatedFolders>('/folders', {
        parent_id: parentId ?? undefined,
        page_size: 200,
      } as Record<string, string | number | boolean | undefined>);
      return res.items;
    },
  });
}

export function useFolderTree() {
  return useQuery({
    queryKey: ['folders', 'tree'],
    queryFn: async () => {
      const tree = await apiClient.get<FolderTreeNode[]>('/folders/tree');
      return Array.isArray(tree) ? tree : [];
    },
  });
}

export function useFolderDetail(folderId: string | null) {
  return useQuery({
    queryKey: ['folders', 'detail', folderId],
    queryFn: () => apiClient.get<FolderData>(`/folders/${folderId}`),
    enabled: !!folderId,
  });
}

export function useFolderItems(
  folderId: string | null,
  scopeKey?: string | null,
  queryEnabled: boolean = true,
) {
  return useQuery({
    queryKey: ['folders', 'items', folderId, scopeKey ?? 'global'],
    queryFn: () =>
      apiClient.get<FolderFileItem[]>('/folder-items', {
        folder_id: folderId!,
      } as Record<string, string | number | boolean | undefined>),
    enabled: Boolean(folderId) && queryEnabled,
  });
}

export function useCreateFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateFolderInput) =>
      apiClient.post<FolderData>('/folders', data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['folders'] });
    },
  });
}

export function useUpdateFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...data }: { id: string } & Partial<CreateFolderInput & { position: number }>) =>
      apiClient.put<FolderData>(`/folders/${id}`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['folders'] });
    },
  });
}

export function useDeleteFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, recursive = false }: { id: string; recursive?: boolean }) =>
      apiClient.delete(`/folders/${id}?recursive=${recursive}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['folders'] });
    },
  });
}

export function useMoveFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, parent_id }: { id: string; parent_id: string | null }) =>
      apiClient.put<FolderData>(`/folders/${id}`, { parent_id }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['folders'] });
    },
  });
}

export function useUploadFileToFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ file, folderId }: { file: File; folderId: string }) => {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('folder_id', folderId);
      return apiClient.upload('/files/upload', formData);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['folders'] });
      emitRealtimeFileEvent('uploaded');
    },
  });
}

export function useRemoveFileFromFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ folderId, fileId }: { folderId: string; fileId: string }) =>
      apiClient.delete(`/folder-items/${folderId}/${fileId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['folders'] });
      emitRealtimeFileEvent('deleted');
    },
  });
}

export function useMoveFileToFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ fileId, toFolderId }: { fileId: string; toFolderId: string }) =>
      apiClient.put(`/folder-items/${fileId}/move`, { to_folder_id: toFolderId }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['folders'] });
      emitRealtimeFileEvent('updated');
    },
  });
}
