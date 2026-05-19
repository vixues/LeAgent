import { useState, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Card,
  CardContent,
  Button,
  Input,
  Switch,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Badge,
  Textarea,
} from '@/components/ui';
import { useAdminStore } from '@/stores/admin';
import {
  useRules,
  useRule,
  useCreateRule,
  useUpdateRule,
  useTestRule,
} from '@/hooks/useAdmin';
import type { RuleSetInfo, RuleSetCreateData, RuleSetUpdateData } from '@/types/admin';

interface RuleSetEditorForm {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  tagsText: string;
  rulesJson: string;
}

const DEFAULT_FORM_DATA: RuleSetEditorForm = {
  id: '',
  name: '',
  description: '',
  enabled: true,
  tagsText: '',
  rulesJson: '[]',
};

export function RuleEditor() {
  const { t } = useTranslation();
  const { data: rules, isLoading } = useRules();
  const createRule = useCreateRule();
  const updateRule = useUpdateRule();
  const testRule = useTestRule();

  const {
    selectedRule,
    setSelectedRule,
    isRuleModalOpen,
    setRuleModalOpen,
  } = useAdminStore();

  const [formData, setFormData] = useState<RuleSetEditorForm>(DEFAULT_FORM_DATA);
  const [testData, setTestData] = useState('{}');
  const [testResult, setTestResult] = useState<{ success: boolean; result: unknown } | null>(null);
  const [testError, setTestError] = useState('');
  const hydratedRuleSetId = useRef<string | null>(null);

  const detailQuery = useRule(selectedRule?.id ?? '', {
    enabled: isRuleModalOpen && !!selectedRule,
  });

  const handleOpenCreate = () => {
    hydratedRuleSetId.current = null;
    setSelectedRule(null);
    setFormData(DEFAULT_FORM_DATA);
    setTestResult(null);
    setTestError('');
    setRuleModalOpen(true);
  };

  const handleOpenEdit = (rule: RuleSetInfo) => {
    hydratedRuleSetId.current = null;
    setSelectedRule(rule);
    setFormData({
      id: rule.id,
      name: rule.name,
      description: rule.description ?? '',
      enabled: rule.enabled,
      tagsText: rule.tags.join(', '),
      rulesJson: '[]',
    });
    setTestResult(null);
    setTestError('');
    setRuleModalOpen(true);
  };

  useEffect(() => {
    if (!isRuleModalOpen || !selectedRule || !detailQuery.data) return;
    if (hydratedRuleSetId.current === selectedRule.id) return;
    hydratedRuleSetId.current = selectedRule.id;
    const d = detailQuery.data;
    setFormData({
      id: d.id,
      name: d.name,
      description: d.description ?? '',
      enabled: d.enabled,
      tagsText: d.tags.join(', '),
      rulesJson: JSON.stringify(d.rules ?? [], null, 2),
    });
  }, [isRuleModalOpen, selectedRule, detailQuery.data]);

  const handleClose = () => {
    setRuleModalOpen(false);
    setSelectedRule(null);
    hydratedRuleSetId.current = null;
    setFormData(DEFAULT_FORM_DATA);
    setTestResult(null);
    setTestError('');
  };

  const handleSubmit = async () => {
    let rules: Record<string, unknown>[] = [];
    try {
      const parsed = JSON.parse(formData.rulesJson || '[]');
      if (!Array.isArray(parsed)) throw new Error('not_array');
      rules = parsed as Record<string, unknown>[];
    } catch {
      window.alert(t('admin.rule.invalidRulesJson'));
      return;
    }

    const tags = formData.tagsText
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);

    if (selectedRule) {
      const payload: RuleSetUpdateData = {
        name: formData.name,
        description: formData.description || undefined,
        enabled: formData.enabled,
        tags,
        rules,
      };
      await updateRule.mutateAsync({ id: selectedRule.id, data: payload });
    } else {
      if (!formData.id.trim()) {
        window.alert(t('admin.rule.idRequired'));
        return;
      }
      const payload: RuleSetCreateData = {
        id: formData.id.trim(),
        name: formData.name,
        description: formData.description || undefined,
        enabled: formData.enabled,
        tags,
        rules,
      };
      await createRule.mutateAsync(payload);
    }
    handleClose();
  };

  const handleTest = async () => {
    if (!selectedRule) return;
    setTestError('');
    setTestResult(null);
    try {
      const data = JSON.parse(testData) as Record<string, unknown>;
      const result = await testRule.mutateAsync({ id: selectedRule.id, data });
      setTestResult({ success: result.passed, result });
    } catch (e) {
      if ((e as Error).message.includes('JSON')) {
        setTestError(t('admin.rule.invalidTestData'));
      } else {
        setTestError((e as Error).message);
      }
    }
  };

  const sortedRules = rules?.slice().sort((a, b) => a.name.localeCompare(b.name));

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-gray-500 dark:text-gray-400">{t('common.loading')}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            {t('admin.rule.title')}
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {t('admin.rule.description')}
          </p>
        </div>
        <Button onClick={handleOpenCreate}>
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          {t('admin.rule.add')}
        </Button>
      </div>

      <div className="space-y-4">
        {sortedRules?.map((rule) => (
          <Card key={rule.id} className="hover:shadow-md transition-shadow">
            <CardContent className="p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-2 flex-wrap">
                    <code className="text-xs text-gray-500 dark:text-gray-400">{rule.id}</code>
                    <h4 className="font-medium text-gray-900 dark:text-white">
                      {rule.name}
                    </h4>
                    <Badge variant={rule.enabled ? 'success' : 'default'}>
                      {rule.enabled ? t('admin.rule.enabled') : t('admin.rule.disabled')}
                    </Badge>
                    <Badge variant="info">
                      {rule.rule_count} {t('admin.rule.rulesInSet')}
                    </Badge>
                  </div>
                  {rule.description && (
                    <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">
                      {rule.description}
                    </p>
                  )}
                  {rule.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {rule.tags.map((tag) => (
                        <Badge key={tag} variant="secondary" className="text-xs">
                          {tag}
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex flex-col gap-2">
                  <Button variant="ghost" size="sm" onClick={() => handleOpenEdit(rule)}>
                    {t('common.edit')}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}

        {(!rules || rules.length === 0) && (
          <Card className="text-center py-12">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
              <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
              </svg>
            </div>
            <p className="text-gray-500 dark:text-gray-400">{t('admin.rule.empty')}</p>
            <Button className="mt-4" onClick={handleOpenCreate}>
              {t('admin.rule.add')}
            </Button>
          </Card>
        )}
      </div>

      <Modal isOpen={isRuleModalOpen} onClose={handleClose} size="xl">
        <ModalHeader onClose={handleClose}>
          {selectedRule ? t('admin.rule.edit') : t('admin.rule.add')}
        </ModalHeader>
        <ModalBody className="space-y-4">
          {!selectedRule && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('admin.rule.ruleSetId')}
              </label>
              <Input
                value={formData.id}
                onChange={(e) => setFormData({ ...formData, id: e.target.value })}
                placeholder={t('admin.rule.ruleSetIdPlaceholder')}
              />
              <p className="mt-1 text-xs text-gray-500">
                {t('admin.rule.ruleSetIdHelp')}
              </p>
            </div>
          )}
          {selectedRule && detailQuery.isFetching && (
            <p className="text-sm text-gray-500">{t('common.loading')}</p>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('admin.rule.name')}
              </label>
              <Input
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder={t('admin.rule.namePlaceholder')}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t('admin.rule.tags')}
              </label>
              <Input
                value={formData.tagsText}
                onChange={(e) => setFormData({ ...formData, tagsText: e.target.value })}
                placeholder={t('admin.rule.tagsPlaceholder')}
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('admin.rule.descriptionLabel')}
            </label>
            <Input
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder={t('admin.rule.descriptionPlaceholder')}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t('admin.rule.rulesJson')}
            </label>
            <Textarea
              value={formData.rulesJson}
              onChange={(e) => setFormData({ ...formData, rulesJson: e.target.value })}
                placeholder="[]"
              className="font-mono text-sm min-h-[200px]"
            />
            <p className="mt-1 text-xs text-gray-500">
              {t('admin.rule.rulesJsonHelp')}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Switch
              checked={formData.enabled}
              onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
            />
            <span className="text-sm text-gray-700 dark:text-gray-300">
              {t('admin.rule.enableRule')}
            </span>
          </div>

          {selectedRule && (
            <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
              <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {t('admin.rule.testRule')}
              </h4>
              <Textarea
                value={testData}
                onChange={(e) => setTestData(e.target.value)}
                placeholder='{"key": "value"}'
                className="font-mono text-sm mb-3"
              />
              <Button
                variant="secondary"
                size="sm"
                onClick={handleTest}
                loading={testRule.isPending}
              >
                {t('admin.rule.runTest')}
              </Button>
              {testError && (
                <div className="mt-3 p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 text-sm">
                  {testError}
                </div>
              )}
              {testResult && (
                <div
                  className={`mt-3 p-3 rounded-lg text-sm ${
                    testResult.success
                      ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300'
                      : 'bg-yellow-50 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-300'
                  }`}
                >
                  <p className="font-medium mb-1">
                    {testResult.success ? t('admin.rule.testPassed') : t('admin.rule.testFailed')}
                  </p>
                  <pre className="text-xs overflow-auto">
                    {JSON.stringify(testResult.result, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </ModalBody>
        <ModalFooter>
          <Button variant="secondary" onClick={handleClose}>
            {t('common.cancel')}
          </Button>
          <Button
            onClick={handleSubmit}
            loading={createRule.isPending || updateRule.isPending}
            disabled={
              !formData.name ||
              (!selectedRule && !formData.id.trim()) ||
              (!!selectedRule && detailQuery.isFetching && !hydratedRuleSetId.current)
            }
          >
            {selectedRule ? t('common.save') : t('common.create')}
          </Button>
        </ModalFooter>
      </Modal>
    </div>
  );
}
