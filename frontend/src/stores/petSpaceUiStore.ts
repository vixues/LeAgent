import { create } from 'zustand';

/**
 * UI-only state for Pet Space. While the page is mounted, `dockPreviewProjectId`
 * drives the global dock / shared pet previews so they match the selected library.
 */
type PetSpaceUiState = {
  dockPreviewProjectId: string | null;
  setDockPreviewProjectId: (id: string | null) => void;
};

export const usePetSpaceUiStore = create<PetSpaceUiState>((set) => ({
  dockPreviewProjectId: null,
  setDockPreviewProjectId: (id) => set({ dockPreviewProjectId: id }),
}));
