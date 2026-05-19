import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Trash2, ExternalLink, Edit2, ChevronDown } from 'lucide-react';
import { PageShell } from '@/components/layout/PageShell';
import { Button, Input } from '@/components/ui';
import { PRIMARY_SOFT_CTA_CLASSNAME } from '@/components/ui/Button';
import { Textarea } from '@/components/ui/Textarea';
import { useToast } from '@/components/ui/Toaster';
import { cn } from '@/lib/utils';
import { petSpaceApi, type PetProject, type PetProjectFileRow } from '@/api/petSpace';
import { usePetSpaceUiStore } from '@/stores/petSpaceUiStore';
import { fetchAuthedFilePreviewBlob, useAuthedFileBlobUrl } from '@/hooks/useAuthedFileBlobUrl';
import { usePetClipResolver } from '@/hooks/usePetClipResolver';
import { BrandMascot } from '@/components/brand/BrandMascot';
import { usePrefersReducedMotion } from '@/hooks/useMobile';
import { builtinPetSvgUrl, isPetBuiltinAppearance, PET_BUILTIN_APPEARANCES } from '@/lib/builtinPets';
import { effectivePetImageMime, isPetRenderableImageRow } from '@/lib/petAppearanceMime';
import {
  appearanceGifBindMotionActive,
  DEFAULT_DOCK_FLOOR_Y_PX,
  DEFAULT_DOCK_SHADOW_OFFSET_Y_PX,
  DOCK_FLOOR_Y_MAX,
  DOCK_FLOOR_Y_MIN,
  DOCK_SHADOW_OFFSET_Y_MAX,
  DOCK_SHADOW_OFFSET_Y_MIN,
  mergePetSettings,
  parsePetSettings,
  PET_PERSONALITY_MAX_CHARS,
  resolvedBehavior,
  resolvedNest,
  resolvedPersonalityDocument,
  type NestBackgroundPattern,
  type NestBackgroundFit,
  type NestBackgroundPosition,
  type NestThemeId,
  type PetAutoReactivity,
  type PetIdleAnimation,
  type PetManualMode,
  type PetMotionStyle,
  type PetSettings,
  type PetClipState,
  type PetSettingsClipPatch,
} from '@/lib/petSettings';
import {
  petClipMotionStyleVars,
  petMotionStyleVars,
  pickPetClipAppearanceClass,
  pickPetMotionClass,
  resolvePetVisual,
} from '@/lib/petBehaviorVisual';
import { PetShowcaseSection } from './PetShowcaseSection';
import { loadImageElement, spriteSheetToGifBlob, type SpriteSheetGifMeta } from '@/lib/spriteSheetToGif';
import { PET_PRESET_SAMPLE_FILES, petPresetPublicUrl } from '@/lib/petPresetSamples';
import {
  PET_ACTION_VISUALS,
  presetStateKind,
  previewInputForVisual,
  type PetActionPreviewId,
} from '@/lib/petActionCatalog';
import { findPresetManifestPet, loadPetPresetManifest } from '@/lib/petPresetManifest';
import { ActionStudioPanel } from './ActionStudio';
import { PetSceneStage } from '@/components/pet/PetSceneStage';
import { PetLibraryFileCard } from './PetLibraryFileCard';

type TabId = 'customize' | 'studio' | 'showroom' | 'personality' | 'library' | 'about';

const NEST_THEMES: NestThemeId[] = ['grass', 'wood', 'night'];
const NEST_BACKGROUND_FITS: NestBackgroundFit[] = ['cover', 'contain', 'repeat'];
const NEST_BACKGROUND_POSITIONS: NestBackgroundPosition[] = ['center', 'top', 'bottom', 'left', 'right'];
const MANUAL_MODES: PetManualMode[] = [
  'calm',
  'sleep',
  'focus',
  'excited',
  'walk',
  'wave',
  'jump',
  'shake',
  'lookAround',
  'dance',
];
const IDLE_ANIMATIONS: PetIdleAnimation[] = ['none', 'breath', 'blink', 'float', 'tailWag', 'hop'];
const MOTION_STYLES: PetMotionStyle[] = ['gentle', 'bouncy', 'playful', 'focused'];

interface PersonalityEditorProps {
  project: PetProject;
  primaryParsed: PetSettings;
  patchSettingsMut: {
    isPending: boolean;
    mutateAsync: (vars: {
      projectId: string;
      baseSettings: string | null | undefined;
      patch: Partial<Omit<PetSettings, 'clips'>> & { clips?: PetSettingsClipPatch };
    }) => Promise<unknown>;
  };
}

function PersonalityEditor({ project, primaryParsed, patchSettingsMut }: PersonalityEditorProps) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const stored = resolvedPersonalityDocument(primaryParsed);
  const defaultPersonalityQuery = useQuery({
    queryKey: ['pet-space', 'personality', 'default'],
    queryFn: () => petSpaceApi.getDefaultPersonality(),
    staleTime: 60 * 60 * 1000,
  });
  const defaultDocument = defaultPersonalityQuery.data?.document.trim() ?? '';
  const [draft, setDraft] = useState<string>(stored || defaultDocument);

  useEffect(() => {
    setDraft(stored || defaultDocument);
  }, [defaultDocument, stored, project.id]);

  const trimmed = draft.trim();
  const charCount = draft.length;
  const overLimit = charCount > PET_PERSONALITY_MAX_CHARS;
  const isDirty = draft !== stored;
  const canSave = isDirty && !overLimit && !patchSettingsMut.isPending;

  const handleSave = useCallback(async () => {
    try {
      await patchSettingsMut.mutateAsync({
        projectId: project.id,
        baseSettings: project.settings,
        patch: {
          personality: trimmed ? { document: trimmed } : null,
        },
      });
      toast({ variant: 'success', title: t('petSpace.personalitySaved') });
    } catch (err) {
      toast({
        variant: 'error',
        title: err instanceof Error ? err.message : t('petSpace.personalitySaved'),
      });
    }
  }, [patchSettingsMut, project.id, project.settings, trimmed, toast, t]);

  const handleClear = useCallback(() => {
    setDraft('');
  }, []);

  return (
    <div className="space-y-4 rounded-xl border border-border bg-surface-raised p-5">
      <div className="space-y-2">
        <h2 className="text-base font-semibold text-foreground">{t('petSpace.personalityTitle')}</h2>
        <p className="text-sm text-muted-foreground">
          {t('petSpace.personalityDescription', { max: PET_PERSONALITY_MAX_CHARS })}
        </p>
      </div>

      <Textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder={t('petSpace.personalityPlaceholder')}
        rows={12}
        maxLength={PET_PERSONALITY_MAX_CHARS + 200}
        className="font-mono text-sm leading-relaxed"
      />

      <div className="flex flex-col gap-1">
        <p className="text-xs text-muted-foreground">{t('petSpace.personalityHint')}</p>
        <p
          className={cn(
            'text-xs',
            overLimit ? 'text-red-600 dark:text-red-400' : 'text-muted-foreground',
          )}
        >
          {t('petSpace.personalityCharCount', {
            count: charCount,
            max: PET_PERSONALITY_MAX_CHARS,
          })}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          size="sm"
          onClick={handleSave}
          disabled={!canSave}
        >
          {patchSettingsMut.isPending ? t('petSpace.personalitySaving') : t('petSpace.personalitySave')}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={handleClear}
          disabled={draft.length === 0 || patchSettingsMut.isPending}
        >
          {t('petSpace.personalityClear')}
        </Button>
      </div>
    </div>
  );
}

function SpriteSheetGifTool({
  projectId,
  files,
  onDone,
}: {
  projectId: string;
  files: PetProjectFileRow[];
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const images = useMemo(() => files.filter((f) => isPetRenderableImageRow(f)), [files]);
  const [sourceId, setSourceId] = useState<string | null>(() => images[0]?.file_id ?? null);
  const [cols, setCols] = useState(4);
  const [rows, setRows] = useState(4);
  const [pad, setPad] = useState(0);
  const [fps, setFps] = useState(8);
  const [transparent, setTransparent] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewMeta, setPreviewMeta] = useState<SpriteSheetGifMeta | null>(null);
  const [sourceDims, setSourceDims] = useState<{ w: number; h: number } | null>(null);

  const srcRow = images.find((f) => f.file_id === sourceId) ?? null;

  useEffect(() => {
    if (!images.find((f) => f.file_id === sourceId) && images[0]) {
      setSourceId(images[0]!.file_id);
    }
  }, [images, sourceId]);

  useEffect(() => {
    const row = images.find((f) => f.file_id === sourceId) ?? null;
    if (!row) {
      setSourceDims(null);
      return;
    }
    let cancelled = false;
    let objectUrl: string | null = null;
    void (async () => {
      try {
        const blob = await fetchAuthedFilePreviewBlob(row.file_id, row.mime_type, row.original_name);
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        const img = await loadImageElement(objectUrl);
        if (!cancelled) setSourceDims({ w: img.naturalWidth, h: img.naturalHeight });
      } catch {
        if (!cancelled) setSourceDims(null);
      } finally {
        if (objectUrl) {
          URL.revokeObjectURL(objectUrl);
          objectUrl = null;
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [images, sourceId]);

  const uploadMut = useMutation({
    mutationFn: ({ pid, file }: { pid: string; file: File }) => petSpaceApi.uploadFile(pid, file),
    onSuccess: () => {
      onDone();
    },
  });

  const generate = async () => {
    setErr(null);
    const row = images.find((f) => f.file_id === sourceId) ?? null;
    if (!row) {
      setErr(t('petSpace.spriteNeedImage'));
      return;
    }
    let objectUrl: string | null = null;
    setBusy(true);
    try {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
        setPreviewUrl(null);
      }
      setPreviewMeta(null);
      const sourcePreviewBlob = await fetchAuthedFilePreviewBlob(
        row.file_id,
        row.mime_type,
        row.original_name,
      );
      objectUrl = URL.createObjectURL(sourcePreviewBlob);
      const img = await loadImageElement(objectUrl);
      const result = await spriteSheetToGifBlob(img, {
        cols,
        rows,
        pad,
        fps,
        transparent,
        loop: 0,
      });
      const { blob: gifBlob, ...meta } = result;
      setPreviewMeta(meta);
      setPreviewUrl(URL.createObjectURL(gifBlob));
    } catch (e) {
      setErr(String((e as Error)?.message ?? e));
    } finally {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      setBusy(false);
    }
  };

  const uploadGenerated = async () => {
    if (!previewUrl) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch(previewUrl);
      const blob = await res.blob();
      const file = new File([blob], 'pet-sprite.gif', { type: 'image/gif' });
      uploadMut.mutate({ pid: projectId, file });
    } catch (e) {
      setErr(String((e as Error)?.message ?? e));
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const spritePreviewScale = useMemo(
    () =>
      previewMeta
        ? Math.min(4, Math.max(1, Math.floor(288 / Math.max(previewMeta.frameWidth, previewMeta.frameHeight))))
        : 1,
    [previewMeta],
  );

  if (images.length === 0) {
    return (
      <p className="text-sm text-muted-foreground border border-dashed border-border rounded-xl p-4">
        {t('petSpace.spriteNoImages')}
      </p>
    );
  }

  return (
    <div className="rounded-xl border border-border p-4 space-y-4 bg-surface-sunken/20">
      <h3 className="text-sm font-semibold">{t('petSpace.spriteTitle')}</h3>
      <p className="text-xs text-muted-foreground">{t('petSpace.spriteIntro')}</p>
      <p className="text-xs text-muted-foreground-tertiary">{t('petSpace.spriteFormatsNote')}</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label className="text-xs space-y-1 block">
          <span className="text-muted-foreground">{t('petSpace.spriteSource')}</span>
          <select
            className="w-full rounded-lg border border-border bg-background px-2 py-1.5 text-sm"
            value={sourceId ?? images[0]?.file_id ?? ''}
            onChange={(e) => setSourceId(e.target.value || null)}
          >
            {images.map((f) => (
              <option key={f.id} value={f.file_id}>
                {f.original_name}
              </option>
            ))}
          </select>
        </label>
        <div className="grid grid-cols-2 gap-2">
          <label className="text-xs space-y-1 block">
            <span className="text-muted-foreground">{t('petSpace.spriteCols')}</span>
            <Input type="number" min={1} max={32} value={cols} onChange={(e) => setCols(+e.target.value || 1)} />
          </label>
          <label className="text-xs space-y-1 block">
            <span className="text-muted-foreground">{t('petSpace.spriteRows')}</span>
            <Input type="number" min={1} max={32} value={rows} onChange={(e) => setRows(+e.target.value || 1)} />
          </label>
          <label className="text-xs space-y-1 block">
            <span className="text-muted-foreground">{t('petSpace.spritePad')}</span>
            <Input type="number" min={0} max={64} value={pad} onChange={(e) => setPad(+e.target.value || 0)} />
          </label>
          <label className="text-xs space-y-1 block">
            <span className="text-muted-foreground">{t('petSpace.spriteFps')}</span>
            <Input type="number" min={1} max={60} value={fps} onChange={(e) => setFps(+e.target.value || 8)} />
          </label>
        </div>
      </div>
      {sourceDims ? (
        <div className="space-y-1 rounded-lg border border-border-subtle bg-background/50 px-2 py-2 text-xs text-muted-foreground">
          <p>
            {t('petSpace.spriteSourceDims', { w: sourceDims.w, h: sourceDims.h })}
            {' · '}
            {t('petSpace.spriteCellEstimate', {
              cols,
              rows,
              cw: Math.floor(sourceDims.w / cols),
              ch: Math.floor(sourceDims.h / rows),
            })}
            {' · '}
            {t('petSpace.spriteInnerEstimate', {
              iw: Math.max(0, Math.floor(sourceDims.w / cols) - pad * 2),
              ih: Math.max(0, Math.floor(sourceDims.h / rows) - pad * 2),
            })}
          </p>
          {sourceDims.w % cols !== 0 || sourceDims.h % rows !== 0 ? (
            <p className="text-amber-700 dark:text-amber-300">
              {t('petSpace.spriteGridRemainder', {
                rx: sourceDims.w % cols,
                ry: sourceDims.h % rows,
              })}
            </p>
          ) : null}
        </div>
      ) : null}
      <div className="space-y-1">
        <label className="flex items-center gap-2 text-xs cursor-pointer">
          <input type="checkbox" checked={transparent} onChange={(e) => setTransparent(e.target.checked)} />
          {t('petSpace.spriteTransparent')}
        </label>
        <p className="text-[11px] text-muted-foreground leading-snug pl-5">{t('petSpace.spriteAlphaNote')}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button type="button" size="sm" disabled={busy || !srcRow} onClick={() => void generate()}>
          {t('petSpace.spriteGenerate')}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={busy || !previewUrl || uploadMut.isPending}
          onClick={() => void uploadGenerated()}
        >
          {t('petSpace.spriteUpload')}
        </Button>
      </div>
      {err ? <p className="text-xs text-red-600">{err}</p> : null}
      {previewUrl && previewMeta ? (
        <div className="space-y-2">
          <p className="text-xs text-muted-foreground">
            {t('petSpace.spritePreviewOut', {
              fw: previewMeta.frameWidth,
              fh: previewMeta.frameHeight,
              n: previewMeta.frameCount,
            })}
          </p>
          <div className="inline-block rounded-lg border border-border-subtle bg-muted/30 p-1 dark:bg-muted/20">
            <img
              key={previewUrl}
              src={previewUrl}
              alt=""
              className="block rounded-md border border-border-subtle bg-transparent"
              style={{
                width: previewMeta.frameWidth * spritePreviewScale,
                height: previewMeta.frameHeight * spritePreviewScale,
                imageRendering: 'pixelated',
              }}
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default function PetSpacePage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const reduceMotion = usePrefersReducedMotion();
  const [tab, setTab] = useState<TabId>('customize');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [simulateCustomizeStream, setSimulateCustomizeStream] = useState(false);
  const [actionPreviewId, setActionPreviewId] = useState<PetActionPreviewId>('current');
  const [showActionCss, setShowActionCss] = useState(false);
  const [projectNameEditing, setProjectNameEditing] = useState(false);
  const [nameDraft, setNameDraft] = useState('');

  const invalidateDock = () => {
    void qc.invalidateQueries({ queryKey: ['pet-space', 'dock'] });
  };

  const projectsQuery = useQuery({
    queryKey: ['pet-space', 'projects'],
    queryFn: petSpaceApi.listProjects,
    staleTime: 30_000,
  });

  const presetManifestQuery = useQuery({
    queryKey: ['pet-space', 'preset-manifest'],
    queryFn: loadPetPresetManifest,
    staleTime: Number.POSITIVE_INFINITY,
  });

  const projects = projectsQuery.data ?? [];
  const activeProjectId = useMemo(() => {
    if (projects.length === 0) return null;
    if (selectedId != null && projects.some((p) => p.id === selectedId)) return selectedId;
    return projects[0]!.id;
  }, [projects, selectedId]);
  const activeProject = useMemo(
    () => (activeProjectId ? projects.find((p) => p.id === activeProjectId) ?? null : null),
    [projects, activeProjectId],
  );

  useEffect(() => {
    if (projects.length === 0) {
      setSelectedId(null);
      return;
    }
    if (selectedId == null || !projects.some((p) => p.id === selectedId)) {
      setSelectedId(projects[0]!.id);
    }
  }, [projects, selectedId]);

  const setDockPreviewProjectId = usePetSpaceUiStore((s) => s.setDockPreviewProjectId);
  useEffect(() => {
    setDockPreviewProjectId(activeProjectId);
    return () => setDockPreviewProjectId(null);
  }, [activeProjectId, setDockPreviewProjectId]);

  const fileListId = activeProjectId;

  const filesQuery = useQuery({
    queryKey: ['pet-space', 'files', fileListId],
    queryFn: () => petSpaceApi.listFiles(fileListId!),
    enabled: !!fileListId && (tab === 'customize' || tab === 'library' || tab === 'showroom' || tab === 'studio'),
    staleTime: 15_000,
  });

  const listedFiles = filesQuery.data ?? [];
  const primaryParsed = useMemo(() => parsePetSettings(activeProject?.settings), [activeProject?.settings]);
  const appearanceFileId =
    typeof primaryParsed.appearance_file_id === 'string' ? primaryParsed.appearance_file_id : null;
  const heroBuiltin = isPetBuiltinAppearance(primaryParsed.appearance_builtin)
    ? primaryParsed.appearance_builtin
    : null;
  const nestResolved = resolvedNest(primaryParsed);
  const nestDockFloorUi = useMemo(
    () =>
      Math.min(
        DOCK_FLOOR_Y_MAX,
        Math.max(DOCK_FLOOR_Y_MIN, Math.round(nestResolved.dockFloorYPx ?? DEFAULT_DOCK_FLOOR_Y_PX)),
      ),
    [nestResolved.dockFloorYPx],
  );
  const nestDockShadowUi = useMemo(
    () =>
      Math.min(
        DOCK_SHADOW_OFFSET_Y_MAX,
        Math.max(
          DOCK_SHADOW_OFFSET_Y_MIN,
          Math.round(nestResolved.dockShadowOffsetYPx ?? DEFAULT_DOCK_SHADOW_OFFSET_Y_PX),
        ),
      ),
    [nestResolved.dockShadowOffsetYPx],
  );
  const behaviorResolved = resolvedBehavior(primaryParsed);
  const heroPreviewId =
    heroBuiltin
      ? null
      : appearanceFileId && listedFiles.some((f) => f.file_id === appearanceFileId)
        ? appearanceFileId
        : listedFiles.find((f) => isPetRenderableImageRow(f))?.file_id ?? null;
  const heroFileRow = heroPreviewId ? listedFiles.find((f) => f.file_id === heroPreviewId) ?? null : null;
  const heroMime = heroFileRow
    ? effectivePetImageMime(heroFileRow.mime_type, heroFileRow.original_name)
    : null;
  const { url: heroBlobUrl, isPending: heroMainBlobPending } = useAuthedFileBlobUrl(
    heroPreviewId,
    heroMime,
    heroFileRow?.original_name ?? null,
  );
  const heroSrc = heroBuiltin ? builtinPetSvgUrl(heroBuiltin) : heroBlobUrl;
  const currentRuntimeVisual = resolvePetVisual({
    behavior: behaviorResolved,
    reduceMotion,
    isStreaming: simulateCustomizeStream,
    happyFlash: false,
  });
  const heroPreviewInput =
    actionPreviewId === 'current'
      ? { behavior: behaviorResolved, isStreaming: simulateCustomizeStream, happyFlash: false }
      : previewInputForVisual(actionPreviewId, behaviorResolved);
  const heroVisual = resolvePetVisual({
    behavior: heroPreviewInput.behavior,
    reduceMotion,
    isStreaming: heroPreviewInput.isStreaming,
    happyFlash: heroPreviewInput.happyFlash,
  });
  const heroClip = usePetClipResolver({
    settings: primaryParsed,
    files: listedFiles,
    visual: heroVisual,
    idleAnimation: heroPreviewInput.behavior.idleAnimation,
  });
  const usingHeroClip = heroClip.isClipDrawable && Boolean(heroClip.displaySrc);
  const heroDisplaySrc = usingHeroClip ? (heroClip.displaySrc as string) : heroSrc;
  const effectiveHeroMime = usingHeroClip
    ? heroClip.displayMime
    : heroBuiltin
      ? null
      : heroMime;
  const heroHasBuiltin = usingHeroClip
    ? Boolean(heroClip.activeClip?.binding.builtin)
    : Boolean(heroBuiltin);
  const heroGifBind = appearanceGifBindMotionActive(
    primaryParsed,
    effectiveHeroMime,
    heroHasBuiltin,
  );
  const clipOverride =
    usingHeroClip && heroClip.activeClip && heroClip.activeClip.binding.overrideCssMotion !== false;
  const heroMotionClass = pickPetClipAppearanceClass(heroVisual, heroPreviewInput.behavior, reduceMotion, {
    clipActive: usingHeroClip,
    clipOverride: Boolean(clipOverride),
    gifBindForDisplayedAsset: heroGifBind,
  });
  const heroMotionStyle =
    usingHeroClip && heroClip.activeClip
      ? petClipMotionStyleVars(heroPreviewInput.behavior, true, heroClip.activeClip.binding.speed)
      : petMotionStyleVars(heroPreviewInput.behavior);
  const heroClipMirror = usingHeroClip && heroClip.activeClip?.binding.mirror;
  const heroObjectFit = usingHeroClip && heroClip.activeClip?.binding?.fit === 'cover' ? 'object-cover' : 'object-contain';
  const heroAppearanceLoading = Boolean(
    (!heroBuiltin && heroPreviewId && heroMainBlobPending) || heroClip.clipFileBlobPending,
  );
  const actionRows = useMemo(
    () =>
      PET_ACTION_VISUALS.map((visual) => {
        const input = previewInputForVisual(visual, behaviorResolved);
        const resolved = resolvePetVisual({
          behavior: input.behavior,
          reduceMotion: false,
          isStreaming: input.isStreaming,
          happyFlash: input.happyFlash,
        });
        return {
          visual,
          cssClass: pickPetMotionClass(resolved, input.behavior, false),
        };
      }),
    [behaviorResolved],
  );
  const heroSceneContext = useMemo(
    () =>
      activeProject
        ? {
            settings: primaryParsed,
            projectFiles: listedFiles,
            previewFileId: heroPreviewId,
            mimeType: heroMime,
            appearanceBuiltin: heroBuiltin,
            appearancePreviewOriginalName: heroFileRow?.original_name ?? null,
          }
        : null,
    [activeProject, primaryParsed, listedFiles, heroPreviewId, heroMime, heroBuiltin, heroFileRow?.original_name],
  );
  const activeManifestPet = findPresetManifestPet(presetManifestQuery.data, heroBuiltin);

  const createMut = useMutation({
    mutationFn: (name: string) => petSpaceApi.createProject({ name }),
    onSuccess: (created) => {
      void qc.invalidateQueries({ queryKey: ['pet-space', 'projects'] });
      invalidateDock();
      setCreateOpen(false);
      setNewName('');
      setSelectedId(created.id);
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => petSpaceApi.deleteProject(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['pet-space', 'projects'] });
      invalidateDock();
    },
  });

  const renameMut = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => petSpaceApi.updateProject(id, { name }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['pet-space', 'projects'] });
      invalidateDock();
    },
  });

  const uploadMut = useMutation({
    mutationFn: ({ pid, file }: { pid: string; file: File }) => petSpaceApi.uploadFile(pid, file),
    onSuccess: (_, vars) => {
      void qc.invalidateQueries({ queryKey: ['pet-space', 'files', vars.pid] });
      void qc.invalidateQueries({ queryKey: ['pet-space', 'projects'] });
      invalidateDock();
    },
  });

  const deleteFileMut = useMutation({
    mutationFn: async ({
      projectId,
      fileId,
      baseSettings,
    }: {
      projectId: string;
      fileId: string;
      baseSettings: string | null | undefined;
    }) => {
      const parsed = parsePetSettings(baseSettings);
      const nest = resolvedNest(parsed);
      const patch: Partial<Omit<PetSettings, 'clips'>> & { clips?: PetSettingsClipPatch } = {};
      if (parsed.appearance_file_id === fileId) {
        patch.appearance_file_id = null;
      }
      if (nest.backgroundFileId === fileId) {
        patch.nest = { backgroundFileId: null };
      }
      const clipPatch: PetSettingsClipPatch = {};
      if (parsed.clips) {
        for (const k of Object.keys(parsed.clips) as PetClipState[]) {
          if (parsed.clips[k]?.fileId === fileId) {
            clipPatch[k] = { fileId: null, builtin: null };
          }
        }
      }
      if (Object.keys(clipPatch).length > 0) {
        patch.clips = clipPatch;
      }
      if (Object.keys(patch).length > 0) {
        await petSpaceApi.updateProject(projectId, { settings: mergePetSettings(baseSettings, patch) });
      }
      await petSpaceApi.deleteFile(fileId);
    },
    onSuccess: (_, vars) => {
      void qc.invalidateQueries({ queryKey: ['pet-space', 'files', vars.projectId] });
      void qc.invalidateQueries({ queryKey: ['pet-space', 'projects'] });
      invalidateDock();
    },
  });

  const setAppearanceMut = useMutation({
    mutationFn: async ({
      projectId,
      fileId,
      baseSettings,
    }: {
      projectId: string;
      fileId: string;
      baseSettings: string | null | undefined;
    }) => {
      const settings = mergePetSettings(baseSettings, { appearance_file_id: fileId });
      return petSpaceApi.updateProject(projectId, { settings });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['pet-space', 'projects'] });
      void qc.invalidateQueries({ queryKey: ['pet-space', 'files'] });
      invalidateDock();
    },
  });

  const patchSettingsMut = useMutation({
    mutationFn: ({
      projectId,
      baseSettings,
      patch,
    }: {
      projectId: string;
      baseSettings: string | null | undefined;
      patch: Partial<Omit<PetSettings, 'clips'>> & { clips?: PetSettingsClipPatch };
    }) => petSpaceApi.updateProject(projectId, { settings: mergePetSettings(baseSettings, patch) }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['pet-space', 'projects'] });
      invalidateDock();
    },
  });

  const [accentDraft, setAccentDraft] = useState(nestResolved.accent);
  useEffect(() => {
    setAccentDraft(nestResolved.accent);
  }, [nestResolved.accent, activeProject?.id]);

  useEffect(() => {
    if (activeProject) {
      setNameDraft(activeProject.name);
    }
  }, [activeProject?.id, activeProject?.name]);

  const commitProjectName = useCallback(() => {
    if (!activeProject) return;
    const next = nameDraft.trim();
    if (!next || next === activeProject.name) {
      setNameDraft(activeProject.name);
      setProjectNameEditing(false);
      return;
    }
    renameMut.mutate(
      { id: activeProject.id, name: next },
      {
        onSuccess: () => setProjectNameEditing(false),
        onError: () => setNameDraft(activeProject.name),
      },
    );
  }, [activeProject, nameDraft, renameMut]);

  const onPickFile = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>, pid: string) => {
      const f = e.target.files?.[0];
      if (!f || !pid) return;
      uploadMut.mutate({ pid, file: f });
      e.target.value = '';
    },
    [uploadMut],
  );

  const tabs = useMemo(
    () =>
      [
        { id: 'customize' as const, label: t('petSpace.navCustomize') },
        { id: 'studio' as const, label: t('petSpace.navStudio') },
        { id: 'showroom' as const, label: t('petSpace.navShowroom') },
        { id: 'personality' as const, label: t('petSpace.navPersonality') },
        { id: 'library' as const, label: t('petSpace.navLibrary') },
        { id: 'about' as const, label: t('petSpace.navAbout') },
      ] as const,
    [t],
  );

  return (
    <PageShell title={t('petSpace.title')} description={t('petSpace.description')}>
      <div className="flex flex-col gap-6">
        <div className="flex flex-wrap gap-1 border-b border-border pb-2">
          {tabs.map((x) => (
            <button
              key={x.id}
              type="button"
              onClick={() => setTab(x.id)}
              className={cn(
                'px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
                tab === x.id
                  ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300'
                  : 'text-muted-foreground hover:bg-surface-sunken hover:text-foreground',
              )}
            >
              {x.label}
            </button>
          ))}
        </div>

        {projectsQuery.isError && (
          <p className="text-sm text-red-600 dark:text-red-400">{t('petSpace.loadError')}</p>
        )}

        {tab === 'customize' && (
          <div className="space-y-6 max-w-4xl">
            {!activeProject ? (
              <div className="rounded-xl border border-dashed border-border p-6 text-center space-y-3">
                <p className="text-sm text-muted-foreground">{t('petSpace.customizeNoProject')}</p>
                {!createOpen ? (
                  <Button size="sm" leftIcon={<Plus className="w-4 h-4" />} onClick={() => setCreateOpen(true)}>
                    {t('petSpace.newProject')}
                  </Button>
                ) : (
                  <div className="flex flex-col sm:flex-row gap-2 justify-center items-stretch sm:items-center max-w-md mx-auto">
                    <Input
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      placeholder={t('petSpace.projectName')}
                    />
                    <div className="flex gap-2 justify-center">
                      <Button variant="outline" size="sm" onClick={() => setCreateOpen(false)}>
                        {t('petSpace.cancel')}
                      </Button>
                      <Button
                        size="sm"
                        disabled={!newName.trim() || createMut.isPending}
                        onClick={() => createMut.mutate(newName.trim())}
                      >
                        {t('petSpace.create')}
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <>
                <div className="rounded-2xl border border-border bg-surface-sunken/30 p-6 flex flex-col sm:flex-row gap-6 items-center">
                  <div className="flex h-36 w-36 shrink-0 items-center justify-center overflow-visible rounded-2xl border border-border-subtle bg-background shadow-inner">
                    {actionPreviewId === 'current' && heroSceneContext ? (
                      <PetSceneStage surface="hero" projectContext={heroSceneContext} className="h-full w-full" />
                    ) : heroDisplaySrc ? (
                      heroClipMirror ? (
                        <span className="inline-flex h-full w-full max-h-full max-w-full items-center justify-center scale-x-[-1]">
                          <img
                            src={heroDisplaySrc}
                            alt=""
                            className={cn(
                              'w-full h-full bg-white/90 dark:bg-slate-900/80',
                              heroObjectFit,
                              heroMotionClass,
                            )}
                            style={heroMotionStyle}
                          />
                        </span>
                      ) : (
                        <img
                          src={heroDisplaySrc}
                          alt=""
                          className={cn(
                            'w-full h-full bg-white/90 dark:bg-slate-900/80',
                            usingHeroClip ? heroObjectFit : 'object-cover',
                            heroMotionClass,
                          )}
                          style={heroMotionStyle}
                        />
                      )
                    ) : heroAppearanceLoading ? (
                      <span className={heroMotionClass} style={heroMotionStyle} aria-hidden />
                    ) : (
                      <span className={heroMotionClass} style={heroMotionStyle}>
                        <BrandMascot size="lg" staticFallback={reduceMotion} />
                      </span>
                    )}
                  </div>
                  <div className="flex-1 min-w-0 space-y-3">
                    <div className="flex flex-wrap items-center gap-2 min-w-0">
                      {projectNameEditing ? (
                        <div className="flex flex-wrap items-center gap-2 flex-1 min-w-0">
                          <Input
                            value={nameDraft}
                            onChange={(e) => setNameDraft(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                e.preventDefault();
                                commitProjectName();
                              }
                              if (e.key === 'Escape') {
                                setNameDraft(activeProject.name);
                                setProjectNameEditing(false);
                              }
                            }}
                            disabled={renameMut.isPending}
                            className="max-w-md"
                            autoFocus
                            aria-label={t('petSpace.projectName')}
                          />
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            disabled={renameMut.isPending}
                            onClick={() => {
                              setNameDraft(activeProject.name);
                              setProjectNameEditing(false);
                            }}
                          >
                            {t('petSpace.cancel')}
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            disabled={renameMut.isPending || !nameDraft.trim()}
                            onClick={() => commitProjectName()}
                          >
                            {t('petSpace.rename')}
                          </Button>
                        </div>
                      ) : (
                        <>
                          <h2
                            className="text-lg font-semibold text-foreground cursor-pointer hover:underline decoration-dotted underline-offset-4 min-w-0 truncate"
                            title={t('petSpace.projectNameEditHint')}
                            onClick={() => setProjectNameEditing(true)}
                          >
                            {activeProject.name}
                          </h2>
                          <button
                            type="button"
                            className="shrink-0 p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-surface-sunken transition-colors"
                            title={t('petSpace.projectNameEditHint')}
                            aria-label={t('petSpace.rename')}
                            onClick={() => setProjectNameEditing(true)}
                          >
                            <Edit2 className="w-4 h-4" />
                          </button>
                        </>
                      )}
                    </div>
                    <p className="text-sm text-muted-foreground">{t('petSpace.customizeIntro')}</p>
                    <label
                      className={cn(
                        'inline-flex items-center justify-center rounded-lg font-medium text-sm px-4 py-2 cursor-pointer transition-colors',
                        PRIMARY_SOFT_CTA_CLASSNAME,
                      )}
                    >
                      <input
                        type="file"
                        className="sr-only"
                        accept="image/png,image/jpeg,image/jpg,image/webp,image/gif,image/svg+xml,.png,.jpg,.jpeg,.webp,.gif,.svg"
                        onChange={(e) => onPickFile(e, activeProject.id)}
                      />
                      {t('petSpace.uploadProject')}
                    </label>
                    {uploadMut.isError && (
                      <p className="text-xs text-red-600">{String((uploadMut.error as Error)?.message)}</p>
                    )}
                  </div>
                </div>

                <div className="rounded-xl border border-border p-4 space-y-4">
                  <h3 className="text-sm font-semibold">{t('petSpace.nestTitle')}</h3>
                  <p className="text-xs text-muted-foreground">{t('petSpace.nestIntro')}</p>
                  <div className="flex flex-wrap gap-2">
                    {NEST_THEMES.map((tid) => (
                      <button
                        key={tid}
                        type="button"
                        disabled={patchSettingsMut.isPending}
                        onClick={() =>
                          patchSettingsMut.mutate({
                            projectId: activeProject.id,
                            baseSettings: activeProject.settings,
                            patch: { nest: { themeId: tid } },
                          })
                        }
                        className={cn(
                          'px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors',
                          nestResolved.themeId === tid
                            ? 'border-primary-500 bg-primary-50 dark:bg-primary-950/40 text-primary-800 dark:text-primary-200'
                            : 'border-border-subtle bg-surface-sunken/50 hover:bg-surface-sunken',
                        )}
                      >
                        {t(`petSpace.nestTheme.${tid}`)}
                      </button>
                    ))}
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <label className="text-xs space-y-1.5 block">
                      <span className="text-muted-foreground">{t('petSpace.nestAccent')}</span>
                      <div className="flex gap-2 items-center">
                        <input
                          type="color"
                          aria-label={t('petSpace.nestAccent')}
                          className="h-9 w-12 cursor-pointer rounded border border-border-subtle bg-background p-0.5"
                          value={/^#[0-9A-Fa-f]{6}$/.test(accentDraft) ? accentDraft : '#0284c7'}
                          onChange={(e) => setAccentDraft(e.target.value)}
                        />
                        <Input
                          value={accentDraft}
                          onChange={(e) => setAccentDraft(e.target.value)}
                          onBlur={() => {
                            if (accentDraft === nestResolved.accent) return;
                            patchSettingsMut.mutate({
                              projectId: activeProject.id,
                              baseSettings: activeProject.settings,
                              patch: { nest: { accent: accentDraft } },
                            });
                          }}
                          className="text-sm font-mono"
                        />
                      </div>
                    </label>
                    <label className="text-xs space-y-1.5 block">
                      <span className="text-muted-foreground">{t('petSpace.nestBackground')}</span>
                      <select
                        className="w-full rounded-lg border border-border bg-background px-2 py-2 text-sm"
                        value={nestResolved.backgroundFileId ?? ''}
                        onChange={(e) => {
                          const v = e.target.value;
                          patchSettingsMut.mutate({
                            projectId: activeProject.id,
                            baseSettings: activeProject.settings,
                            patch: { nest: { backgroundFileId: v ? v : null } },
                          });
                        }}
                      >
                        <option value="">{t('petSpace.nestBackgroundNone')}</option>
                        {listedFiles
                          .filter((f) => isPetRenderableImageRow(f))
                          .map((f) => (
                            <option key={f.id} value={f.file_id}>
                              {f.original_name}
                            </option>
                          ))}
                      </select>
                    </label>
                  </div>
                  <div className="mt-4 space-y-4 border-t border-border-subtle pt-4">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <label className="text-xs space-y-1.5 block">
                        <span className="text-muted-foreground">{t('petSpace.nestBackgroundFit')}</span>
                        <select
                          className="w-full rounded-lg border border-border bg-background px-2 py-2 text-sm"
                          value={nestResolved.backgroundFit ?? 'cover'}
                          disabled={patchSettingsMut.isPending}
                          onChange={(e) =>
                            patchSettingsMut.mutate({
                              projectId: activeProject.id,
                              baseSettings: activeProject.settings,
                              patch: {
                                nest: { backgroundFit: e.target.value as NestBackgroundFit },
                              },
                            })
                          }
                        >
                          {NEST_BACKGROUND_FITS.map((fit) => (
                            <option key={fit} value={fit}>
                              {t(`petSpace.nestBackgroundFitOption.${fit}`)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="text-xs space-y-1.5 block">
                        <span className="text-muted-foreground">{t('petSpace.nestBackgroundPosition')}</span>
                        <select
                          className="w-full rounded-lg border border-border bg-background px-2 py-2 text-sm"
                          value={nestResolved.backgroundPosition ?? 'center'}
                          disabled={patchSettingsMut.isPending}
                          onChange={(e) =>
                            patchSettingsMut.mutate({
                              projectId: activeProject.id,
                              baseSettings: activeProject.settings,
                              patch: {
                                nest: { backgroundPosition: e.target.value as NestBackgroundPosition },
                              },
                            })
                          }
                        >
                          {NEST_BACKGROUND_POSITIONS.map((pos) => (
                            <option key={pos} value={pos}>
                              {t(`petSpace.nestBackgroundPositionOption.${pos}`)}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                    <label className="text-xs space-y-2 block">
                      <span className="text-muted-foreground">
                        {t('petSpace.nestBackgroundOpacity')}:{' '}
                        {Math.round((nestResolved.backgroundOpacity ?? 0.25) * 100)}%
                      </span>
                      <input
                        type="range"
                        min={0}
                        max={1}
                        step={0.05}
                        value={nestResolved.backgroundOpacity ?? 0.25}
                        disabled={patchSettingsMut.isPending}
                        onChange={(e) =>
                          patchSettingsMut.mutate({
                            projectId: activeProject.id,
                            baseSettings: activeProject.settings,
                            patch: { nest: { backgroundOpacity: Number(e.target.value) } },
                          })
                        }
                        className="w-full h-2 accent-primary-600"
                      />
                    </label>
                    <div className="space-y-4">
                      <div className="space-y-2">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="text-xs text-muted-foreground">
                            {t('petSpace.nestDockFloorY')}: {nestDockFloorUi}px
                          </span>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="h-7 shrink-0 px-2.5 text-xs"
                            disabled={
                              patchSettingsMut.isPending ||
                              ((nestResolved.dockFloorYPx ?? DEFAULT_DOCK_FLOOR_Y_PX) ===
                                DEFAULT_DOCK_FLOOR_Y_PX &&
                                (nestResolved.dockShadowOffsetYPx ?? DEFAULT_DOCK_SHADOW_OFFSET_Y_PX) ===
                                  DEFAULT_DOCK_SHADOW_OFFSET_Y_PX)
                            }
                            onClick={() =>
                              patchSettingsMut.mutate({
                                projectId: activeProject.id,
                                baseSettings: activeProject.settings,
                                patch: {
                                  nest: {
                                    dockFloorYPx: DEFAULT_DOCK_FLOOR_Y_PX,
                                    dockShadowOffsetYPx: DEFAULT_DOCK_SHADOW_OFFSET_Y_PX,
                                  },
                                },
                              })
                            }
                          >
                            {t('petSpace.nestDockFloorYReset')}
                          </Button>
                        </div>
                        <p className="text-xs text-muted-foreground leading-snug">
                          {t('petSpace.nestDockFloorYHint')}
                        </p>
                        <input
                          type="range"
                          min={DOCK_FLOOR_Y_MIN}
                          max={DOCK_FLOOR_Y_MAX}
                          step={1}
                          value={nestDockFloorUi}
                          disabled={patchSettingsMut.isPending}
                          aria-label={t('petSpace.nestDockFloorY')}
                          onChange={(e) =>
                            patchSettingsMut.mutate({
                              projectId: activeProject.id,
                              baseSettings: activeProject.settings,
                              patch: {
                                nest: {
                                  dockFloorYPx: Math.min(
                                    DOCK_FLOOR_Y_MAX,
                                    Math.max(DOCK_FLOOR_Y_MIN, Number(e.target.value)),
                                  ),
                                },
                              },
                            })
                          }
                          className="w-full h-2 accent-primary-600"
                        />
                      </div>
                      <div className="space-y-2">
                        <span className="text-xs text-muted-foreground">
                          {t('petSpace.nestDockShadowOffsetY')}: {nestDockShadowUi}px
                        </span>
                        <p className="text-xs text-muted-foreground leading-snug">
                          {t('petSpace.nestDockShadowOffsetYHint')}
                        </p>
                        <input
                          type="range"
                          min={DOCK_SHADOW_OFFSET_Y_MIN}
                          max={DOCK_SHADOW_OFFSET_Y_MAX}
                          step={1}
                          value={nestDockShadowUi}
                          disabled={patchSettingsMut.isPending}
                          aria-label={t('petSpace.nestDockShadowOffsetY')}
                          onChange={(e) =>
                            patchSettingsMut.mutate({
                              projectId: activeProject.id,
                              baseSettings: activeProject.settings,
                              patch: {
                                nest: {
                                  dockShadowOffsetYPx: Math.min(
                                    DOCK_SHADOW_OFFSET_Y_MAX,
                                    Math.max(DOCK_SHADOW_OFFSET_Y_MIN, Number(e.target.value)),
                                  ),
                                },
                              },
                            })
                          }
                          className="w-full h-2 accent-primary-600"
                        />
                      </div>
                    </div>
                    <label className="text-xs space-y-1.5 block max-w-md">
                      <span className="text-muted-foreground">{t('petSpace.nestBackgroundPattern')}</span>
                      <select
                        className="w-full rounded-lg border border-border bg-background px-2 py-2 text-sm"
                        value={nestResolved.backgroundPattern ?? 'none'}
                        disabled={patchSettingsMut.isPending}
                        onChange={(e) =>
                          patchSettingsMut.mutate({
                            projectId: activeProject.id,
                            baseSettings: activeProject.settings,
                            patch: {
                              nest: { backgroundPattern: e.target.value as NestBackgroundPattern },
                            },
                          })
                        }
                      >
                        <option value="none">{t('petSpace.nestPattern.none')}</option>
                        <option value="dots">{t('petSpace.nestPattern.dots')}</option>
                        <option value="grid">{t('petSpace.nestPattern.grid')}</option>
                        <option value="noise">{t('petSpace.nestPattern.noise')}</option>
                      </select>
                    </label>
                  </div>
                </div>

                <div className="rounded-xl border border-border p-4 space-y-3">
                  <h3 className="text-sm font-semibold">{t('petSpace.behaviorTitle')}</h3>
                  <p className="text-xs text-muted-foreground">{t('petSpace.behaviorIntro')}</p>
                  <details className="group rounded-lg border border-border-subtle bg-surface-sunken/20 [&_summary]:outline-none [&_summary]:focus-visible:ring-2 [&_summary]:focus-visible:ring-primary-500/30 [&_summary]:rounded-lg">
                    <summary className="cursor-pointer list-none flex items-center gap-2.5 rounded-lg px-2 py-2 hover:bg-surface-sunken/50 transition-colors [&::-webkit-details-marker]:hidden">
                      <ChevronDown
                        className="w-4 h-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180"
                        aria-hidden
                      />
                      <div className="min-w-0 flex-1">
                        <span className="block text-sm font-semibold text-foreground">{t('petSpace.actionTitle')}</span>
                        <span className="block text-xs text-muted-foreground truncate">
                          {t('petSpace.actionSummaryLine')}
                        </span>
                      </div>
                    </summary>
                    <div className="mt-2 space-y-3 border-t border-border-subtle pt-3">
                      <p className="text-xs text-muted-foreground leading-snug line-clamp-2" title={t('petSpace.actionIntro')}>
                        {t('petSpace.actionIntro')}
                      </p>
                      <label className="text-xs space-y-1 block w-full max-w-md">
                        <span className="text-muted-foreground block mb-1">{t('petSpace.actionPreview')}</span>
                        <select
                          className="w-full rounded-lg border border-border bg-background px-2 py-2 text-sm"
                          value={actionPreviewId}
                          onChange={(e) => setActionPreviewId(e.target.value as PetActionPreviewId)}
                        >
                          <option value="current">{t('petSpace.actionPreviewCurrent')}</option>
                          {PET_ACTION_VISUALS.map((visual) => (
                            <option key={visual} value={visual}>
                              {t(`petSpace.actionState.${visual}.name`)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <div className="flex items-center justify-end">
                        <button
                          type="button"
                          className="text-xs font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300"
                          onClick={() => setShowActionCss((v) => !v)}
                        >
                          {showActionCss ? t('petSpace.actionHideCss') : t('petSpace.actionShowCss')}
                        </button>
                      </div>
                      <div className="rounded-lg border border-border-subtle overflow-hidden">
                        <table className="w-full text-xs">
                          <thead>
                            <tr className="text-left text-muted-foreground border-b border-border-subtle bg-surface-sunken/40">
                              <th className="py-1.5 px-2 font-medium w-[32%]">{t('petSpace.actionStateColumn')}</th>
                              <th className="py-1.5 px-2 font-medium">{t('petSpace.actionDetailsColumn')}</th>
                              {showActionCss ? (
                                <th className="py-1.5 px-2 font-medium w-[28%]">{t('petSpace.actionCssColumn')}</th>
                              ) : null}
                            </tr>
                          </thead>
                          <tbody>
                            {actionRows.map((row) => {
                              const isRuntimeState = currentRuntimeVisual === row.visual;
                              const isPreviewState =
                                actionPreviewId === 'current' ? isRuntimeState : actionPreviewId === row.visual;
                              return (
                                <tr
                                  key={row.visual}
                                  className={cn(
                                    'border-b border-border-subtle last:border-0',
                                    isPreviewState && 'bg-primary-50/70 dark:bg-primary-950/25',
                                  )}
                                >
                                  <td className="py-1.5 px-2 align-top font-medium text-foreground">
                                    <div className="flex flex-wrap items-center gap-1.5">
                                      <span>{t(`petSpace.actionState.${row.visual}.name`)}</span>
                                      {isRuntimeState ? (
                                        <span className="rounded bg-primary-100 px-1.5 py-0.5 text-[10px] font-medium text-primary-800 dark:bg-primary-900/50 dark:text-primary-200">
                                          {t('petSpace.actionRuntimeBadge')}
                                        </span>
                                      ) : null}
                                    </div>
                                  </td>
                                  <td className="py-1.5 px-2 align-top text-muted-foreground leading-snug">
                                    <span className="block">{t(`petSpace.actionState.${row.visual}.trigger`)}</span>
                                    <span className="mt-0.5 block text-[10px] text-muted-foreground/90">
                                      {t(`petSpace.actionState.${row.visual}.binding`)}
                                    </span>
                                  </td>
                                  {showActionCss ? (
                                    <td className="py-1.5 px-2 align-top">
                                      <code className="text-[10px] text-muted-foreground break-all">{row.cssClass}</code>
                                    </td>
                                  ) : null}
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                      {heroBuiltin ? (
                        <div className="rounded-lg border border-border-subtle bg-background/60 p-2 space-y-2">
                          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                            <div className="min-w-0 space-y-0.5">
                              <h4 className="text-xs font-semibold text-foreground">
                                {t('petSpace.actionSupportedTitle')}
                              </h4>
                              <p className="text-[11px] text-muted-foreground leading-snug line-clamp-2">
                                {t('petSpace.actionSupportedIntro')}
                              </p>
                            </div>
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              className="shrink-0 self-start sm:self-center"
                              disabled={patchSettingsMut.isPending || !activeManifestPet?.motionDefaults}
                              onClick={() => {
                                if (!activeManifestPet?.motionDefaults) return;
                                patchSettingsMut.mutate({
                                  projectId: activeProject.id,
                                  baseSettings: activeProject.settings,
                                  patch: { behavior: activeManifestPet.motionDefaults },
                                });
                              }}
                            >
                              {t('petSpace.actionApplyMotionDefaults')}
                            </Button>
                          </div>
                          {presetManifestQuery.isError ? (
                            <p className="text-[11px] text-muted-foreground">{t('petSpace.actionManifestUnavailable')}</p>
                          ) : activeManifestPet ? (
                            <div className="flex flex-wrap gap-1.5">
                              {activeManifestPet.supportedStates.map((state) => {
                                const kind = presetStateKind(state);
                                const label =
                                  kind.kind === 'visual'
                                    ? t(`petSpace.actionState.${kind.visual}.name`)
                                    : kind.kind === 'idle'
                                      ? t(`petSpace.idleAnimation.${kind.idle}`)
                                      : state;
                                return (
                                  <span
                                    key={state}
                                    className="inline-flex max-w-full items-center gap-1 rounded-md border border-border-subtle bg-surface-sunken/40 px-1.5 py-0.5 text-[10px] text-muted-foreground"
                                  >
                                    <span className="truncate font-medium text-foreground">{label}</span>
                                    <span className="shrink-0 opacity-80">{t(`petSpace.actionStateKind.${kind.kind}`)}</span>
                                  </span>
                                );
                              })}
                            </div>
                          ) : (
                            <p className="text-[11px] text-muted-foreground">{t('petSpace.actionManifestUnavailable')}</p>
                          )}
                        </div>
                      ) : null}
                    </div>
                  </details>
                  <div className="flex flex-wrap gap-3 items-end">
                    <label className="text-xs space-y-1 block">
                      <span className="text-muted-foreground block mb-1">{t('petSpace.behaviorMode')}</span>
                      <select
                        className="rounded-lg border border-border bg-background px-2 py-1.5 text-sm min-w-[140px]"
                        value={behaviorResolved.mode}
                        disabled={patchSettingsMut.isPending}
                        onChange={(e) =>
                          patchSettingsMut.mutate({
                            projectId: activeProject.id,
                            baseSettings: activeProject.settings,
                            patch: {
                              behavior: { mode: e.target.value as 'auto' | 'manual' },
                            },
                          })
                        }
                      >
                        <option value="auto">{t('petSpace.behaviorAuto')}</option>
                        <option value="manual">{t('petSpace.behaviorManual')}</option>
                      </select>
                    </label>
                    <label className="text-xs space-y-1 block">
                      <span className="text-muted-foreground block mb-1">{t('petSpace.behaviorAutoReactivity')}</span>
                      <select
                        className="rounded-lg border border-border bg-background px-2 py-1.5 text-sm min-w-[140px]"
                        value={behaviorResolved.autoReactivity ?? 'normal'}
                        disabled={patchSettingsMut.isPending || behaviorResolved.mode !== 'auto'}
                        onChange={(e) =>
                          patchSettingsMut.mutate({
                            projectId: activeProject.id,
                            baseSettings: activeProject.settings,
                            patch: {
                              behavior: { autoReactivity: e.target.value as PetAutoReactivity },
                            },
                          })
                        }
                      >
                        <option value="subtle">{t('petSpace.autoReactivity.subtle')}</option>
                        <option value="normal">{t('petSpace.autoReactivity.normal')}</option>
                        <option value="expressive">{t('petSpace.autoReactivity.expressive')}</option>
                      </select>
                    </label>
                    <label className="text-xs space-y-1 block">
                      <span className="text-muted-foreground block mb-1">{t('petSpace.behaviorManualMode')}</span>
                      <select
                        className="rounded-lg border border-border bg-background px-2 py-1.5 text-sm min-w-[160px]"
                        value={behaviorResolved.manualMode}
                        disabled={patchSettingsMut.isPending || behaviorResolved.mode !== 'manual'}
                        onChange={(e) =>
                          patchSettingsMut.mutate({
                            projectId: activeProject.id,
                            baseSettings: activeProject.settings,
                            patch: {
                              behavior: { manualMode: e.target.value as PetManualMode },
                            },
                          })
                        }
                      >
                        {MANUAL_MODES.map((mode) => (
                          <option key={mode} value={mode}>
                            {t(`petSpace.manualMode.${mode}`)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="text-xs space-y-1 block">
                      <span className="text-muted-foreground block mb-1">{t('petSpace.behaviorIdleAnimation')}</span>
                      <select
                        className="rounded-lg border border-border bg-background px-2 py-1.5 text-sm min-w-[150px]"
                        value={behaviorResolved.idleAnimation ?? 'breath'}
                        disabled={patchSettingsMut.isPending}
                        onChange={(e) =>
                          patchSettingsMut.mutate({
                            projectId: activeProject.id,
                            baseSettings: activeProject.settings,
                            patch: {
                              behavior: { idleAnimation: e.target.value as PetIdleAnimation },
                            },
                          })
                        }
                      >
                        {IDLE_ANIMATIONS.map((anim) => (
                          <option key={anim} value={anim}>
                            {t(`petSpace.idleAnimation.${anim}`)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="text-xs space-y-1 block">
                      <span className="text-muted-foreground block mb-1">{t('petSpace.behaviorMotionStyle')}</span>
                      <select
                        className="rounded-lg border border-border bg-background px-2 py-1.5 text-sm min-w-[150px]"
                        value={behaviorResolved.motionStyle ?? 'gentle'}
                        disabled={patchSettingsMut.isPending}
                        onChange={(e) =>
                          patchSettingsMut.mutate({
                            projectId: activeProject.id,
                            baseSettings: activeProject.settings,
                            patch: {
                              behavior: { motionStyle: e.target.value as PetMotionStyle },
                            },
                          })
                        }
                      >
                        {MOTION_STYLES.map((style) => (
                          <option key={style} value={style}>
                            {t(`petSpace.motionStyle.${style}`)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="text-xs space-y-2 block min-w-[180px]">
                      <span className="text-muted-foreground block">
                        {t('petSpace.behaviorMotionSpeed')}: {(behaviorResolved.motionSpeed ?? 1).toFixed(1)}x
                      </span>
                      <input
                        type="range"
                        min={0.5}
                        max={2}
                        step={0.1}
                        value={behaviorResolved.motionSpeed ?? 1}
                        disabled={patchSettingsMut.isPending}
                        onChange={(e) =>
                          patchSettingsMut.mutate({
                            projectId: activeProject.id,
                            baseSettings: activeProject.settings,
                            patch: {
                              behavior: { motionSpeed: Number(e.target.value) },
                            },
                          })
                        }
                        className="w-full h-2 accent-primary-600"
                      />
                    </label>
                    <label className="flex items-center gap-2 text-xs cursor-pointer select-none pb-2">
                      <input
                        type="checkbox"
                        className="rounded border-border"
                        checked={simulateCustomizeStream}
                        onChange={(e) => setSimulateCustomizeStream(e.target.checked)}
                      />
                      {t('petSpace.behaviorSimulateStream')}
                    </label>
                  </div>
                </div>

                <SpriteSheetGifTool
                  projectId={activeProject.id}
                  files={listedFiles}
                  onDone={() => {
                    void qc.invalidateQueries({ queryKey: ['pet-space', 'files', activeProject.id] });
                    void qc.invalidateQueries({ queryKey: ['pet-space', 'projects'] });
                    invalidateDock();
                  }}
                />

                <div className="rounded-xl border border-border p-4 space-y-3">
                  <h3 className="text-sm font-semibold">{t('petSpace.builtinPresetsTitle')}</h3>
                  <p className="text-xs text-muted-foreground">{t('petSpace.builtinPresetsIntro')}</p>
                  <div className="flex flex-wrap gap-2 items-stretch">
                    {PET_BUILTIN_APPEARANCES.map((bid) => {
                      const selected =
                        isPetBuiltinAppearance(primaryParsed.appearance_builtin) &&
                        primaryParsed.appearance_builtin === bid;
                      return (
                        <button
                          key={bid}
                          type="button"
                          disabled={patchSettingsMut.isPending}
                          onClick={() =>
                            patchSettingsMut.mutate({
                              projectId: activeProject.id,
                              baseSettings: activeProject.settings,
                              patch: { appearance_builtin: bid },
                            })
                          }
                          className={cn(
                            'flex flex-col items-center gap-1.5 rounded-xl border px-3 py-2 min-w-[76px] transition-colors',
                            selected
                              ? 'border-primary-500 bg-primary-50 dark:bg-primary-950/40 ring-1 ring-primary-400/25'
                              : 'border-border-subtle bg-surface-sunken/40 hover:bg-surface-sunken',
                          )}
                        >
                          <img
                            src={builtinPetSvgUrl(bid)}
                            alt=""
                            className="h-12 w-12 rounded-lg object-cover border border-border-subtle bg-white/90 dark:bg-slate-900/80"
                          />
                          <span className="text-[11px] font-medium text-foreground">
                            {t(`petSpace.builtin.${bid}`)}
                          </span>
                        </button>
                      );
                    })}
                    <button
                      type="button"
                      disabled={patchSettingsMut.isPending || !heroBuiltin}
                      onClick={() =>
                        patchSettingsMut.mutate({
                          projectId: activeProject.id,
                          baseSettings: activeProject.settings,
                          patch: { appearance_builtin: null },
                        })
                      }
                      className="self-center rounded-lg border border-border-subtle bg-surface-sunken/50 px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-surface-sunken disabled:opacity-50 disabled:pointer-events-none"
                    >
                      {t('petSpace.builtinClear')}
                    </button>
                  </div>
                </div>

                <div>
                  <h3 className="text-sm font-semibold mb-2">{t('petSpace.pickAppearance')}</h3>
                  {deleteFileMut.isError && (
                    <p className="text-xs text-red-600 mb-2">
                      {String((deleteFileMut.error as Error)?.message)}
                    </p>
                  )}
                  <ul className="grid justify-items-center gap-2.5 [grid-template-columns:repeat(auto-fill,minmax(6.75rem,1fr))]">
                    {listedFiles.length === 0 && !filesQuery.isLoading && (
                      <li className="col-span-full text-sm text-muted-foreground">{t('petSpace.noFiles')}</li>
                    )}
                    {listedFiles.map((row) => {
                      const isAppearance = row.file_id === appearanceFileId;
                      const canPick = isPetRenderableImageRow(row);
                      return (
                        <PetLibraryFileCard
                          key={row.id}
                          mode="appearance"
                          compact
                          row={row}
                          canPickAppearance={canPick}
                          isCurrentAppearance={isAppearance}
                          setAppearanceDisabled={setAppearanceMut.isPending}
                          onSetAppearance={() =>
                            setAppearanceMut.mutate({
                              projectId: activeProject.id,
                              fileId: row.file_id,
                              baseSettings: activeProject.settings,
                            })
                          }
                          deleteDisabled={
                            deleteFileMut.isPending || setAppearanceMut.isPending || uploadMut.isPending
                          }
                          onDelete={() => {
                            if (
                              !window.confirm(t('petSpace.deleteFileConfirm', { name: row.original_name }))
                            )
                              return;
                            deleteFileMut.mutate({
                              projectId: activeProject.id,
                              fileId: row.file_id,
                              baseSettings: activeProject.settings,
                            });
                          }}
                        />
                      );
                    })}
                  </ul>
                  {!heroBuiltin && heroMime?.includes('gif') ? (
                    <div className="mt-3 rounded-lg border border-border-subtle bg-surface-sunken/20 px-3 py-2 space-y-1.5">
                      <label className="flex items-center gap-2 text-xs cursor-pointer select-none">
                        <input
                          type="checkbox"
                          className="rounded border-border"
                          checked={primaryParsed.appearance_gif_bind_motion !== false}
                          disabled={patchSettingsMut.isPending}
                          onChange={(e) =>
                            patchSettingsMut.mutate({
                              projectId: activeProject.id,
                              baseSettings: activeProject.settings,
                              patch: { appearance_gif_bind_motion: e.target.checked },
                            })
                          }
                        />
                        <span>{t('petSpace.gifBindMotion')}</span>
                      </label>
                      <p className="text-[11px] text-muted-foreground leading-snug pl-5">
                        {t('petSpace.gifBindMotionIntro')}
                      </p>
                    </div>
                  ) : null}
                </div>
              </>
            )}
          </div>
        )}

        {tab === 'studio' && (
          <div className="max-w-6xl">
            {!activeProject ? (
              <div className="rounded-xl border border-dashed border-border p-6 text-center">
                <p className="text-sm text-muted-foreground">{t('petSpace.customizeNoProject')}</p>
              </div>
            ) : (
              <ActionStudioPanel
                project={activeProject}
                primaryParsed={primaryParsed}
                listedFiles={listedFiles}
                patchSettingsMut={patchSettingsMut}
                onFilesChanged={() => {
                  void qc.invalidateQueries({ queryKey: ['pet-space', 'files', activeProject.id] });
                }}
              />
            )}
          </div>
        )}

        {tab === 'showroom' && (
          <div className="space-y-6 max-w-5xl">
            {!activeProject ? (
              <div className="rounded-xl border border-dashed border-border p-6 text-center">
                <p className="text-sm text-muted-foreground">{t('petSpace.customizeNoProject')}</p>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                  <p className="text-sm text-muted-foreground max-w-2xl">{t('petSpace.showroomLead')}</p>
                  <Button type="button" variant="outline" size="sm" onClick={() => setTab('customize')}>
                    {t('petSpace.showroomGoCustomize')}
                  </Button>
                </div>
                <PetShowcaseSection
                  primaryProject={activeProject}
                  listedFiles={listedFiles}
                  primaryParsed={primaryParsed}
                  patchSettingsMut={patchSettingsMut}
                  presetLayout="grid"
                />
              </div>
            )}
          </div>
        )}

        {tab === 'personality' && (
          <div className="max-w-3xl">
            {!activeProject ? (
              <div className="rounded-xl border border-dashed border-border p-6 text-center">
                <p className="text-sm text-muted-foreground">{t('petSpace.personalityNoProject')}</p>
              </div>
            ) : (
              <PersonalityEditor
                project={activeProject}
                primaryParsed={primaryParsed}
                patchSettingsMut={patchSettingsMut}
              />
            )}
          </div>
        )}

        {tab === 'library' && (
          <div className="grid min-h-[320px] grid-cols-1 gap-6 lg:grid-cols-[280px_1fr]">
            <div className="min-w-0 space-y-3">
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-sm font-semibold text-foreground">{t('petSpace.navLibrary')}</h2>
                <Button size="sm" leftIcon={<Plus className="w-4 h-4" />} onClick={() => setCreateOpen(true)}>
                  {t('petSpace.newProject')}
                </Button>
              </div>
              {createOpen && (
                <div className="rounded-xl border border-border p-3 space-y-2 bg-surface-sunken/40">
                  <Input
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder={t('petSpace.projectName')}
                  />
                  <div className="flex gap-2 justify-end">
                    <Button variant="outline" size="sm" onClick={() => setCreateOpen(false)}>
                      {t('petSpace.cancel')}
                    </Button>
                    <Button
                      size="sm"
                      disabled={!newName.trim() || createMut.isPending}
                      onClick={() => createMut.mutate(newName.trim())}
                    >
                      {t('petSpace.create')}
                    </Button>
                  </div>
                </div>
              )}
              <ul className="space-y-1">
                {projects.length === 0 && !projectsQuery.isLoading && (
                  <li className="text-sm text-muted-foreground py-6 text-center border border-dashed border-border rounded-xl">
                    {t('petSpace.noProjects')}
                    <p className="text-xs mt-2 text-muted-foreground-tertiary">{t('petSpace.noProjectsHint')}</p>
                  </li>
                )}
                {projects.map((p: PetProject) => (
                  <li key={p.id}>
                    <div
                      role="presentation"
                      className={cn(
                        'w-full text-left px-3 py-2 rounded-lg text-sm transition-colors flex items-center justify-between gap-2',
                        selectedId === p.id
                          ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-800 dark:text-primary-200'
                          : 'hover:bg-surface-sunken text-foreground',
                      )}
                    >
                      <button
                        type="button"
                        className="truncate font-medium text-left flex-1 min-w-0"
                        onClick={() => setSelectedId(p.id)}
                      >
                        {p.name}
                      </button>
                      <button
                        type="button"
                        className="p-1 rounded hover:bg-red-100 dark:hover:bg-red-900/30 text-muted-foreground hover:text-red-600 shrink-0"
                        title={t('petSpace.deleteProject')}
                        onClick={() => {
                          if (window.confirm(t('petSpace.deleteProject'))) deleteMut.mutate(p.id);
                        }}
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            </div>

            <div className="min-w-0 space-y-6 rounded-xl border border-border p-4 min-h-[280px]">
              {!activeProjectId ? (
                <p className="text-sm text-muted-foreground">{t('petSpace.files')}</p>
              ) : (
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="text-sm font-semibold">{t('petSpace.files')}</h3>
                    <label
                      className={cn(
                        'inline-flex cursor-pointer items-center justify-center gap-2 rounded-lg font-medium transition-colors',
                        'px-3 py-1.5 text-xs',
                        'bg-surface-sunken text-foreground hover:bg-border-subtle dark:bg-surface-elevated dark:hover:bg-surface-sunken',
                      )}
                    >
                      <input
                        type="file"
                        className="sr-only"
                        accept="image/png,image/jpeg,image/jpg,image/webp,image/gif,image/svg+xml,.png,.jpg,.jpeg,.webp,.gif,.svg"
                        onChange={(e) => onPickFile(e, activeProjectId)}
                      />
                      {t('petSpace.upload')}
                    </label>
                  </div>
                  {uploadMut.isError && (
                    <p className="text-xs text-red-600">{String((uploadMut.error as Error)?.message)}</p>
                  )}
                  {deleteFileMut.isError && (
                    <p className="text-xs text-red-600">{String((deleteFileMut.error as Error)?.message)}</p>
                  )}
                  <ul className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(10.5rem,1fr))]">
                    {(filesQuery.data ?? []).length === 0 && !filesQuery.isLoading && (
                      <li className="col-span-full text-sm text-muted-foreground">{t('petSpace.noFiles')}</li>
                    )}
                    {(filesQuery.data ?? []).map((row) => (
                      <PetLibraryFileCard
                        key={row.id}
                        row={row}
                        downloadHref={`${import.meta.env.VITE_API_BASE_URL || '/api/v1'}/files/${row.file_id}/download`}
                        deleteDisabled={deleteFileMut.isPending || uploadMut.isPending}
                        onDelete={() => {
                          if (!window.confirm(t('petSpace.deleteFileConfirm', { name: row.original_name }))) return;
                          deleteFileMut.mutate({
                            projectId: activeProjectId!,
                            fileId: row.file_id,
                            baseSettings: activeProject?.settings ?? null,
                          });
                        }}
                      />
                    ))}
                  </ul>
                </div>
              )}

              <div className="rounded-xl border border-dashed border-border-subtle bg-surface-sunken/20 p-4 space-y-3">
                <h3 className="text-sm font-semibold text-foreground">{t('petSpace.libraryBuiltInSamplesTitle')}</h3>
                <p className="text-xs text-muted-foreground leading-relaxed">{t('petSpace.libraryBuiltInSamplesIntro')}</p>
                <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {PET_PRESET_SAMPLE_FILES.map((rel) => {
                    const href = petPresetPublicUrl(rel);
                    const label = rel.replace(/^pet-presets\//, '');
                    return (
                      <li key={rel}>
                        <a
                          href={href}
                          target="_blank"
                          rel="noreferrer"
                          className="flex items-center gap-2 text-xs text-primary-600 dark:text-primary-400 hover:underline min-w-0"
                        >
                          <ExternalLink className="w-3.5 h-3.5 shrink-0" />
                          <span className="truncate font-mono">{label}</span>
                        </a>
                      </li>
                    );
                  })}
                </ul>
              </div>
            </div>
          </div>
        )}

        {tab === 'about' && (
          <div className="max-w-2xl space-y-8 text-sm text-muted-foreground">
            <section className="space-y-2">
              <h2 className="text-base font-semibold text-foreground">{t('petSpace.aboutSectionOverview')}</h2>
              <p>{t('petSpace.aboutBody')}</p>
            </section>
            <section className="space-y-2">
              <h2 className="text-base font-semibold text-foreground">{t('petSpace.aboutSectionCustomizeTitle')}</h2>
              <p className="whitespace-pre-line leading-relaxed">{t('petSpace.aboutCustomizeSteps')}</p>
            </section>
            <section className="space-y-2">
              <h2 className="text-base font-semibold text-foreground">{t('petSpace.aboutSectionFormatsTitle')}</h2>
              <p className="whitespace-pre-line leading-relaxed">{t('petSpace.aboutFormatsBody')}</p>
            </section>
            <section className="space-y-2">
              <h2 className="text-base font-semibold text-foreground">{t('petSpace.aboutSectionAiTitle')}</h2>
              <p className="whitespace-pre-line leading-relaxed">{t('petSpace.aboutAiBody')}</p>
            </section>
            <section className="space-y-2">
              <h2 className="text-base font-semibold text-foreground">{t('petSpace.aboutSectionSpriteTitle')}</h2>
              <p className="whitespace-pre-line leading-relaxed">{t('petSpace.aboutSpriteBody')}</p>
            </section>
            <section className="space-y-2">
              <h2 className="text-base font-semibold text-foreground">{t('petSpace.aboutSectionStudioTitle')}</h2>
              <p className="whitespace-pre-line leading-relaxed">{t('petSpace.aboutStudioBody')}</p>
            </section>
            <section className="space-y-2">
              <h2 className="text-base font-semibold text-foreground">{t('petSpace.aboutSectionSceneTitle')}</h2>
              <p className="whitespace-pre-line leading-relaxed">{t('petSpace.aboutSceneBody')}</p>
            </section>
          </div>
        )}
      </div>
    </PageShell>
  );
}
