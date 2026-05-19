import { useEffect, useMemo, useRef, useState } from 'react';
import { useChatStore } from '@/stores/chat';
import { usePrefersReducedMotion } from '@/hooks/useMobile';
import type { PetAutoReactivity, PetBehaviorSettings, PetSettings } from '@/lib/petSettings';
import { parsePetSettings, resolvedBehavior } from '@/lib/petSettings';
import { resolvePetVisual, type PetBehaviorVisual } from '@/lib/petBehaviorVisual';

export type { PetBehaviorVisual } from '@/lib/petBehaviorVisual';

/**
 * Sidebar / chat chip behavior: streaming → working; brief happy after a stream ends (unless manual focus);
 * manual sleep / focus / excited; reduced motion collapses to idle (sleep still shown).
 */
export function usePetBehaviorMode(
  settingsInput: PetSettings | string | null | undefined,
  options?: { overrideVisual: PetBehaviorVisual | null },
): {
  visual: PetBehaviorVisual;
  reduceMotion: boolean;
  reactivity: PetAutoReactivity;
  behavior: PetBehaviorSettings;
} {
  const reduceMotion = usePrefersReducedMotion();
  const settings = useMemo(() => {
    if (settingsInput === null || settingsInput === undefined) return {};
    if (typeof settingsInput === 'string') return parsePetSettings(settingsInput);
    return settingsInput;
  }, [settingsInput]);

  const behavior = useMemo(() => resolvedBehavior(settings), [settings]);

  const isStreaming = useChatStore((s) => s.isStreaming);
  const prevStreaming = useRef(isStreaming);
  const [happyFlash, setHappyFlash] = useState(false);
  const happyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const suppressHappy = behavior.mode === 'manual' && behavior.manualMode === 'focus';
    if (suppressHappy) {
      prevStreaming.current = isStreaming;
      return;
    }
    if (prevStreaming.current && !isStreaming) {
      if (happyTimer.current) clearTimeout(happyTimer.current);
      setHappyFlash(true);
      happyTimer.current = setTimeout(() => {
        setHappyFlash(false);
        happyTimer.current = null;
      }, 2000);
    }
    prevStreaming.current = isStreaming;
    return () => {
      if (happyTimer.current) clearTimeout(happyTimer.current);
    };
  }, [isStreaming, behavior.mode, behavior.manualMode]);

  const visual = useMemo(() => {
    if (options?.overrideVisual) {
      return options.overrideVisual;
    }
    return resolvePetVisual({
      behavior,
      reduceMotion,
      isStreaming,
      happyFlash,
    });
  }, [behavior, reduceMotion, isStreaming, happyFlash, options?.overrideVisual]);

  const reactivity: PetAutoReactivity = behavior.autoReactivity ?? 'normal';

  return { visual, reduceMotion, reactivity, behavior };
}
