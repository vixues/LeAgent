import { create } from 'zustand';

/**
 * Tracks the in-flight connection drag so nodes can dim themselves when they
 * have no compatible slot (ComfyUI's link-drag affordance).
 */
interface ConnectionDragState {
  /** Wire type of the dangling end, or null when not dragging. */
  type: string | null;
  /** 'out' = dragging from an output (looking for inputs), 'in' = reverse. */
  direction: 'out' | 'in' | null;
  start: (type: string, direction: 'out' | 'in') => void;
  clear: () => void;
}

export const useConnectionDrag = create<ConnectionDragState>((set) => ({
  type: null,
  direction: null,
  start: (type, direction) => set({ type, direction }),
  clear: () => set({ type: null, direction: null }),
}));
