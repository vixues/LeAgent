import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardHeader, CardTitle, Select } from '@/components/ui';
import { useDefaultModel, useSetDefaultModel } from '@/hooks/useAdmin';
import type { ModelProvider } from '@/types/admin';

interface DefaultModelCardProps {
  providers: ModelProvider[];
}

export function DefaultModelCard({ providers }: DefaultModelCardProps) {
  const { t } = useTranslation();
  const { data: defaultModel } = useDefaultModel();
  const setDefaultModel = useSetDefaultModel();

  const enabledProviders = useMemo(
    () => providers.filter((p) => p.enabled !== false),
    [providers],
  );

  const handleSetDefaultModel = (providerName: string, modelName: string) => {
    setDefaultModel.mutate({ provider: providerName, model: modelName });
  };

  return (
    <Card padding="sm">
      <CardHeader className="mb-0 flex-col items-stretch gap-0 p-0 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 flex-1 flex-col gap-0.5 pb-3 sm:pb-0 sm:pr-4">
          <CardTitle className="text-sm font-semibold leading-tight">
            {t('admin.modelSettings.defaultModel.title')}
          </CardTitle>
          <p className="text-[11px] leading-snug text-gray-500 dark:text-gray-400">
            {t('admin.modelSettings.defaultModel.desc')}
          </p>
        </div>
        <div className="relative w-full shrink-0 sm:w-auto sm:max-w-md">
          <Select
            value={
              defaultModel?.provider && defaultModel?.model
                ? `${defaultModel.provider}/${defaultModel.model}`
                : ''
            }
            onChange={(e) => {
              const [providerName = '', ...modelParts] = e.target.value.split('/');
              const model = modelParts.join('/');
              if (providerName && model) handleSetDefaultModel(providerName, model);
            }}
            className="h-9 max-w-md py-1.5 sm:min-w-[16rem]"
          >
            <option value="">{t('admin.modelSettings.defaultModel.selectPlaceholder')}</option>
            {enabledProviders.map((p) => (
              <optgroup key={p.name} label={p.label || p.name}>
                {p.models
                  .filter((m) => m.enabled !== false)
                  .map((m) => (
                    <option key={`${p.name}/${m.name}`} value={`${p.name}/${m.name}`}>
                      {m.name}
                    </option>
                  ))}
              </optgroup>
            ))}
          </Select>
        </div>
      </CardHeader>
    </Card>
  );
}
