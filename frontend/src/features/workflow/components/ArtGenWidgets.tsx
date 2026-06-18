import { useTranslation } from 'react-i18next';

import { useImageGenModels, useImageGenPresets } from '@/hooks/useImageGen';

const FIELD =
  'nodrag w-full rounded border border-border bg-background px-1.5 py-0.5 text-xs text-foreground disabled:opacity-50';

/** Art image nodes that expose configurable provider/model/preset inputs. */
export const ART_IMAGE_NODE_TYPES = new Set(['Art.ImageGen', 'Art.Upscale']);

/**
 * Provider-dependent model dropdown for art image nodes. When the provider is a
 * concrete backend, the model list is fetched from
 * ``/models/image-gen/models?backend=``; on ``auto`` it falls back to a plain
 * text field (the model is provider-resolved at run time).
 */
export function ArtModelSelect({
  provider,
  value,
  onChange,
  disabled,
}: {
  provider: string | undefined;
  value: unknown;
  onChange: (v: unknown) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const backend = provider && provider !== 'auto' ? provider : undefined;
  const { data: models } = useImageGenModels(backend);
  const current = typeof value === 'string' ? value : '';

  if (!backend) {
    return (
      <input
        className={FIELD}
        value={current}
        disabled={disabled}
        placeholder={t('workflow.imageGen.modelAutoPlaceholder')}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }

  const options = models ?? [];
  const hasCurrent = current && options.includes(current);
  return (
    <select
      className={FIELD}
      value={current}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">{t('workflow.imageGen.modelDefault')}</option>
      {options.map((m) => (
        <option key={m} value={m}>
          {m}
        </option>
      ))}
      {current && !hasCurrent ? <option value={current}>{current}</option> : null}
    </select>
  );
}

/** Preset picker for art image nodes (one-click backend+model+params bundle). */
export function ArtPresetSelect({
  value,
  onChange,
  disabled,
}: {
  value: unknown;
  onChange: (v: unknown) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  const { data: presets } = useImageGenPresets();
  const current = typeof value === 'string' ? value : '';

  return (
    <select
      className={FIELD}
      value={current}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">{t('workflow.imageGen.presetNone')}</option>
      {(presets ?? []).map((p) => (
        <option key={p.id} value={p.id}>
          {p.label}
        </option>
      ))}
    </select>
  );
}
