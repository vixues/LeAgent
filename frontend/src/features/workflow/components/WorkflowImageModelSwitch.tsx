import { useTranslation } from 'react-i18next';
import { ImageIcon } from 'lucide-react';

import { useToast } from '@/components/ui/Toaster';
import {
  useImageGenPresets,
  useImageGenDefault,
  useSetDefaultPreset,
} from '@/hooks/useImageGen';

/**
 * Compact quick-switch for the workflow-level active image model. Bound to the
 * image-gen *default preset*, which every art node left on ``auto`` adopts at
 * run time — so a single change re-targets the whole graph without editing
 * each node.
 */
export function WorkflowImageModelSwitch() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const { data: presets } = useImageGenPresets();
  const { data: def } = useImageGenDefault();
  const setDefault = useSetDefaultPreset();

  if (!presets || presets.length === 0) return null;

  const onChange = async (id: string) => {
    try {
      await setDefault.mutateAsync(id);
      toast({ variant: 'success', title: t('workflow.imageGen.switched') });
    } catch (e) {
      toast({
        variant: 'error',
        title: t('workflow.imageGen.switchError'),
        description: e instanceof Error ? e.message : String(e),
      });
    }
  };

  return (
    <label
      className="flex items-center gap-1.5 rounded border border-border bg-surface px-2 py-1 text-xs text-muted-foreground"
      title={t('workflow.imageGen.switchHelp')}
    >
      <ImageIcon className="h-3.5 w-3.5" />
      <span className="hidden sm:inline">{t('workflow.imageGen.activeModel')}</span>
      <select
        className="nodrag max-w-[180px] bg-transparent text-foreground focus:outline-none"
        value={def?.preset_id ?? ''}
        disabled={setDefault.isPending}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">{t('workflow.imageGen.presetNone')}</option>
        {presets.map((p) => (
          <option key={p.id} value={p.id}>
            {p.label}
          </option>
        ))}
      </select>
    </label>
  );
}
