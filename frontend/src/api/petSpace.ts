import { apiClient } from '@/api/client';

export interface PetProject {
  id: string;
  user_id: string;
  workspace_id: string | null;
  name: string;
  description: string | null;
  settings?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PetProjectFileRow {
  id: string;
  pet_project_id: string;
  file_id: string;
  original_name: string;
  mime_type: string | null;
  size: number;
  created_at: string;
}

export interface FileUploadResponse {
  id: string;
  name: string;
  original_name: string;
  file_type: string;
  mime_type: string | null;
  size: number;
  checksum: string;
}

export interface DefaultPetPersonalityResponse {
  document: string;
}

export const petSpaceApi = {
  getDefaultPersonality: () =>
    apiClient.get<DefaultPetPersonalityResponse>('/pet-space/personality/default'),

  listProjects: () => apiClient.get<PetProject[]>('/pet-space/projects'),

  createProject: (body: { name: string; description?: string | null }) =>
    apiClient.post<PetProject>('/pet-space/projects', body),

  updateProject: (
    id: string,
    body: { name?: string; description?: string | null; settings?: string | null },
  ) => apiClient.patch<PetProject>(`/pet-space/projects/${id}`, body),

  deleteProject: (id: string) => apiClient.delete<void>(`/pet-space/projects/${id}`),

  listFiles: (projectId: string) =>
    apiClient.get<PetProjectFileRow[]>(`/pet-space/projects/${projectId}/files`),

  uploadFile: (projectId: string, file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return apiClient.upload<FileUploadResponse>(`/pet-space/projects/${projectId}/upload`, fd);
  },

  /** Soft-deletes the stored file; pet project list APIs omit deleted files. */
  deleteFile: (fileId: string) => apiClient.delete<void>(`/files/${fileId}`),
};
