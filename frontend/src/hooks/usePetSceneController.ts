import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useChatStore } from '@/stores/chat';
import { usePrefersReducedMotion } from '@/hooks/useMobile';
import type { PetBehaviorVisual } from '@/lib/petBehaviorVisual';
import {
  PET_SCENE_ACTION_KEYS,
  type PetSceneActionKey,
  type PetRoamRange,
  type PetSettings,
  resolveActionWeights,
  resolvedBehavior,
  roamRangeFraction,
} from '@/lib/petSettings';

const JUMP_MS = 700;
const HAPPY_MS = 1200;
const STATIONARY_MS: Partial<Record<PetBehaviorVisual, number>> = {
  lookAround: 1400,
  wave: 1000,
  dance: 1500,
  shake: 600,
};

const DOCK_NARROW_PX = 80;

function easeInOut(t: number) {
  return t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
}

function getHalfBoundPx(
  stageWidth: number,
  roam: PetRoamRange | undefined,
  surface: 'dock' | 'hero' | 'chatEmpty',
): number {
  if (stageWidth < 1) return 0;
  const f = roamRangeFraction(roam);
  let half = (stageWidth / 2) * f;
  if (stageWidth < DOCK_NARROW_PX) {
    const cap = surface === 'dock' ? 10 : 14;
    half = Math.min(half, cap);
  }
  return Math.max(0, half);
}

export interface PetSceneState {
  overrideVisual: PetBehaviorVisual | null;
  x: number;
  y: number;
  facing: 1 | -1;
  isMoving: boolean;
}

function pickWeighted(weights: Record<PetSceneActionKey, number>, rng: () => number): PetSceneActionKey {
  const entries = PET_SCENE_ACTION_KEYS.map((k) => [k, Math.max(0, weights[k] ?? 0)] as const);
  const total = entries.reduce((s, [, w]) => s + w, 0);
  if (total <= 0) return 'idle';
  let r = rng() * total;
  for (const [k, w] of entries) {
    r -= w;
    if (r <= 0) return k;
  }
  return 'idle';
}

function visualForAction(a: PetSceneActionKey): PetBehaviorVisual {
  if (a === 'idle') return 'idle';
  if (a === 'lookAround') return 'lookAround';
  if (a === 'shake') return 'shake';
  return a;
}

export function usePetSceneController(args: {
  settings: PetSettings;
  stageRef: React.RefObject<HTMLElement | null>;
  surface: 'dock' | 'hero' | 'chatEmpty';
}): PetSceneState & {
  onPetClick: (e: React.MouseEvent) => void;
  onPetDoubleClick: (e: React.MouseEvent) => void;
  reduceMotion: boolean;
} {
  const { settings, stageRef, surface } = args;
  const behavior = useMemo(() => resolvedBehavior(settings), [settings]);
  const reduceMotion = usePrefersReducedMotion();
  const isStreaming = useChatStore((s) => s.isStreaming);

  const canAutopilot = useMemo(() => {
    if (reduceMotion) return false;
    if (isStreaming) return false;
    if (behavior.autopilot === false) return false;
    if (behavior.mode === 'manual' && (behavior.manualMode === 'sleep' || behavior.manualMode === 'focus')) {
      return false;
    }
    return true;
  }, [reduceMotion, isStreaming, behavior.autopilot, behavior.mode, behavior.manualMode]);

  const [overrideVisual, setOverrideVisual] = useState<PetBehaviorVisual | null>(null);
  const [x, setX] = useState(0);
  const [y, setY] = useState(0);
  const [facing, setFacing] = useState<1 | -1>(1);
  const [isMoving, setIsMoving] = useState(false);
  const [stageWidth, setStageWidth] = useState(200);

  const xRef = useRef(0);
  const rafRef = useRef<number | null>(null);
  const timeoutRefs = useRef<ReturnType<typeof setTimeout>[]>([]);
  const mounted = useRef(true);
  const rngRef = useRef<() => number>(Math.random);
  const singleClickTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const phaseRef = useRef(0);
  const pickAndRunRef = useRef<() => void>(() => {});

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const clearTimers = useCallback(() => {
    for (const t of timeoutRefs.current) {
      clearTimeout(t);
    }
    timeoutRefs.current = [];
  }, []);

  const cancelRaf = useCallback(() => {
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }, []);

  const hardResetPosition = useCallback(() => {
    xRef.current = 0;
    setX(0);
    setY(0);
    setIsMoving(false);
    setOverrideVisual(null);
  }, []);

  useEffect(() => {
    xRef.current = x;
  }, [x]);

  useEffect(() => {
    const el = stageRef.current;
    if (!el || typeof ResizeObserver === 'undefined') {
      return;
    }
    const ro = new ResizeObserver((ents) => {
      const w = ents[0]?.contentRect?.width;
      if (w != null && w > 0) setStageWidth(w);
    });
    ro.observe(el);
    setStageWidth(el.getBoundingClientRect().width);
    return () => ro.disconnect();
  }, [stageRef]);

  const runWalkTo = useCallback(
    (from: number, to: number, durationMs: number, onDone: () => void) => {
      cancelRaf();
      setIsMoving(true);
      setOverrideVisual('walk');
      setFacing((to >= from ? 1 : -1) as 1 | -1);
      const t0 = performance.now();
      const start = from;
      const step = (now: number) => {
        if (!mounted.current) return;
        const t = Math.min(1, (now - t0) / durationMs);
        const p = start + (to - start) * easeInOut(t);
        xRef.current = p;
        setX(p);
        if (t < 1) {
          rafRef.current = requestAnimationFrame(step);
        } else {
          rafRef.current = null;
          setIsMoving(false);
          onDone();
        }
      };
      rafRef.current = requestAnimationFrame(step);
    },
    [cancelRaf],
  );

  const runIdleDwell = useCallback(
    (ms: number) => {
      clearTimers();
      const t = setTimeout(() => {
        if (!mounted.current) return;
        if (!canAutopilot) return;
        pickAndRunRef.current();
      }, ms);
      timeoutRefs.current.push(t);
    },
    [canAutopilot, clearTimers],
  );

  const pickAndRun = useCallback(() => {
    if (!mounted.current) return;
    const w = getHalfBoundPx(stageWidth, behavior.roamRange, surface);
    if (w < 2) {
      const t = setTimeout(() => {
        if (mounted.current) runIdleDwell(1200);
      }, 800);
      timeoutRefs.current.push(t);
      return;
    }
    const weights = resolveActionWeights(behavior.actionWeights);
    const action = pickWeighted(weights, rngRef.current);
    const v = visualForAction(action);
    if (action === 'idle' || v === 'idle') {
      setOverrideVisual(null);
      const dwell = 2000 + rngRef.current() * 2500;
      runIdleDwell(dwell);
      return;
    }
    if (action === 'walk') {
      const from = xRef.current;
      const wideDock = surface === 'dock' && stageWidth > 72;
      const spanLo = wideDock ? 0.48 : 0.35;
      const spanHi = wideDock ? 0.92 : 0.9;
      const dist = w * (spanLo + rngRef.current() * (spanHi - spanLo));
      const dir = rngRef.current() > 0.5 ? 1 : -1;
      let target = from + dir * dist;
      target = Math.max(-w, Math.min(w, target));
      if (Math.abs(target - from) < 6) {
        const bump = (rngRef.current() > 0.5 ? 1 : -1) * Math.max(12, w * 0.2);
        target = Math.max(-w, Math.min(w, -from * 0.3 + bump));
      }
      const baseDur = wideDock && stageWidth > 100 ? 1800 : 1500;
      const durRange = wideDock && stageWidth > 100 ? 1600 : 1200;
      const dur = baseDur + rngRef.current() * durRange;
      runWalkTo(from, target, dur, () => {
        if (!mounted.current) return;
        if (!canAutopilot) {
          setOverrideVisual(null);
          return;
        }
        setOverrideVisual(null);
        runIdleDwell(800 + rngRef.current() * 1200);
      });
      return;
    }
    if (action === 'jump') {
      cancelRaf();
      setOverrideVisual('jump');
      setIsMoving(true);
      const j0 = performance.now();
      const h = 18 + rngRef.current() * 8;
      const stepJ = (now: number) => {
        if (!mounted.current) return;
        const tj = Math.min(1, (now - j0) / JUMP_MS);
        const yy = -4 * h * tj * (1 - tj);
        setY(yy);
        if (tj < 1) {
          rafRef.current = requestAnimationFrame(stepJ);
        } else {
          rafRef.current = null;
          setY(0);
          setIsMoving(false);
          setOverrideVisual(null);
          runIdleDwell(600 + rngRef.current() * 800);
        }
      };
      rafRef.current = requestAnimationFrame(stepJ);
      return;
    }
    const du = STATIONARY_MS[v] ?? 1000;
    setOverrideVisual(v);
    setIsMoving(false);
    const t2 = setTimeout(() => {
      if (!mounted.current) return;
      setOverrideVisual(null);
      runIdleDwell(500 + rngRef.current() * 1000);
    }, du);
    timeoutRefs.current.push(t2);
  }, [
    canAutopilot,
    stageWidth,
    behavior.roamRange,
    behavior.actionWeights,
    surface,
    runWalkTo,
    cancelRaf,
    runIdleDwell,
  ]);

  useEffect(() => {
    pickAndRunRef.current = pickAndRun;
  }, [pickAndRun]);

  useEffect(() => {
    let s = 0;
    for (let i = 0; i < surface.length; i++) s = (s * 31 + surface.charCodeAt(i)) | 0;
    phaseRef.current = (s & 0xffff) / 0x10000;
    rngRef.current = () => {
      phaseRef.current = (phaseRef.current * 9301 + 49297) % 233280;
      return phaseRef.current / 233280;
    };
  }, [surface]);

  useEffect(() => {
    if (!canAutopilot) {
      clearTimers();
      cancelRaf();
      hardResetPosition();
      return;
    }
    const delay = 800 + rngRef.current() * 1200;
    const t = setTimeout(() => {
      if (mounted.current) pickAndRunRef.current();
    }, delay);
    timeoutRefs.current.push(t);
    return () => {
      clearTimers();
      cancelRaf();
    };
  }, [canAutopilot, clearTimers, cancelRaf, hardResetPosition]);

  useEffect(() => {
    if (!isStreaming) {
      if (xRef.current !== 0) {
        cancelRaf();
        const from = xRef.current;
        const t0 = performance.now();
        const d = 400;
        const step = (now: number) => {
          if (!mounted.current) return;
          const u = Math.min(1, (now - t0) / d);
          const nx = from * (1 - easeInOut(u));
          xRef.current = nx;
          setX(nx);
          if (u < 1) {
            rafRef.current = requestAnimationFrame(step);
          } else {
            rafRef.current = null;
            xRef.current = 0;
            setX(0);
          }
        };
        rafRef.current = requestAnimationFrame(step);
      }
      return;
    }
    clearTimers();
    cancelRaf();
    setOverrideVisual(null);
    setY(0);
    setIsMoving(false);
    const from = xRef.current;
    if (from === 0) return;
    const t0 = performance.now();
    const d = 320;
    const step = (now: number) => {
      if (!mounted.current) return;
      const u = Math.min(1, (now - t0) / d);
      const nx = from * (1 - easeInOut(u));
      xRef.current = nx;
      setX(nx);
      if (u < 1) {
        rafRef.current = requestAnimationFrame(step);
      } else {
        rafRef.current = null;
        xRef.current = 0;
        setX(0);
      }
    };
    rafRef.current = requestAnimationFrame(step);
  }, [isStreaming, clearTimers, cancelRaf]);

  const onPetClick = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      if (reduceMotion) return;
      if (singleClickTimer.current) {
        clearTimeout(singleClickTimer.current);
        singleClickTimer.current = null;
      }
      singleClickTimer.current = setTimeout(() => {
        singleClickTimer.current = null;
        if (!mounted.current) return;
        setOverrideVisual('happy');
        const t = setTimeout(() => {
          if (!mounted.current) return;
          setOverrideVisual(null);
        }, HAPPY_MS);
        timeoutRefs.current.push(t);
      }, 300);
    },
    [reduceMotion],
  );

  const onPetDoubleClick = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      if (reduceMotion) return;
      if (singleClickTimer.current) {
        clearTimeout(singleClickTimer.current);
        singleClickTimer.current = null;
      }
      clearTimers();
      cancelRaf();
      setIsMoving(true);
      setOverrideVisual('jump');
      const j0 = performance.now();
      const h = 20;
      const stepJ = (now: number) => {
        if (!mounted.current) return;
        const tj = Math.min(1, (now - j0) / JUMP_MS);
        const yy = -4 * h * tj * (1 - tj);
        setY(yy);
        if (tj < 1) {
          rafRef.current = requestAnimationFrame(stepJ);
        } else {
          rafRef.current = null;
          setY(0);
          setIsMoving(false);
          setOverrideVisual(null);
        }
      };
      rafRef.current = requestAnimationFrame(stepJ);
    },
    [reduceMotion, clearTimers, cancelRaf],
  );

  return {
    overrideVisual: isStreaming ? null : overrideVisual,
    x,
    y,
    facing,
    isMoving,
    onPetClick,
    onPetDoubleClick,
    reduceMotion,
  };
}
