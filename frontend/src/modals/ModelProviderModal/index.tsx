import { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { BaseModal } from '../BaseModal';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Switch } from '@/components/ui/Switch';
import { cn } from '@/lib/utils';

export interface ModelProvider {
  id?: string;
  name: string;
  type: 'openai' | 'azure' | 'anthropic' | 'ollama' | 'custom' | 'deepseek';
  baseUrl: string;
  apiKey: string;
  models: string;
  enabled: boolean;
}

interface ModelProviderModalProps {
  isOpen: boolean;
  onClose: () => void;
  provider?: ModelProvider | null;
  onSave: (provider: ModelProvider) => void;
}

const defaultBaseUrls: Record<string, string> = {
  openai: 'https://api.openai.com/v1',
  azure: 'https://YOUR_RESOURCE.openai.azure.com',
  anthropic: 'https://api.anthropic.com',
  ollama: 'http://localhost:11434',
  deepseek: 'https://api.deepseek.com',
  custom: '',
};

export const ModelProviderModal = ({
  isOpen,
  onClose,
  provider,
  onSave,
}: ModelProviderModalProps) => {
  const { t } = useTranslation();
  const providerTypes = useMemo(
    () => [
      { value: 'openai' as const, label: 'OpenAI' },
      { value: 'azure' as const, label: 'Azure OpenAI' },
      { value: 'anthropic' as const, label: 'Anthropic' },
      { value: 'deepseek' as const, label: 'DeepSeek' },
      { value: 'ollama' as const, label: 'Ollama' },
      { value: 'custom' as const, label: t('modals.modelProvider.types.custom') },
    ],
    [t]
  );
  const isEdit = !!provider?.id;

  const [formData, setFormData] = useState<ModelProvider>({
    name: '',
    type: 'openai',
    baseUrl: defaultBaseUrls.openai ?? '',
    apiKey: '',
    models: '',
    enabled: true,
  });

  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<'success' | 'error' | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (provider) {
      setFormData(provider);
    } else {
      setFormData({
        name: '',
        type: 'openai',
        baseUrl: defaultBaseUrls.openai ?? '',
        apiKey: '',
        models: '',
        enabled: true,
      });
    }
    setTestResult(null);
    setErrors({});
  }, [provider, isOpen]);

  const handleTypeChange = (type: ModelProvider['type']) => {
    setFormData((prev) => ({
      ...prev,
      type,
      baseUrl: defaultBaseUrls[type] ?? '',
    }));
  };

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};
    if (!formData.name.trim()) {
      newErrors.name = t('modals.provider.errors.nameRequired');
    }
    if (!formData.baseUrl.trim()) {
      newErrors.baseUrl = t('modals.provider.errors.baseUrlRequired');
    }
    if (!formData.apiKey.trim() && formData.type !== 'ollama') {
      newErrors.apiKey = t('modals.provider.errors.apiKeyRequired');
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleTest = async () => {
    if (!validate()) return;

    setTesting(true);
    setTestResult(null);

    try {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      const success = Math.random() > 0.3;
      setTestResult(success ? 'success' : 'error');
    } catch {
      setTestResult('error');
    } finally {
      setTesting(false);
    }
  };

  const handleSave = () => {
    if (!validate()) return;
    onSave(formData);
    onClose();
  };

  const footer = (
    <>
      <Button variant="outline" onClick={onClose}>
        {t('common.cancel')}
      </Button>
      <Button
        variant="secondary"
        onClick={handleTest}
        loading={testing}
        disabled={testing}
      >
        {t('admin.provider.test')}
      </Button>
      <Button onClick={handleSave}>{t('common.save')}</Button>
    </>
  );

  return (
    <BaseModal
      isOpen={isOpen}
      onClose={onClose}
      title={isEdit ? t('admin.provider.edit') : t('admin.provider.add')}
      size="lg"
      footer={footer}
    >
      <div className="space-y-5">
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">
            {t('admin.provider.name')}
          </label>
          <Input
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            placeholder={t('admin.provider.namePlaceholder')}
            error={errors.name}
          />
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">
            {t('admin.provider.type')}
          </label>
          <Select
            value={formData.type}
            onChange={(e) =>
              handleTypeChange(e.target.value as ModelProvider['type'])
            }
          >
            {providerTypes.map((type) => (
              <option key={type.value} value={type.value}>
                {type.label}
              </option>
            ))}
          </Select>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">
            {t('admin.provider.baseUrl')}
          </label>
          <Input
            value={formData.baseUrl}
            onChange={(e) => setFormData({ ...formData, baseUrl: e.target.value })}
            placeholder={t('integrations.placeholderUrl')}
            error={errors.baseUrl}
          />
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">
            {t('admin.provider.apiKey')}
          </label>
          <Input
            type="password"
            value={formData.apiKey}
            onChange={(e) => setFormData({ ...formData, apiKey: e.target.value })}
            placeholder={t('admin.provider.apiKeyPlaceholder')}
            error={errors.apiKey}
          />
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">
            {t('admin.provider.models')}
          </label>
          <Input
            value={formData.models}
            onChange={(e) => setFormData({ ...formData, models: e.target.value })}
            placeholder={t('admin.provider.modelsPlaceholder')}
          />
          <p className="text-xs text-muted-foreground">
            {t('admin.provider.modelsHelp')}
          </p>
        </div>

        <div className="flex items-center justify-between py-2">
          <span className="text-sm font-medium text-foreground">
            {t('admin.provider.enableProvider')}
          </span>
          <Switch
            checked={formData.enabled}
            onCheckedChange={(checked) =>
              setFormData({ ...formData, enabled: checked })
            }
          />
        </div>

        {testResult && (
          <div
            className={cn(
              'p-4 rounded-lg flex items-center gap-3',
              testResult === 'success'
                ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
                : 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800'
            )}
          >
            {testResult === 'success' ? (
              <>
                <svg
                  className="w-5 h-5 text-green-600 dark:text-green-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M5 13l4 4L19 7"
                  />
                </svg>
                <span className="text-sm text-green-800 dark:text-green-200">
                  {t('admin.provider.testSuccess')}
                </span>
              </>
            ) : (
              <>
                <svg
                  className="w-5 h-5 text-red-600 dark:text-red-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
                <span className="text-sm text-red-800 dark:text-red-200">
                  {t('admin.provider.testFailed')}
                </span>
              </>
            )}
          </div>
        )}
      </div>
    </BaseModal>
  );
};

export default ModelProviderModal;
