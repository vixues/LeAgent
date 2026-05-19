import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui';
import { PRIMARY_SOFT_CTA_CLASSNAME } from '@/components/ui/Button';
import { cn } from '@/lib/utils';
import {
  PET_SCENE_ACTION_KEYS,
  type PetSettingsClipPatch,
  resolveActionWeights,
  resolvedBehavior,
  type PetRoamRange,
  type PetSceneActionKey,
  type PetSettings,
} from '@/lib/petSettings';

type PatchMut = {
  isPending: boolean;
  mutate: (vars: {
    projectId: string;
    baseSettings: string | null | undefined;
    patch: Partial<Omit<PetSettings, 'clips'>> & { clips?: PetSettingsClipPatch };
  }) => void;
};

const ROAMS: { id: PetRoamRange; labelKey: string }[] = [
  { id: 'tight', labelKey: 'petSpace.studio.roamTight' },
  { id: 'normal', labelKey: 'petSpace.studio.roamNormal' },
  { id: 'wide', labelKey: 'petSpace.studio.roamWide' },
];

const ACTION_LABEL: Record<PetSceneActionKey, string> = {
  idle: 'petSpace.studio.wIdle',
  walk: 'petSpace.studio.wWalk',
  lookAround: 'petSpace.studio.wLookAround',
  jump: 'petSpace.studio.wJump',
  wave: 'petSpace.studio.wWave',
  dance: 'petSpace.studio.wDance',
  shake: 'petSpace.studio.wShake',
};

function WeightChips({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  return (
    <div className="flex flex-wrap gap-0.5">
      {[0, 1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          onClick={() => onChange(n)}
          className={cn(
            'h-6 min-w-6 rounded px-1.5 text-[10px] font-medium tabular-nums transition-colors',
            n === value
              ? PRIMARY_SOFT_CTA_CLASSNAME
              : 'bg-surface-sunken text-muted-foreground hover:bg-border/80',
          )}
        >
          {n}
        </button>
      ))}
    </div>
  );
}

export function AutopilotPanel({
  projectId,
  baseSettings,
  primaryParsed,
  patchSettingsMut,
}: {
  projectId: string;
  baseSettings: string | null | undefined;
  primaryParsed: PetSettings;
  patchSettingsMut: PatchMut;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const b = useMemo(() => resolvedBehavior(primaryParsed), [primaryParsed]);
  const [autopilot, setAutopilot] = useState(b.autopilot !== false);
  const [roamRange, setRoamRange] = useState<PetRoamRange>(b.roamRange ?? 'normal');
  const [weights, setWeights] = useState<Record<PetSceneActionKey, number>>(() =>
    resolveActionWeights(b.actionWeights),
  );

  useEffect(() => {
    const b2 = resolvedBehavior(primaryParsed);
    setAutopilot(b2.autopilot !== false);
    setRoamRange(b2.roamRange ?? 'normal');
    setWeights(resolveActionWeights(b2.actionWeights));
  }, [primaryParsed]);

  const setWeight = (key: PetSceneActionKey, n: number) => {
    setWeights((w) => ({ ...w, [key]: n }));
  };

  const apply = useCallback(
    (patch: { autopilot: boolean; roam: PetRoamRange; w: typeof weights }) => {
      patchSettingsMut.mutate({
        projectId,
        baseSettings,
        patch: {
          behavior: {
            autopilot: patch.autopilot,
            roamRange: patch.roam,
            actionWeights: { ...patch.w },
          },
        },
      });
      void qc.invalidateQueries({ queryKey: ['pet-space', 'dock'] });
    },
    [baseSettings, patchSettingsMut, projectId, qc],
  );

  const onSave = () => {
    apply({ autopilot, roam: roamRange, w: weights });
  };

  const onReset = () => {
    const w = resolveActionWeights({});
    setAutopilot(true);
    setRoamRange('normal');
    setWeights(w);
    apply({ autopilot: true, roam: 'normal', w });
  };

  return (
    <div className="rounded-xl border border-border bg-background/60 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-medium">{t('petSpace.studio.autopilotTitle')}</h3>
          <p className="text-xs text-muted-foreground max-w-2xl mt-1">{t('petSpace.studio.autopilotDesc')}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button type="button" size="sm" variant="outline" onClick={onReset} disabled={patchSettingsMut.isPending}>
            {t('petSpace.studio.resetDefaults')}
          </Button>
          <Button type="button" size="sm" onClick={onSave} disabled={patchSettingsMut.isPending}>
            {t('common.save')}
          </Button>
        </div>
      </div>
      <div className="mt-4 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            className="rounded border-border"
            checked={autopilot}
            onChange={(e) => setAutopilot(e.target.checked)}
          />
          {t('petSpace.studio.autopilotLabel')}
        </label>
        <div className="space-y-1">
          <p className="text-xs text-muted-foreground">{t('petSpace.studio.roamRange')}</p>
          <div className="inline-flex rounded-lg border border-border p-0.5">
            {ROAMS.map((r) => (
              <button
                key={r.id}
                type="button"
                onClick={() => setRoamRange(r.id)}
                className={cn(
                  'px-2 py-1 text-xs rounded-md',
                  roamRange === r.id ? 'bg-primary-100 dark:bg-primary-900/30 text-foreground' : 'text-muted-foreground',
                )}
              >
                {t(r.labelKey)}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="mt-4">
        <p className="text-xs font-medium text-muted-foreground mb-2">{t('petSpace.studio.actionWeightsTitle')}</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {PET_SCENE_ACTION_KEYS.map((key) => (
            <div key={key} className="flex items-center justify-between gap-2 rounded-lg border border-border/60 p-2">
              <span className="text-xs text-foreground min-w-0 flex-1">{t(ACTION_LABEL[key])}</span>
              <WeightChips value={weights[key] ?? 0} onChange={(n) => setWeight(key, n)} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
