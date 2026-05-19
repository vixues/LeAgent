import type { PetProjectFileRow } from '@/api/petSpace';
import { useAuthedFileBlobUrl } from '@/hooks/useAuthedFileBlobUrl';
import { usePetClipResolver } from '@/hooks/usePetClipResolver';
import { usePetBehaviorMode } from '@/hooks/usePetBehaviorMode';
import { usePetDockPreview } from '@/hooks/usePetDockPreview';
import { builtinPetSvgUrl } from '@/lib/builtinPets';
import type { PetBuiltinAppearance } from '@/lib/builtinPets';
import { cn } from '@/lib/utils';
import { appearanceGifBindMotionActive, type PetSettings } from '@/lib/petSettings';
import {
  petClipMotionStyleVars,
  petMotionStyleVars,
  pickPetClipAppearanceClass,
} from '@/lib/petBehaviorVisual';
import type { PetBehaviorVisual } from '@/lib/petBehaviorVisual';

export interface PetAppearanceProjectContext {
  settings: PetSettings;
  projectFiles: PetProjectFileRow[];
  previewFileId: string | null;
  mimeType: string | null;
  appearanceBuiltin: PetBuiltinAppearance | null;
  appearancePreviewOriginalName: string | null;
}

export type UsePetAppearancePreviewOptions = {
  /** Merged with chat/streaming behavior when non-null. */
  overrideVisual?: PetBehaviorVisual | null;
  /**
   * When set, use this project context (e.g. Pet Space hero) instead of the dock query for files/settings.
   * When undefined, the hook loads the primary pet from `usePetDockPreview`.
   */
  projectContext?: PetAppearanceProjectContext | null;
};

export function usePetAppearancePreview(options?: UsePetAppearancePreviewOptions) {
  const { data: dock, isPending: dockQueryPending } = usePetDockPreview();
  const ctx = options?.projectContext;
  const settings = ctx?.settings ?? dock?.settings ?? {};
  const projectFiles = ctx?.projectFiles ?? dock?.projectFiles ?? [];
  const previewFileId = ctx != null ? ctx.previewFileId : (dock?.previewFileId ?? null);
  const mime = ctx != null ? ctx.mimeType : dock?.mimeType;
  const origName = ctx != null ? ctx.appearancePreviewOriginalName : dock?.appearancePreviewOriginalName;
  const appearanceBuiltin = ctx != null ? ctx.appearanceBuiltin : dock?.appearanceBuiltin;

  const { url: blobUrl, isPending: mainBlobPending } = useAuthedFileBlobUrl(
    previewFileId ?? null,
    mime ?? null,
    origName ?? null,
  );
  const builtin = appearanceBuiltin ?? null;
  const mainPreviewUrl = builtin ? builtinPetSvgUrl(builtin) : blobUrl;
  const { visual, behavior, reduceMotion } = usePetBehaviorMode(settings, {
    overrideVisual: options?.overrideVisual ?? null,
  });

  const clip = usePetClipResolver({
    settings,
    files: projectFiles,
    visual,
    idleAnimation: behavior.idleAnimation,
  });

  const usingClip = clip.isClipDrawable && Boolean(clip.displaySrc);
  const previewUrl = usingClip ? (clip.displaySrc as string) : mainPreviewUrl;

  const hasBuiltinForGifBind = usingClip ? Boolean(clip.activeClip?.binding?.builtin) : Boolean(appearanceBuiltin);
  const effectiveMime = usingClip ? clip.displayMime : mime;

  const gifBind = appearanceGifBindMotionActive(
    settings,
    effectiveMime,
    hasBuiltinForGifBind,
  );

  const clipOverride = usingClip && clip.activeClip && clip.activeClip.binding.overrideCssMotion !== false;

  const motionClass = pickPetClipAppearanceClass(visual, behavior, reduceMotion, {
    clipActive: usingClip,
    clipOverride: Boolean(clipOverride),
    gifBindForDisplayedAsset: gifBind,
  });

  const motionStyle =
    usingClip && clip.activeClip
      ? petClipMotionStyleVars(behavior, true, clip.activeClip.binding.speed)
      : petMotionStyleVars(behavior);

  const previewShellClass = cn(
    'pet-dock-preview transition-opacity',
    visual === 'sleep' && 'opacity-55',
    visual === 'focus' && 'opacity-90',
  );

  const clipMirror = Boolean(usingClip && clip.activeClip?.binding.mirror);
  const clipObjectFit: 'cover' | 'contain' = usingClip
    ? clip.activeClip?.binding?.fit === 'cover'
      ? 'cover'
      : 'contain'
    : 'contain';

  const dockMetaPending = Boolean(!ctx && dockQueryPending);
  const mainCustomBlobPending = Boolean(!builtin && previewFileId && mainBlobPending);
  const appearanceLoading = dockMetaPending || mainCustomBlobPending || clip.clipFileBlobPending;

  return {
    dock,
    /** Effective image URL (per-state clip when set, else main project appearance). */
    previewUrl,
    visual,
    behavior,
    reduceMotion,
    motionClass,
    motionStyle,
    previewShellClass,
    usingClip,
    clipMirror,
    clipObjectFit,
    /**
     * Custom file blob or dock metadata still resolving — callers should avoid flashing the default mascot.
     */
    appearanceLoading,
  };
}
