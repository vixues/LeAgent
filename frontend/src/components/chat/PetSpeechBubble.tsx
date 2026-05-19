import { memo } from 'react';
import { cn } from '@/lib/utils';

export type PetSpeechBubbleLayout = 'above-left' | 'below-right';

export interface PetSpeechBubbleProps {
  text: string;
  emoji?: string;
  className?: string;
  /**
   * `above-left` — above the pet; pair with `absolute bottom-full right-0` on the parent so the
   * bubble grows leftward and avoids covering the message body; tail points down (default).
   * `below-right` — under the pet, right-aligned; tail points up.
   */
  layout?: PetSpeechBubbleLayout;
}

/**
 * Short caption by the assistant pet (SSE `pet_bubble`, click greeting, or extensions.pet_bubble).
 */
export const PetSpeechBubble = memo(function PetSpeechBubble({
  text,
  emoji,
  className,
  layout = 'above-left',
}: PetSpeechBubbleProps) {
  return (
    <div
      className={cn(
        'chat-pet-speech-bubble isolate pointer-events-none z-[2] max-w-[min(11rem,calc(100vw-2rem))] rounded-xl border border-border/60 bg-background/70 px-2 py-1.5 text-[11px] leading-[1.35] text-foreground shadow-sm ring-1 ring-border/20 backdrop-blur-md dark:bg-background/60',
        layout === 'below-right' && 'chat-pet-speech-bubble--layout-below-right',
        layout === 'above-left' && 'chat-pet-speech-bubble--layout-above-left',
        className,
      )}
      aria-live="polite"
      aria-relevant="additions text"
    >
      {emoji ? (
        <span className="mb-px block text-sm leading-none select-none" aria-hidden>
          {emoji}
        </span>
      ) : null}
      <p className="m-0 whitespace-pre-wrap break-words leading-snug">{text}</p>
    </div>
  );
});
