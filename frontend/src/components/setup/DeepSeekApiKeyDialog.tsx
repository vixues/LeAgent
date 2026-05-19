import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { ExternalLink, Settings } from 'lucide-react';

import { adminApi } from '@/api/admin';
import {
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Button,
  Input,
  Select,
  Switch,
  Textarea,
} from '@/components/ui';
import { useToast } from '@/components/ui/Toaster';
import { cn } from '@/lib/utils';
import { shouldShowProviderNudge } from '@/lib/deepseekSetupNudge';
import type { PresetInfo, ProviderModelInfo, ProviderType, ModelProviderFormData } from '@/types/admin';

type NudgePhase = 'loading' | 'show' | 'hide';

const EMPTY_FORM: ModelProviderFormData = {
  name: '',
  type: 'deepseek',
  base_url: '',
  api_key: '',
  models: [],
  enabled: true,
};

function presetRowToFormModel(m: ProviderModelInfo): ProviderModelInfo {
  return {
    name: m.name,
    tier: m.tier ?? '',
    context_window: m.context_window ?? 0,
    enabled: m.enabled !== false,
    description: m.description,
    price_input_per_1m: m.price_input_per_1m,
    price_output_per_1m: m.price_output_per_1m,
    supports_tools: m.supports_tools,
    supports_vision: m.supports_vision,
  };
}

function parseFreeformModelIds(input: string): string[] {
  return input
    .split(/\r?\n|,/g)
    .map((s) => s.trim())
    .filter(Boolean);
}

export function DeepSeekApiKeyDialog() {
  const { t } = useTranslation();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [phase, setPhase] = useState<NudgePhase>('loading');
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const [presets, setPresets] = useState<PresetInfo[]>([]);
  const [formData, setFormData] = useState<ModelProviderFormData>({ ...EMPTY_FORM });
  const [modelsInput, setModelsInput] = useState('');
  const [formError, setFormError] = useState('');

  const presetCatalog = useMemo(() => {
    const p = presets.find((x) => x.type === formData.type);
    return p?.models?.length ? p.models : [];
  }, [presets, formData.type]);

  const usePresetModelMultiselect = presetCatalog.length > 0;

  const currentPreset = presets.find((p) => p.type === formData.type);
  const requiresApiKey = currentPreset?.requires_api_key ?? !['ollama'].includes(formData.type);
  const showBaseUrl = ['ollama', 'custom', 'azure', 'deepseek', 'openai'].includes(formData.type);
  const showAdvancedProviderFields = formData.type !== 'deepseek';

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [providers, presetsData] = await Promise.all([
          adminApi.providers.list(),
          adminApi.presets.list(),
        ]);
        if (cancelled) return;

        setPresets(presetsData);

        if (shouldShowProviderNudge(providers)) {
          const dsPreset = presetsData.find((p) => p.type === 'deepseek');
          if (dsPreset) {
            setFormData({
              ...EMPTY_FORM,
              base_url: dsPreset.default_base_url,
              models: dsPreset.models.map((m) => presetRowToFormModel(m)),
            });
            setModelsInput(dsPreset.models.map((m) => m.name).join('\n'));
          }
          setPhase('show');
          setOpen(true);
        } else {
          setPhase('hide');
        }
      } catch {
        if (!cancelled) setPhase('hide');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const applyPreset = useCallback(
    (preset: PresetInfo) => {
      setFormData({
        ...EMPTY_FORM,
        type: preset.type as ProviderType,
        base_url: preset.default_base_url,
        models: preset.models.map((m) => presetRowToFormModel(m)),
      });
      setModelsInput(preset.models.map((m) => m.name).join('\n'));
      setFormError('');
    },
    [],
  );

  const handleClose = useCallback(() => {
    setOpen(false);
    setPhase('hide');
  }, []);

  const togglePresetCatalogModel = useCallback((catalogRow: ProviderModelInfo) => {
    setFormError('');
    const name = catalogRow.name;
    setFormData((prev) => {
      const has = (prev.models ?? []).some((m) => m.name === name);
      if (has) {
        return { ...prev, models: (prev.models ?? []).filter((m) => m.name !== name) };
      }
      return { ...prev, models: [...(prev.models ?? []), presetRowToFormModel(catalogRow)] };
    });
  }, []);

  const handleSubmit = useCallback(async () => {
    setFormError('');

    if (!formData.name.trim()) {
      setFormError(t('deepseekSetup.providerNameRequired'));
      return;
    }

    let models: ProviderModelInfo[];

    if (presetCatalog.length > 0) {
      const selected = formData.models ?? [];
      if (selected.length === 0) {
        setFormError(t('admin.provider.atLeastOneModel'));
        return;
      }
      const seen = new Set<string>();
      models = [];
      for (const m of selected) {
        if (seen.has(m.name)) continue;
        seen.add(m.name);
        models.push({
          name: m.name,
          tier: m.tier ?? '',
          context_window: m.context_window ?? 0,
          enabled: m.enabled,
          description: m.description,
          price_input_per_1m: m.price_input_per_1m,
          price_output_per_1m: m.price_output_per_1m,
          supports_tools: m.supports_tools,
          supports_vision: m.supports_vision,
        });
      }
    } else {
      const ids = parseFreeformModelIds(modelsInput);
      if (ids.length === 0) {
        setFormError(t('admin.provider.atLeastOneModel'));
        return;
      }
      const seen = new Set<string>();
      models = [];
      for (const name of ids) {
        if (seen.has(name)) {
          setFormError(t('admin.provider.duplicateModelName', { name }));
          return;
        }
        seen.add(name);
        const existing = formData.models?.find((m) => m.name === name);
        models.push(
          existing
            ? {
                name: existing.name,
                tier: existing.tier ?? '',
                context_window: existing.context_window ?? 0,
                enabled: existing.enabled,
                description: existing.description,
                price_input_per_1m: existing.price_input_per_1m,
                price_output_per_1m: existing.price_output_per_1m,
                supports_tools: existing.supports_tools,
                supports_vision: existing.supports_vision,
              }
            : { name, tier: '', context_window: 0 },
        );
      }
    }

    const payload: ModelProviderFormData = { ...formData, models };

    setSaving(true);
    try {
      await adminApi.providers.create(payload);
      await queryClient.invalidateQueries({ queryKey: ['models', 'providers'] });
      await queryClient.invalidateQueries({ queryKey: ['models', 'default'] });
      await queryClient.invalidateQueries({ queryKey: ['models', 'health'] });
      toast({ variant: 'success', title: t('deepseekSetup.providerCreated') });
      setOpen(false);
      setPhase('hide');
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setFormError(msg);
    } finally {
      setSaving(false);
    }
  }, [formData, modelsInput, presetCatalog, queryClient, t, toast]);

  if (phase !== 'show') {
    return null;
  }

  return (
    <Modal isOpen={open} onClose={handleClose} size="lg">
      <ModalHeader onClose={handleClose}>
        {t('deepseekSetup.title')}
      </ModalHeader>
      <ModalBody className="space-y-5">
        <p className="text-sm text-gray-600 dark:text-gray-400">
          {t('deepseekSetup.subtitle')}
        </p>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {t('admin.provider.providerIdLabel')}
          </label>
          <Input
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            placeholder={t('admin.provider.nameExample')}
            disabled={saving}
          />
          <p className="mt-1 text-xs text-gray-500">
            {t('admin.provider.idImmutableHint')}
          </p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {t('admin.provider.type')}
          </label>
          <Select
            value={formData.type}
            onChange={(e) => {
              const newType = e.target.value as ProviderType;
              const preset = presets.find((p) => p.type === newType);
              setFormError('');
              if (preset) {
                applyPreset(preset);
                setFormData((prev) => ({ ...prev, name: prev.name, type: newType }));
              } else {
                setModelsInput('');
                setFormData((prev) => ({
                  ...prev,
                  type: newType,
                  models: [],
                }));
              }
            }}
            disabled={saving}
          >
            {presets.map((p) => (
              <option key={p.type} value={p.type}>
                {p.label}
              </option>
            ))}
          </Select>
        </div>

        {requiresApiKey && (
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('admin.provider.apiKey')}
            </label>
            <Input
              type="password"
              value={formData.api_key ?? ''}
              onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
              placeholder={t('admin.provider.apiKeyEnter')}
              disabled={saving}
            />
            {formData.type === 'deepseek' && (
              <div className="mt-3 rounded-lg border border-border bg-surface-sunken/50 p-3">
                <div className="flex items-start gap-3">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border bg-surface text-muted-foreground">
                    <Settings className="h-4 w-4" aria-hidden />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-foreground">
                      {t('admin.provider.deepseekBuyGuideTitle')}
                    </p>
                    <p className="mt-0.5 text-xs leading-5 text-muted-foreground">
                      {t('admin.provider.deepseekBuyGuideSubtitle')}
                    </p>
                  </div>
                </div>

                <ol className="mt-3 space-y-2">
                  {[
                    t('admin.provider.deepseekBuyGuideStep1'),
                    t('admin.provider.deepseekBuyGuideStep2'),
                    t('admin.provider.deepseekBuyGuideStep3'),
                  ].map((step, index) => (
                    <li key={step} className="flex gap-2 text-xs leading-5 text-foreground/80">
                      <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-border bg-surface text-[11px] font-medium text-muted-foreground">
                        {index + 1}
                      </span>
                      <span>{step}</span>
                    </li>
                  ))}
                </ol>

                <div className="mt-3 flex flex-wrap gap-2">
                  <a
                    href="https://platform.deepseek.com"
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-surface-sunken"
                  >
                    {t('admin.provider.deepseekBuyGuidePlatform')}
                    <ExternalLink className="h-3 w-3" aria-hidden />
                  </a>
                  <a
                    href="https://api-docs.deepseek.com/quick_start/pricing"
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-surface hover:text-foreground"
                  >
                    {t('admin.provider.deepseekBuyGuidePricing')}
                    <ExternalLink className="h-3 w-3" aria-hidden />
                  </a>
                </div>
              </div>
            )}
            {formData.type === 'qwen' && (
              <p className="mt-1 text-xs text-gray-500">
                {t('admin.provider.qwenApiKeyHint')}
              </p>
            )}
          </div>
        )}

        {showAdvancedProviderFields && showBaseUrl && (
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('admin.provider.endpointUrlLabel')}
            </label>
            <Input
              value={formData.base_url ?? ''}
              onChange={(e) => setFormData({ ...formData, base_url: e.target.value })}
              placeholder={currentPreset?.default_base_url || 'https://api.example.com/v1'}
              disabled={saving}
            />
          </div>
        )}

        {showAdvancedProviderFields && (
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('admin.provider.availableModelsLabel')}
            </label>
            {usePresetModelMultiselect ? (
              <div className="space-y-2 max-h-56 overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                {presetCatalog.map((m) => {
                  const checked = (formData.models ?? []).some((x) => x.name === m.name);
                  return (
                    <label
                      key={m.name}
                      className="flex items-start gap-2.5 cursor-pointer text-sm text-gray-800 dark:text-gray-200"
                    >
                      <input
                        type="checkbox"
                        className="mt-1 rounded border-gray-300 dark:border-gray-600"
                        checked={checked}
                        onChange={() => togglePresetCatalogModel(m)}
                        disabled={saving}
                      />
                      <span>
                        <span className="font-mono text-xs">{m.name}</span>
                        {m.description ? (
                          <span className="block text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                            {m.description}
                          </span>
                        ) : null}
                      </span>
                    </label>
                  );
                })}
                <p className="text-xs text-gray-500 dark:text-gray-400 pt-1">
                  {t('admin.provider.modelsCheckboxHelp')}
                </p>
              </div>
            ) : (
              <>
                <Textarea
                  value={modelsInput}
                  onChange={(e) => {
                    setFormError('');
                    setModelsInput(e.target.value);
                  }}
                  placeholder={t('admin.provider.modelsOnePerLinePlaceholder')}
                  rows={5}
                  className="font-mono text-sm"
                  disabled={saving}
                />
                <p className="mt-1 text-xs text-gray-500">
                  {t('admin.provider.modelsOnePerLineHelp')}
                </p>
              </>
            )}
            {formError ? (
              <p className="mt-2 text-sm text-red-600 dark:text-red-400" role="alert">
                {formError}
              </p>
            ) : null}
          </div>
        )}

        <div className="flex items-center gap-2">
          <Switch
            checked={formData.enabled}
            onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
            disabled={saving}
          />
          <span className="text-sm text-gray-700 dark:text-gray-300">
            {t('admin.provider.enableProvider')}
          </span>
        </div>
      </ModalBody>
      <ModalFooter>
        <Link
          to="/settings"
          className={cn(
            'inline-flex items-center justify-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-surface-sunken no-underline',
          )}
          onClick={handleClose}
        >
          <Settings className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
          {t('deepseekSetup.openSettings')}
        </Link>
        <Button variant="secondary" onClick={handleClose}>
          {t('common.cancel')}
        </Button>
        <Button
          onClick={handleSubmit}
          loading={saving}
          disabled={!formData.name.trim()}
        >
          {t('common.create')}
        </Button>
      </ModalFooter>
    </Modal>
  );
}
