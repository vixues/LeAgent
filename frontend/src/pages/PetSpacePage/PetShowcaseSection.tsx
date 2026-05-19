import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Sparkles } from 'lucide-react';
import { Button } from '@/components/ui';
import { cn } from '@/lib/utils';
import type { PetProject, PetProjectFileRow } from '@/api/petSpace';
import { useAuthedFileBlobUrl } from '@/hooks/useAuthedFileBlobUrl';
import { usePetClipResolver } from '@/hooks/usePetClipResolver';
import { BrandMascot } from '@/components/brand/BrandMascot';
import { usePrefersReducedMotion } from '@/hooks/useMobile';
import type { PetNestSettings, PetSettings } from '@/lib/petSettings';
import {
  appearanceGifBindMotionActive,
  parsePetSettings,
  resolvedBehavior,
  resolvedNest,
} from '@/lib/petSettings';
import {
  petClipMotionStyleVars,
  petMotionStyleVars,
  pickPetClipAppearanceClass,
  resolvePetVisual,
} from '@/lib/petBehaviorVisual';
import { builtinPetSvgUrl, isPetBuiltinAppearance } from '@/lib/builtinPets';
import { effectivePetImageMime, isPetRenderableImageRow } from '@/lib/petAppearanceMime';
import {
  mergeShowcasePreviewSettings,
  PET_SHOWCASE_PRESETS,
  pickPreviewAppearanceFileId,
  type PetShowcasePreset,
} from '@/lib/petShowcasePresets';

export type PetShowcasePresetLayout = 'chips' | 'grid';

interface PetShowcaseSectionProps {
  primaryProject: PetProject;
  listedFiles: PetProjectFileRow[];
  primaryParsed: PetSettings;
  patchSettingsMut: {
    isPending: boolean;
    mutate: (vars: {
      projectId: string;
      baseSettings: string | null | undefined;
      patch: Partial<PetSettings>;
    }) => void;
  };
  /** `grid` shows preset cards (e.g. showroom tab); `chips` compact row */
  presetLayout?: PetShowcasePresetLayout;
  showHeader?: boolean;
}

function dockStatusKey(visual: string): string {
  switch (visual) {
    case 'working':
      return 'petSpace.dockStatusWorking';
    case 'happy':
      return 'petSpace.dockStatusHappy';
    case 'sleep':
      return 'petSpace.dockStatusSleep';
    case 'focus':
      return 'petSpace.dockStatusFocus';
    case 'excited':
      return 'petSpace.dockStatusExcited';
    case 'walk':
    case 'wave':
    case 'jump':
    case 'shake':
    case 'lookAround':
    case 'dance':
      return `petSpace.manualMode.${visual}`;
    default:
      return 'petSpace.dockStatusIdle';
  }
}

export function PetShowcaseSection({
  primaryProject,
  listedFiles,
  primaryParsed,
  patchSettingsMut,
  presetLayout = 'chips',
  showHeader = true,
}: PetShowcaseSectionProps) {
  const { t } = useTranslation();
  const reduceMotion = usePrefersReducedMotion();
  const [presetId, setPresetId] = useState<string | null>(null);
  const [simStream, setSimStream] = useState(false);

  const activePreset = useMemo(
    () => (presetId ? PET_SHOWCASE_PRESETS.find((p) => p.id === presetId) ?? null : null),
    [presetId],
  );

  const previewSettings = useMemo(
    () => mergeShowcasePreviewSettings(primaryParsed, activePreset, listedFiles),
    [primaryParsed, activePreset, listedFiles],
  );

  const nest = resolvedNest(previewSettings);
  const behavior = resolvedBehavior(previewSettings);
  const pattern = nest.backgroundPattern ?? 'none';
  const bgOpacity = nest.backgroundOpacity ?? 0.25;

  const previewAppearanceBuiltin = isPetBuiltinAppearance(previewSettings.appearance_builtin)
    ? previewSettings.appearance_builtin
    : null;
  const previewAppearanceId = previewAppearanceBuiltin
    ? null
    : pickPreviewAppearanceFileId(primaryParsed, listedFiles, activePreset);
  const previewFileRow = listedFiles.find((f) => f.file_id === previewAppearanceId);
  const { url: previewBlobUrl, isPending: previewBlobPending } = useAuthedFileBlobUrl(
    previewAppearanceId,
    previewFileRow?.mime_type ?? null,
    previewFileRow?.original_name ?? null,
  );
  const previewAppearanceSrc = previewAppearanceBuiltin
    ? builtinPetSvgUrl(previewAppearanceBuiltin)
    : previewBlobUrl;

  const bgRow = listedFiles.find((f) => f.file_id === nest.backgroundFileId);
  const { url: bgUrl } = useAuthedFileBlobUrl(
    nest.backgroundFileId,
    bgRow?.mime_type ?? null,
    bgRow?.original_name ?? null,
  );

  const visual = resolvePetVisual({
    behavior,
    reduceMotion,
    isStreaming: simStream,
    happyFlash: false,
  });

  const clip = usePetClipResolver({
    settings: previewSettings,
    files: listedFiles,
    visual,
    idleAnimation: behavior.idleAnimation,
  });
  const usingClip = clip.isClipDrawable && Boolean(clip.displaySrc);
  const showcaseDisplaySrc = usingClip ? (clip.displaySrc as string) : previewAppearanceSrc;
  const showcaseAppearanceLoading = Boolean(
    (!previewAppearanceBuiltin && previewAppearanceId && previewBlobPending) || clip.clipFileBlobPending,
  );

  const effectiveMime = usingClip
    ? clip.displayMime
    : previewFileRow
      ? effectivePetImageMime(previewFileRow.mime_type, previewFileRow.original_name)
      : null;
  const hasBuiltin = usingClip ? Boolean(clip.activeClip?.binding.builtin) : Boolean(previewAppearanceBuiltin);

  const gifBind = appearanceGifBindMotionActive(
    previewSettings,
    effectiveMime,
    hasBuiltin,
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

  const clipMirror = usingClip && clip.activeClip?.binding.mirror;
  const objectFit = usingClip && clip.activeClip?.binding?.fit === 'cover' ? 'object-cover' : 'object-contain';

  const exportExample = useMemo(
    () => ({
      appearance_file_id: previewAppearanceId,
      appearance_builtin: previewAppearanceBuiltin,
      nest: resolvedNest(previewSettings),
      behavior: resolvedBehavior(previewSettings),
    }),
    [previewAppearanceId, previewAppearanceBuiltin, previewSettings],
  );

  const applyPreset = (p: PetShowcasePreset) => {
    const images = listedFiles.filter((f) => isPetRenderableImageRow(f));
    const cur = parsePetSettings(primaryProject.settings);
    const nestPatch: PetNestSettings = { ...resolvedNest(cur), ...p.nest };
    if (p.backgroundImageIndex != null && images[p.backgroundImageIndex]) {
      nestPatch.backgroundFileId = images[p.backgroundImageIndex]!.file_id;
    }
    const patch: Partial<PetSettings> = {
      nest: nestPatch,
      behavior: { ...resolvedBehavior(cur), ...p.behavior },
    };
    if (p.appearanceImageIndex != null && images[p.appearanceImageIndex]) {
      patch.appearance_file_id = images[p.appearanceImageIndex]!.file_id;
    }
    if (p.appearanceBuiltin && isPetBuiltinAppearance(p.appearanceBuiltin)) {
      patch.appearance_builtin = p.appearanceBuiltin;
      patch.appearance_file_id = null;
    }
    patchSettingsMut.mutate({
      projectId: primaryProject.id,
      baseSettings: primaryProject.settings,
      patch,
    });
    setPresetId(null);
  };

  const presetPicker = (
    <>
      {presetLayout === 'grid' ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          <button
            type="button"
            onClick={() => setPresetId(null)}
            className={cn(
              'rounded-xl border p-4 text-left transition-colors min-h-[100px] flex flex-col gap-1',
              presetId === null
                ? 'border-primary-500 bg-primary-50/80 dark:bg-primary-950/40 ring-1 ring-primary-400/30'
                : 'border-border-subtle bg-surface-sunken/50 hover:bg-surface-sunken',
            )}
          >
            <span className="text-sm font-semibold text-foreground">{t('petSpace.showcaseSavedOnly')}</span>
            <span className="text-xs text-muted-foreground">{t('petSpace.showcaseSavedOnlyDesc')}</span>
          </button>
          {PET_SHOWCASE_PRESETS.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => setPresetId(p.id)}
              className={cn(
                'rounded-xl border p-4 text-left transition-colors min-h-[100px] flex flex-col gap-1',
                presetId === p.id
                  ? 'border-primary-500 bg-primary-50/80 dark:bg-primary-950/40 ring-1 ring-primary-400/30'
                  : 'border-border-subtle bg-surface-sunken/50 hover:bg-surface-sunken',
              )}
            >
              <span className="text-sm font-semibold text-foreground truncate">
                {t(`petSpace.showcasePreset.${p.id}.name`, { defaultValue: p.id })}
              </span>
              <span className="text-xs text-muted-foreground line-clamp-2">
                {t(`petSpace.showcasePreset.${p.id}.desc`, { defaultValue: '' })}
              </span>
            </button>
          ))}
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setPresetId(null)}
            className={cn(
              'px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors',
              presetId === null
                ? 'border-primary-500 bg-primary-50 dark:bg-primary-950/50 text-primary-800 dark:text-primary-200'
                : 'border-border-subtle bg-surface-sunken/60 hover:bg-surface-sunken',
            )}
          >
            {t('petSpace.showcaseSavedOnly')}
          </button>
          {PET_SHOWCASE_PRESETS.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => setPresetId(p.id)}
              className={cn(
                'px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors max-w-[200px] truncate',
                presetId === p.id
                  ? 'border-primary-500 bg-primary-50 dark:bg-primary-950/50 text-primary-800 dark:text-primary-200'
                  : 'border-border-subtle bg-surface-sunken/60 hover:bg-surface-sunken',
              )}
              title={t(`petSpace.showcasePreset.${p.id}.desc`, { defaultValue: '' })}
            >
              {t(`petSpace.showcasePreset.${p.id}.name`, { defaultValue: p.id })}
            </button>
          ))}
        </div>
      )}
    </>
  );

  return (
    <div className="rounded-2xl border border-border bg-gradient-to-br from-surface-sunken/50 to-surface-elevated/30 p-5 space-y-4">
      {showHeader ? (
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-100 dark:bg-primary-900/40 text-primary-600 dark:text-primary-300">
            <Sparkles className="h-5 w-5" aria-hidden />
          </div>
          <div className="min-w-0 flex-1 space-y-1">
            <h3 className="text-sm font-semibold text-foreground">{t('petSpace.showcaseTitle')}</h3>
            <p className="text-xs text-muted-foreground leading-relaxed">{t('petSpace.showcaseIntro')}</p>
          </div>
        </div>
      ) : null}

      {presetPicker}

      <label className="flex items-center gap-2 text-xs cursor-pointer select-none">
        <input
          type="checkbox"
          className="rounded border-border"
          checked={simStream}
          onChange={(e) => setSimStream(e.target.checked)}
        />
        {t('petSpace.showcaseSimulateStream')}
      </label>

      <div
        className={cn(
          'pet-nest relative rounded-xl border overflow-hidden border-border/80 bg-surface-sunken/40',
          'ring-1 ring-border-subtle',
        )}
        data-theme={nest.themeId}
        data-pattern={pattern}
        data-bg-fit={nest.backgroundFit ?? 'cover'}
        data-bg-position={nest.backgroundPosition ?? 'center'}
        style={
          {
            '--pet-nest-accent': nest.accent,
            '--pet-nest-bg-opacity': String(bgOpacity),
          } as React.CSSProperties
        }
      >
        <div className="pet-nest__preset pointer-events-none absolute inset-0 opacity-[0.22] dark:opacity-[0.28]" aria-hidden />
        {bgUrl ? (
          <div
            className="pet-nest__bg-photo pointer-events-none absolute inset-0"
            style={{ backgroundImage: `url(${bgUrl})` }}
            aria-hidden
          />
        ) : null}
        {pattern !== 'none' ? (
          <div
            className={cn('pet-nest__pattern pointer-events-none absolute inset-0', `pet-nest__pattern--${pattern}`)}
            aria-hidden
          />
        ) : null}
        <div className="relative z-[1] p-3 sm:p-4 space-y-3">
          <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">
            {t('petSpace.showcasePreviewLabel')}
          </p>
          <div className="flex items-stretch gap-3 rounded-lg border-0 bg-black/[0.03] dark:bg-white/[0.04] p-2.5">
            <div
              className={cn(
                'flex-shrink-0 w-14 h-14 rounded-xl border border-border-subtle bg-background/90 flex items-center justify-center overflow-hidden',
                visual === 'sleep' && 'opacity-55',
                visual === 'excited' && !reduceMotion && 'ring-2 ring-amber-400/50',
                visual === 'focus' && 'ring-1 ring-slate-400/40',
              )}
            >
              {showcaseDisplaySrc ? (
                clipMirror ? (
                  <span className="inline-flex h-full w-full items-center justify-center scale-x-[-1]">
                    <img
                      src={showcaseDisplaySrc}
                      alt=""
                      className={cn(
                        'w-full h-full bg-white/90 dark:bg-slate-900/80',
                        objectFit,
                        motionClass,
                      )}
                      style={motionStyle}
                    />
                  </span>
                ) : (
                  <img
                    src={showcaseDisplaySrc}
                    alt=""
                    className={cn(
                      'w-full h-full bg-white/90 dark:bg-slate-900/80',
                      usingClip ? objectFit : 'object-cover',
                      motionClass,
                    )}
                    style={motionStyle}
                  />
                )
              ) : showcaseAppearanceLoading ? (
                <span className={cn(motionClass, 'h-full w-full min-h-[2.5rem]')} style={motionStyle} aria-hidden />
              ) : (
                <span className={motionClass} style={motionStyle}>
                  <BrandMascot size="md" staticFallback={reduceMotion} aria-hidden />
                </span>
              )}
            </div>
            <div className="flex min-w-0 flex-1 flex-col justify-center gap-0.5">
              <span className="text-xs font-semibold text-foreground truncate">{t('petSpace.nav')}</span>
              <span className="text-[11px] text-muted-foreground truncate">
                {t(dockStatusKey(visual))}
                {behavior.mode === 'auto' && (
                  <span className="text-muted-foreground-tertiary">
                    {' · '}
                    {t(`petSpace.autoReactivity.${behavior.autoReactivity ?? 'normal'}`)}
                  </span>
                )}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 items-center">
        <Button
          type="button"
          size="sm"
          disabled={!activePreset || patchSettingsMut.isPending}
          onClick={() => activePreset && applyPreset(activePreset)}
        >
          {t('petSpace.showcaseApply')}
        </Button>
        <p className="text-[11px] text-muted-foreground-tertiary">{t('petSpace.showcaseApplyHint')}</p>
      </div>

      <details className="rounded-lg border border-dashed border-border-subtle bg-surface-sunken/30 px-3 py-2">
        <summary className="text-xs font-medium text-muted-foreground cursor-pointer select-none">
          {t('petSpace.showcaseJsonHint')}
        </summary>
        <pre className="mt-2 text-[10px] leading-snug font-mono text-muted-foreground overflow-x-auto whitespace-pre-wrap break-all">
          {JSON.stringify(exportExample, null, 2)}
        </pre>
      </details>
    </div>
  );
}
