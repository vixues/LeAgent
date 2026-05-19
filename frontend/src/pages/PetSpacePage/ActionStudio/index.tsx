import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { PetProject, PetProjectFileRow } from '@/api/petSpace';
import type { PetSettings } from '@/lib/petSettings';
import type { PetClipState } from '@/lib/petSettings';
import { useQueryClient } from '@tanstack/react-query';
import { cn } from '@/lib/utils';
import { ACTION_STUDIO_MAIN_COLUMN_HEIGHT_CLASS } from './actionStudioConstants';
import { ActionGroups } from './ActionGroups';
import { ClipInspector } from './ClipInspector';
import { LivePreview } from './LivePreview';
import { SpriteSheetBatchBinder } from './SpriteSheetBatchBinder';
import { AutopilotPanel } from './AutopilotPanel';

type PatchMut = {
  isPending: boolean;
  mutate: (vars: {
    projectId: string;
    baseSettings: string | null | undefined;
    patch: Partial<Omit<PetSettings, 'clips'>> & { clips?: import('@/lib/petSettings').PetSettingsClipPatch };
  }) => void;
};

export function ActionStudioPanel({
  project,
  primaryParsed,
  listedFiles,
  patchSettingsMut,
  onFilesChanged,
}: {
  project: PetProject;
  primaryParsed: PetSettings;
  listedFiles: PetProjectFileRow[];
  patchSettingsMut: PatchMut;
  onFilesChanged: () => void;
}) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [selected, setSelected] = useState<PetClipState | null>('working');

  return (
    <div className="space-y-6 max-w-6xl">
      <p className="text-sm text-muted-foreground max-w-2xl">{t('petSpace.studio.lead')}</p>
      <AutopilotPanel
        projectId={project.id}
        baseSettings={project.settings}
        primaryParsed={primaryParsed}
        patchSettingsMut={patchSettingsMut}
      />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="lg:col-span-4">
          <ActionGroups selected={selected} onSelect={setSelected} t={t} />
        </div>
        <div className="lg:col-span-4 order-first lg:order-none">
          <div
            className={cn(
              ACTION_STUDIO_MAIN_COLUMN_HEIGHT_CLASS,
              'flex shrink-0 flex-col rounded-xl border border-border bg-background/60 p-4',
            )}
          >
            <p className="mb-3 shrink-0 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {t('petSpace.studio.livePreview')}
            </p>
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
              <LivePreview primaryParsed={primaryParsed} listedFiles={listedFiles} selectedState={selected} />
            </div>
          </div>
        </div>
        <div className="lg:col-span-4 space-y-3">
          <div className="rounded-xl border border-border bg-background/60 p-4 min-h-[12rem]">
            <ClipInspector
              state={selected}
              listedFiles={listedFiles}
              projectId={project.id}
              projectSettings={project.settings}
              primaryParsed={primaryParsed}
              patchSettingsMut={patchSettingsMut}
              onCleared={() => void qc.invalidateQueries({ queryKey: ['pet-space', 'dock'] })}
            />
          </div>
        </div>
      </div>
      <SpriteSheetBatchBinder
        projectId={project.id}
        baseSettings={project.settings}
        files={listedFiles}
        defaultTarget={selected ?? 'working'}
        onDone={() => {
          onFilesChanged();
          void qc.invalidateQueries({ queryKey: ['pet-space', 'projects'] });
        }}
      />
    </div>
  );
}
