import type { Message } from '@/types/chat';

/** A single row currently inside the mounted window. */
export interface VirtualItem {
  index: number;
  id: string;
  /** Absolute pixel offset from the top of the virtual spacer. */
  top: number;
  message: Message;
}

export interface VirtualRange {
  start: number;
  end: number;
}
