import { type ReactNode } from 'react';
import type { Message } from '@/types/chat';
import type { VirtualItem } from './types';

interface VirtualConversationListProps {
  items: VirtualItem[];
  totalHeight: number;
  registerRow: (id: string) => (el: HTMLElement | null) => void;
  renderRow: (message: Message, index: number) => ReactNode;
}

/**
 * Dumb windowed renderer. The engine (`useConversationVirtualizer`) owns range,
 * heights, and offsets; this component only mounts the rows it is handed and
 * positions them absolutely inside a full-height spacer. Each row keeps the
 * centered reading column (`max-w-[72ch] pl-20 pr-6`) and a bottom gap (`pb-8`)
 * so measured heights include inter-row spacing.
 */
export function VirtualConversationList({
  items,
  totalHeight,
  registerRow,
  renderRow,
}: VirtualConversationListProps) {
  return (
    <div style={{ position: 'relative', width: '100%', height: totalHeight }}>
      {items.map((item) => (
        <div
          key={item.id}
          ref={registerRow(item.id)}
          data-message-id={item.id}
          style={{ position: 'absolute', top: item.top, left: 0, right: 0 }}
        >
          <div className="mx-auto w-full max-w-[72ch] pl-20 pr-6 pb-8">
            {renderRow(item.message, item.index)}
          </div>
        </div>
      ))}
    </div>
  );
}
