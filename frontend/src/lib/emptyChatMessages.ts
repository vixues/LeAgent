import type { Message } from '@/types/chat';

/** Stable reference for Zustand selectors — avoid `?? []` creating a new array every subscribe. */
export const EMPTY_MESSAGE_LIST: Message[] = [];
