import { useTranslation } from 'react-i18next';
import { isPetBuiltinAppearance, PET_BUILTIN_APPEARANCES, type PetBuiltinAppearance } from '@/lib/builtinPets';
import { isPetRenderableImageRow } from '@/lib/petAppearanceMime';
import type { PetProjectFileRow } from '@/api/petSpace';
import { Button } from '@/components/ui';
import type { PetClipBinding, PetClipState, PetSettings } from '@/lib/petSettings';
import { normalizeClipBinding, type PetSettingsClipPatch } from '@/lib/petSettings';

type PatchMut = {
  isPending: boolean;
  mutate: (vars: {
    projectId: string;
    baseSettings: string | null | undefined;
    patch: Partial<Omit<PetSettings, 'clips'>> & { clips?: import('@/lib/petSettings').PetSettingsClipPatch };
  }) => void;
};

function labelKeyForState(s: PetClipState): string {
  if (s === 'lookAround') return 'petSpace.manualMode.lookAround';
  if (s === 'idle') return 'petSpace.actionState.idle.name';
  if (['none', 'breath', 'blink', 'float', 'tailWag', 'hop'].includes(s)) {
    return `petSpace.idleAnimation.${s}`;
  }
  return `petSpace.actionState.${s}.name`;
}

export function ClipInspector({
  state,
  listedFiles,
  projectId,
  projectSettings,
  primaryParsed,
  patchSettingsMut,
  onCleared,
}: {
  state: PetClipState | null;
  listedFiles: PetProjectFileRow[];
  projectId: string;
  projectSettings: string | null | undefined;
  primaryParsed: PetSettings;
  patchSettingsMut: PatchMut;
  onCleared: () => void;
}) {
  const { t } = useTranslation();
  const cur = state ? primaryParsed.clips?.[state] : undefined;
  const b = state && cur ? normalizeClipBinding(cur) : null;
  const displayFileId = b?.fileId ?? null;
  const displayBuiltin = b?.builtin ?? null;

  const setClip = (next: PetClipBinding | null) => {
    if (!state) return;
    if (!next || !normalizeClipBinding(next)) {
      patchSettingsMut.mutate({
        projectId,
        baseSettings: projectSettings,
        patch: { clips: { [state]: { fileId: null, builtin: null } } },
      });
      onCleared();
      return;
    }
    const patch: PetSettingsClipPatch = { [state]: { ...next, fileId: next.fileId, builtin: next.builtin ?? null } };
    patchSettingsMut.mutate({ projectId, baseSettings: projectSettings, patch: { clips: patch } });
  };

  if (!state) {
    return (
      <div className="rounded-xl border border-dashed border-border p-4 text-sm text-muted-foreground">
        {t('petSpace.studio.selectAction')}
      </div>
    );
  }

  const images = listedFiles.filter((f) => isPetRenderableImageRow(f));
  return (
    <div className="space-y-4">
      <div>
        <h4 className="text-sm font-semibold text-foreground mb-1">{t(labelKeyForState(state), { defaultValue: state })}</h4>
        <p className="text-xs text-muted-foreground mb-3">{t('petSpace.studio.inspectorHelp')}</p>
      </div>
      <label className="text-xs space-y-1 block w-full">
        <span className="text-muted-foreground">{t('petSpace.studio.file')}</span>
        <select
          className="w-full rounded-lg border border-border bg-background px-2 py-2 text-sm"
          value={displayFileId ?? ''}
          disabled={patchSettingsMut.isPending}
          onChange={(e) => {
            const v = e.target.value;
            if (!v) {
              if (displayBuiltin) {
                setClip(
                  b
                    ? { ...b, fileId: null, builtin: displayBuiltin }
                    : { fileId: null, builtin: null },
                );
                return;
              }
              setClip(null);
              return;
            }
            setClip(
              b
                ? { ...b, fileId: v, builtin: null, overrideCssMotion: b.overrideCssMotion ?? true }
                : { fileId: v, builtin: null, overrideCssMotion: true },
            );
          }}
        >
          <option value="">{t('petSpace.studio.noFile')}</option>
          {images.map((row) => (
            <option key={row.id} value={row.file_id}>
              {row.original_name}
            </option>
          ))}
        </select>
      </label>
      <label className="text-xs space-y-1 block w-full">
        <span className="text-muted-foreground">{t('petSpace.studio.builtin')}</span>
        <select
          className="w-full rounded-lg border border-border bg-background px-2 py-2 text-sm"
          value={displayBuiltin ?? ''}
          disabled={patchSettingsMut.isPending}
          onChange={(e) => {
            const v = e.target.value;
            if (!v) {
              if (displayFileId) {
                setClip(
                  b ? { ...b, builtin: null, fileId: displayFileId } : { fileId: displayFileId, builtin: null, overrideCssMotion: true },
                );
                return;
              }
              setClip(null);
              return;
            }
            const bid = v as PetBuiltinAppearance;
            if (!isPetBuiltinAppearance(bid)) return;
            setClip(
              b
                ? { ...b, builtin: bid, fileId: null, overrideCssMotion: b.overrideCssMotion ?? true }
                : { fileId: null, builtin: bid, overrideCssMotion: true },
            );
          }}
        >
          <option value="">{t('petSpace.studio.noBuiltin')}</option>
          {PET_BUILTIN_APPEARANCES.map((bid) => (
            <option key={bid} value={bid}>
              {t(`petSpace.builtin.${bid}`)}
            </option>
          ))}
        </select>
      </label>
      {b && (b.fileId || b.builtin) ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="text-xs space-y-1 block">
            <span className="text-muted-foreground">{t('petSpace.studio.loop')}</span>
            <select
              className="w-full rounded-lg border border-border bg-background px-2 py-1.5 text-sm"
              value={b.loop ?? 'loop'}
              disabled={patchSettingsMut.isPending}
              onChange={(e) => setClip({ ...b, loop: e.target.value as 'loop' | 'once' })}
            >
              <option value="loop">{t('petSpace.studio.loopOn')}</option>
              <option value="once">{t('petSpace.studio.loopOnce')}</option>
            </select>
          </label>
          <label className="text-xs space-y-1 block">
            <span className="text-muted-foreground">
              {t('petSpace.studio.speed')}: {Number(b.speed ?? 1).toFixed(2)}x
            </span>
            <input
              type="range"
              min={0.25}
              max={4}
              step={0.05}
              className="w-full h-2 accent-primary-600"
              value={b.speed ?? 1}
              disabled={patchSettingsMut.isPending}
              onChange={(e) => setClip({ ...b, speed: Number(e.target.value) })}
            />
          </label>
          <label className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={Boolean(b.mirror)}
              onChange={(e) => setClip({ ...b, mirror: e.target.checked })}
            />
            {t('petSpace.studio.mirror')}
          </label>
          <label className="text-xs space-y-1 block">
            <span className="text-muted-foreground">{t('petSpace.studio.fit')}</span>
            <select
              className="w-full rounded-lg border border-border bg-background px-2 py-1.5 text-sm"
              value={b.fit ?? 'contain'}
              disabled={patchSettingsMut.isPending}
              onChange={(e) => setClip({ ...b, fit: e.target.value as 'cover' | 'contain' })}
            >
              <option value="contain">{t('petSpace.studio.fitContain')}</option>
              <option value="cover">{t('petSpace.studio.fitCover')}</option>
            </select>
          </label>
          <label className="flex items-center gap-2 text-xs sm:col-span-2">
            <input
              type="checkbox"
              checked={b.overrideCssMotion !== false}
              onChange={(e) => setClip({ ...b, overrideCssMotion: e.target.checked })}
            />
            {t('petSpace.studio.overrideCss')}
          </label>
        </div>
      ) : null}
      {b && (b.fileId || b.builtin) ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={patchSettingsMut.isPending}
          onClick={() => {
            if (!state) return;
            patchSettingsMut.mutate({
              projectId,
              baseSettings: projectSettings,
              patch: { clips: { [state]: { fileId: null, builtin: null } } },
            });
            onCleared();
          }}
        >
          {t('petSpace.studio.clearBinding')}
        </Button>
      ) : null}
    </div>
  );
}
