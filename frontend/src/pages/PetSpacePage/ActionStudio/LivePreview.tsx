import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuthedFileBlobUrl } from '@/hooks/useAuthedFileBlobUrl';
import { usePetClipResolver } from '@/hooks/usePetClipResolver';
import { BrandMascot } from '@/components/brand/BrandMascot';
import { usePrefersReducedMotion } from '@/hooks/useMobile';
import { builtinPetSvgUrl, isPetBuiltinAppearance } from '@/lib/builtinPets';
import { effectivePetImageMime } from '@/lib/petAppearanceMime';
import { appearanceGifBindMotionActive, resolvedBehavior, type PetSettings } from '@/lib/petSettings';
import { petClipMotionStyleVars, petMotionStyleVars, pickPetClipAppearanceClass, resolvePetVisual } from '@/lib/petBehaviorVisual';
import type { PetProjectFileRow } from '@/api/petSpace';
import { pickPreviewAppearanceFileId } from '@/lib/petShowcasePresets';
import { Button } from '@/components/ui';
import { cn } from '@/lib/utils';
import type { PetClipState } from '@/lib/petSettings';
import { studioStateToVisualInput } from './actionStudioPreview';

const PULSE_MS = 2_200;

export function LivePreview({
  primaryParsed,
  listedFiles,
  selectedState,
}: {
  primaryParsed: PetSettings;
  listedFiles: PetProjectFileRow[];
  selectedState: PetClipState | null;
}) {
  const { t } = useTranslation();
  const reduceMotion = usePrefersReducedMotion();
  const [simStream, setSimStream] = useState(false);
  const [tick, setTick] = useState(0);
  const [pulseOn, setPulseOn] = useState(false);

  const behavior = resolvedBehavior(primaryParsed);
  const s = selectedState;
  const inputs = useMemo(
    () => (s ? studioStateToVisualInput(s, behavior) : { behavior, isStreaming: false, happyFlash: false }),
    [s, behavior, tick],
  );
  const visual = resolvePetVisual({
    behavior: inputs.behavior,
    reduceMotion,
    isStreaming: simStream,
    happyFlash: inputs.happyFlash,
  });
  const previewIdle = inputs.behavior.idleAnimation;
  const clip = usePetClipResolver({
    settings: primaryParsed,
    files: listedFiles,
    visual,
    idleAnimation: previewIdle,
    disableOnceFallback: true,
  });
  const prevBuiltin = isPetBuiltinAppearance(primaryParsed.appearance_builtin)
    ? primaryParsed.appearance_builtin
    : null;
  const appId = pickPreviewAppearanceFileId(primaryParsed, listedFiles, null);
  const row = appId ? listedFiles.find((f) => f.file_id === appId) ?? null : null;
  const m = row ? effectivePetImageMime(row.mime_type, row.original_name) : null;
  const { url: blob, isPending: baseBlobPending } = useAuthedFileBlobUrl(appId, m, row?.original_name ?? null);
  const baseUrl = prevBuiltin ? builtinPetSvgUrl(prevBuiltin) : blob;
  const using = clip.isClipDrawable && Boolean(clip.displaySrc);
  const showUrl = using ? (clip.displaySrc as string) : baseUrl;
  const hasBuiltin = using ? Boolean(clip.activeClip?.binding.builtin) : Boolean(prevBuiltin);
  const em = using ? clip.displayMime : m;
  const gifB = appearanceGifBindMotionActive(primaryParsed, em, hasBuiltin);
  const ov = using && clip.activeClip && clip.activeClip.binding.overrideCssMotion !== false;
  const motionC = pickPetClipAppearanceClass(visual, behavior, reduceMotion, {
    clipActive: using,
    clipOverride: Boolean(ov),
    gifBindForDisplayedAsset: gifB,
  });
  const style =
    using && clip.activeClip
      ? petClipMotionStyleVars(behavior, true, clip.activeClip.binding.speed)
      : petMotionStyleVars(behavior);
  const mirror = using && clip.activeClip?.binding.mirror;
  const fit = using && clip.activeClip?.binding?.fit === 'cover' ? 'object-cover' : 'object-contain';
  const appearanceLoading = Boolean(
    (!prevBuiltin && appId && baseBlobPending) || clip.clipFileBlobPending,
  );

  useEffect(() => {
    if (!s) return;
    if (!pulseOn) return;
    const t0 = window.setTimeout(() => setPulseOn(false), PULSE_MS);
    return () => clearTimeout(t0);
  }, [s, pulseOn, tick]);

  return (
    <div className="space-y-3">
      <div
        className={cn(
          'mx-auto flex aspect-square max-w-[17rem] w-full items-center justify-center overflow-hidden rounded-2xl border border-border bg-background shadow-inner',
          visual === 'sleep' && 'opacity-55',
        )}
      >
        {showUrl ? (
          mirror ? (
            <span className="inline-flex h-full w-full max-h-full max-w-full items-center justify-center scale-x-[-1]">
              <img
                key={`${s}-${String(pulseOn)}-${tick}`}
                src={showUrl}
                alt=""
                className={cn('h-full w-full', fit, motionC, 'bg-white/90 dark:bg-slate-900/80')}
                style={style}
              />
            </span>
          ) : (
            <img
              key={`${s}-${String(pulseOn)}-${tick}`}
              src={showUrl}
              alt=""
              className={cn('h-full w-full', fit, motionC, 'bg-white/90 dark:bg-slate-900/80')}
              style={style}
            />
          )
        ) : appearanceLoading ? (
          <span className={motionC} style={style} aria-hidden />
        ) : (
          <span className={motionC} style={style}>
            <BrandMascot size="lg" staticFallback={reduceMotion} />
          </span>
        )}
      </div>
      <div className="flex flex-wrap items-center justify-center gap-2">
        <Button type="button" size="sm" variant={simStream ? 'primary' : 'outline'} onClick={() => setSimStream((v) => !v)}>
          {t('petSpace.behaviorSimulateStream')}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={!s}
          onClick={() => {
            if (!s) return;
            setTick((k) => k + 1);
            setPulseOn(true);
          }}
        >
          {t('petSpace.studio.testPulse')}
        </Button>
      </div>
      {pulseOn && s ? <p className="text-center text-[11px] text-muted-foreground">{t('petSpace.studio.pulseHint')}</p> : null}
    </div>
  );
}
