import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { BrandMascot } from '@/components/brand/BrandMascot';
import { usePetAppearancePreview } from '@/hooks/usePetAppearancePreview';
import type { PetBehaviorVisual } from '@/lib/petBehaviorVisual';

export type ChatAgentRolePetVariant = 'rail' | 'inline';

export interface ChatAgentRolePetProps {
  /** `rail` — left column beside prose; `inline` — tiny mark (e.g. compact rows). */
  variant?: ChatAgentRolePetVariant;
  /** Fired after single-click debounce (alongside happy animation when motion is allowed). */
  onShowGreeting?: () => void;
}

const CHAT_PET_CLICK_DELAY_MS = 300;
const CHAT_PET_HAPPY_MS = 1200;
const CHAT_PET_JUMP_MS = 700;

/**
 * Assistant-turn pet — same preview source as the dock / empty state (`usePetAppearancePreview`).
 */
export const ChatAgentRolePet = memo(function ChatAgentRolePet({
  variant = 'rail',
  onShowGreeting,
}: ChatAgentRolePetProps) {
  const [interactionOverride, setInteractionOverride] = useState<PetBehaviorVisual | null>(null);
  const singleClickTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const happyEndTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const jumpEndTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearReactionTimers = useCallback(() => {
    if (singleClickTimer.current) {
      clearTimeout(singleClickTimer.current);
      singleClickTimer.current = null;
    }
    if (happyEndTimer.current) {
      clearTimeout(happyEndTimer.current);
      happyEndTimer.current = null;
    }
    if (jumpEndTimer.current) {
      clearTimeout(jumpEndTimer.current);
      jumpEndTimer.current = null;
    }
  }, []);

  useEffect(() => () => clearReactionTimers(), [clearReactionTimers]);

  const {
    previewUrl,
    motionClass,
    motionStyle,
    previewShellClass,
    reduceMotion,
    clipMirror,
    clipObjectFit,
    appearanceLoading,
  } = usePetAppearancePreview({ overrideVisual: interactionOverride });
  const objectFit = clipObjectFit === 'cover' ? 'object-cover' : 'object-contain';

  const handlePetClick = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      if (singleClickTimer.current) {
        clearTimeout(singleClickTimer.current);
        singleClickTimer.current = null;
      }
      singleClickTimer.current = setTimeout(() => {
        singleClickTimer.current = null;
        onShowGreeting?.();
        if (reduceMotion) return;
        setInteractionOverride('happy');
        happyEndTimer.current = setTimeout(() => {
          happyEndTimer.current = null;
          setInteractionOverride(null);
        }, CHAT_PET_HAPPY_MS);
      }, CHAT_PET_CLICK_DELAY_MS);
    },
    [reduceMotion, onShowGreeting],
  );

  const handlePetDoubleClick = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      if (reduceMotion) return;
      if (singleClickTimer.current) {
        clearTimeout(singleClickTimer.current);
        singleClickTimer.current = null;
      }
      if (happyEndTimer.current) {
        clearTimeout(happyEndTimer.current);
        happyEndTimer.current = null;
      }
      if (jumpEndTimer.current) {
        clearTimeout(jumpEndTimer.current);
        jumpEndTimer.current = null;
      }
      setInteractionOverride('jump');
      jumpEndTimer.current = setTimeout(() => {
        jumpEndTimer.current = null;
        setInteractionOverride(null);
      }, CHAT_PET_JUMP_MS);
    },
    [reduceMotion],
  );

  const wrapClass =
    variant === 'rail'
      ? /* Outer box > image so scale/translate motion is not clipped (see `.pet-motion` in chat.css). */
        'inline-flex size-20 flex-shrink-0 items-center justify-center overflow-visible'
      : 'inline-flex h-5 w-5 flex-shrink-0 items-center justify-center overflow-hidden';

  return (
    <span
      className={cn(wrapClass, previewUrl && previewShellClass)}
      aria-hidden
      onClick={handlePetClick}
      onDoubleClick={handlePetDoubleClick}
    >
      {previewUrl ? (
        clipMirror ? (
          <span
            className={cn('inline-block scale-x-[-1]', variant === 'rail' && 'h-[3.375rem] w-[3.375rem]')}
          >
            <img
              src={previewUrl}
              alt=""
              className={cn(
                variant === 'rail' ? 'h-[3.375rem] w-[3.375rem]' : 'h-full w-full',
                objectFit,
                variant === 'rail' ? 'rounded-lg' : 'rounded-[3px]',
                motionClass,
              )}
              style={motionStyle}
            />
          </span>
        ) : (
          <img
            src={previewUrl}
            alt=""
            className={cn(
              variant === 'rail' ? 'h-[3.375rem] w-[3.375rem]' : 'h-full w-full',
              objectFit,
              variant === 'rail' ? 'rounded-lg' : 'rounded-[3px]',
              motionClass,
            )}
            style={motionStyle}
          />
        )
      ) : appearanceLoading ? (
        <span
          className={cn(
            'flex items-center justify-center',
            variant === 'rail' ? 'size-[3.375rem]' : 'h-full w-full',
            motionClass,
          )}
          style={motionStyle}
          aria-hidden
        />
      ) : (
        <span
          className={cn(
            'flex items-center justify-center',
            variant === 'rail' ? 'size-[3.375rem]' : 'h-full w-full',
            motionClass,
          )}
          style={motionStyle}
        >
          <BrandMascot
            size={variant === 'rail' ? 'lg' : 'xs'}
            staticFallback={reduceMotion}
            aria-hidden
          />
        </span>
      )}
    </span>
  );
});
