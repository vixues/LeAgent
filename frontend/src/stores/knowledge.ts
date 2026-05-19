import { create } from 'zustand';

interface Document {
  id: string;
  name: string;
  type: string;
  size: number;
  url: string;
  preview?: string;
  chunks?: number;
  createdAt: string;
}

interface KnowledgeStore {
  search: string;
  setSearch: (search: string) => void;
  selectedDocument: Document | null;
  setSelectedDocument: (doc: Document | null) => void;
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
