import { useEffect, useMemo, useRef, useState } from 'react';
import type { PetProjectFileRow } from '@/api/petSpace';
import { useAuthedFileBlobUrl } from '@/hooks/useAuthedFileBlobUrl';
import { builtinPetSvgUrl, isPetBuiltinAppearance } from '@/lib/builtinPets';
import { effectivePetImageMime } from '@/lib/petAppearanceMime';
import { resolvePetClip, type PetClipBinding, type PetClipBehaviorKey, type PetClipState, type PetSettings } from '@/lib/petSettings';
import type { PetBehaviorVisual } from '@/lib/petBehaviorVisual';
import type { PetIdleAnimation } from '@/lib/petSettings';

const ONCE_FALLBACK_MS = 2_800;

/**
 * Resolves a per-state/built-in asset clip, optional once-play suppression for loop: "once" bindings, and a blob URL for file clips.
 */
export function usePetClipResolver(options: {
  settings: PetSettings;
  files: PetProjectFileRow[] | null | undefined;
  visual: PetBehaviorVisual;
  idleAnimation: PetIdleAnimation;
  /**
   * When true (e.g. action studio "test pulse"), skip auto once suppression so the test clip always shows.
   */
  disableOnceFallback?: boolean;
}): {
  activeClip: { key: PetClipState; binding: PetClipBinding } | null;
  displaySrc: string | null;
  displayMime: string | null;
  isClipDrawable: boolean;
  /** File-backed clip selected but preview blob not ready yet. */
  clipFileBlobPending: boolean;
} {
  const { settings, files, visual, idleAnimation, disableOnceFallback = false } = options;

  const r = useMemo(
    () => resolvePetClip(visual as PetClipBehaviorKey, idleAnimation, settings),
    [settings, visual, idleAnimation],
  );

  const fileRow = useMemo(() => {
    if (!r?.binding.fileId) return null;
    return (files ?? []).find((f) => f.file_id === r.binding.fileId) ?? null;
  }, [r, files]);

  const canResolveFile = useMemo(() => {
    if (!r) return false;
    if (r.binding.builtin) return isPetBuiltinAppearance(r.binding.builtin);
    if (r.binding.fileId) return Boolean(fileRow);
    return false;
  }, [r, fileRow]);

  const [onceExhausted, setOnceExhausted] = useState(false);
  const visualRef = useRef(visual);
  const clipIdRef = useRef<string>('');
  const nextClipId = r ? `${r.key}:${r.binding.fileId ?? r.binding.builtin ?? 'x'}:${r.binding.loop ?? 'loop'}` : 'none';

  useEffect(() => {
    if (clipIdRef.current !== nextClipId) {
      clipIdRef.current = nextClipId;
      setOnceExhausted(false);
    }
  }, [nextClipId]);

  useEffect(() => {
    if (visualRef.current !== visual) {
      visualRef.current = visual;
      setOnceExhausted(false);
    }
  }, [visual]);

  useEffect(() => {
    if (disableOnceFallback) {
      return;
    }
    if (!r || r.binding.loop !== 'once' || !canResolveFile) {
      return;
    }
    if (onceExhausted) {
      return;
    }
    const s = 1 / Math.max(0.25, Math.min(4, Number(r.binding.speed) || 1));
    const ms = Math.min(10_000, Math.round(ONCE_FALLBACK_MS * s));
    const t = window.setTimeout(() => {
      setOnceExhausted(true);
    }, ms);
    return () => clearTimeout(t);
  }, [r, canResolveFile, onceExhausted, nextClipId, visual, disableOnceFallback]);

  const isOnceClip = r?.binding.loop === 'once';
  const isClipDrawable = Boolean(
    r &&
      canResolveFile &&
      (!isOnceClip || !onceExhausted || disableOnceFallback),
  );

  const displayMime = useMemo(() => {
    if (!r) return null;
    if (r.binding.builtin) return 'image/svg+xml';
    if (!fileRow) return null;
    return effectivePetImageMime(fileRow.mime_type, fileRow.original_name);
  }, [r, fileRow]);

  const fileIdForUrl = isClipDrawable && r?.binding.fileId && fileRow ? r.binding.fileId : null;
  const { url: clipBlob, isPending: clipBlobFetchPending } = useAuthedFileBlobUrl(
    fileIdForUrl,
    displayMime,
    fileRow?.original_name ?? null,
  );

  const displaySrc = useMemo(() => {
    if (!isClipDrawable || !r) return null;
    if (r.binding.builtin && isPetBuiltinAppearance(r.binding.builtin)) {
      return builtinPetSvgUrl(r.binding.builtin);
    }
    return clipBlob;
  }, [isClipDrawable, r, clipBlob]);

  const hasDrawable = isClipDrawable && displaySrc;
  const clipFileBlobPending = Boolean(fileIdForUrl && clipBlobFetchPending);
  return {
    activeClip: isClipDrawable && r && canResolveFile ? r : null,
    displaySrc: hasDrawable ? displaySrc : null,
    displayMime: hasDrawable ? displayMime : null,
    isClipDrawable: Boolean(hasDrawable),
    clipFileBlobPending,
  };
}
