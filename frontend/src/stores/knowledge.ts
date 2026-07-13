import { create } from 'zustand';

export interface KnowledgeDocument {
  id: string;
  name: string;
  type: string;
  size: number;
  url: string;
  /** Extractive catalog blurb or search snippet shown in the list/preview. */
  preview?: string;
  summary?: string | null;
  status?: string;
  isIndexed?: boolean;
  chunks?: number;
  createdAt: string;
}

interface KnowledgeStore {
  search: string;
  setSearch: (search: string) => void;
  selectedDocument: KnowledgeDocument | null;
  setSelectedDocument: (doc: KnowledgeDocument | null) => void;
  isPreviewOpen: boolean;
  setPreviewOpen: (open: boolean) => void;
}

export const useKnowledgeStore = create<KnowledgeStore>((set) => ({
  search: '',
  setSearch: (search) => set({ search }),
  selectedDocument: null,
  setSelectedDocument: (selectedDocument) => set({ selectedDocument }),
  isPreviewOpen: false,
  setPreviewOpen: (isPreviewOpen) => set({ isPreviewOpen }),
}));
