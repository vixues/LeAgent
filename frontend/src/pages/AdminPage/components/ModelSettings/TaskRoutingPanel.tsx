import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Card, CardHeader, CardTitle, CardContent, Button, Select } from '@/components/ui';
import { PageLoader } from '@/components/common/PageLoader';
import { useTaskRouting, useSetTaskRouting } from '@/hooks/useAdmin';
import { TASK_KEYS } from '@/lib/modelTasks';
import type { ModelProvider, ModelTaskKey, TaskBinding } from '@/types/admin';

interface TaskRoutingPanelProps {
  providers: ModelProvider[];
}

export function TaskRoutingPanel({ providers }: TaskRoutingPanelProps) {
  const { t } = useTranslation();
  const { data: remoteTasks, isLoading } = useTaskRouting();
  const setTaskRouting = useSetTaskRouting();
  const [localTasks, setLocalTasks] = useState<Partial<Record<ModelTaskKey, TaskBinding>>>({});
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (remoteTasks && !dirty) {
      setLocalTasks(remoteTasks as Partial<Record<ModelTaskKey, TaskBinding>>);
    }
  }, [remoteTasks, dirty]);

  const enabledProviders = useMemo(
    () => providers.filter((p) => p.enabled !== false),
    [providers],
  );

  const modelOptions = useMemo(() => {
    const options: Array<{ value: string; label: string }> = [];
    for (const provider of enabledProviders) {
      for (const model of provider.models.filter((m) => m.enabled !== false)) {
        options.push({
          value: `${provider.name}/${model.name}`,
          label: `${provider.label || provider.name} / ${model.name}`,
        });
      }
    }
    return options;
  }, [enabledProviders]);

  const updateTask = (task: ModelTaskKey, value: string) => {
    setDirty(true);
    if (!value) {
      setLocalTasks((prev) => {
        const next = { ...prev };
        delete next[task];
        return next;
      });
      return;
    }
    const slash = value.indexOf('/');
    if (slash <= 0) return;
    setLocalTasks((prev) => ({
      ...prev,
      [task]: {
        provider: value.slice(0, slash),
        model: value.slice(slash + 1),
      },
    }));
  };

  const handleSave = async () => {
    const payload: Record<string, TaskBinding> = {};
    for (const key of TASK_KEYS) {
      const binding = localTasks[key];
      if (binding?.provider && binding?.model) {
        payload[key] = binding;
      }
    }
    await setTaskRouting.mutateAsync(payload);
    setDirty(false);
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">{t('admin.modelSettings.taskRouting.title')}</CardTitle>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
          {t('admin.modelSettings.taskRouting.desc')}
        </p>
      </CardHeader>
      <CardContent className="pt-0">
        {isLoading ? (
          <PageLoader size="sm" message={t('common.loading')} />
        ) : (
          <div className="space-y-3">
            {TASK_KEYS.map((task) => {
              const binding = localTasks[task];
              const value =
                binding?.provider && binding?.model
                  ? `${binding.provider}/${binding.model}`
                  : '';
              return (
                <div key={task} className="grid gap-2 sm:grid-cols-[8rem_1fr] sm:items-center">
                  <label className="text-xs font-medium text-gray-600 dark:text-gray-300">
                    {t(`admin.modelSettings.taskRouting.tasks.${task}`)}
                  </label>
                  <Select
                    value={value}
                    onChange={(e) => updateTask(task, e.target.value)}
                    className="h-8 text-xs"
                  >
                    <option value="">{t('admin.modelSettings.taskRouting.unset')}</option>
                    {modelOptions.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </Select>
                </div>
              );
            })}
            <div className="flex justify-end pt-2">
              <Button
                size="sm"
                onClick={handleSave}
                loading={setTaskRouting.isPending}
                disabled={!dirty}
              >
                {t('common.save')}
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
